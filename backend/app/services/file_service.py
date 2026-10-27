"""Upload, replication, integrity verification, verified download and recovery.

Trust rule used everywhere in this file: the ONLY trusted hash is the one the
coordinator calculated at upload time and stored in SQLite (and on the ledger).
A replica is trusted only after the coordinator downloads its bytes and
recalculates SHA-256 itself. A node's own claim about its hash is shown for
comparison but never relied on.
"""
import time
import threading
import uuid
from pathlib import PurePath

from shared.blockcore import NODE_IDS, QUORUM, sha256_bytes, utc_now

from ..blockchain import consensus
from ..config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES
from ..database import db
from . import node_client


class UploadError(Exception):
    def __init__(self, status: int, message: str, details=None):
        super().__init__(message)
        self.status, self.message, self.details = status, message, details


class VersionConflict(Exception):
    def __init__(self, latest: dict):
        super().__init__("A newer document version was committed. Refresh and base the next version on it.")
        self.latest = latest


_version_lock = threading.Lock()


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def clean_filename(name: str) -> str:
    name = PurePath(name or "").name.strip()          # drop any directory part
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"/\\|?*')
    return name[:120]


# ---------------------------------------------------------------------------
# Upload + replication
# ---------------------------------------------------------------------------
def upload(filename: str, content_type: str | None, data: bytes, owner_org_id: str,
           document_id: str | None = None, version_number: int = 1,
           previous_file_id: str | None = None) -> dict:
    t_total = time.perf_counter()
    name = clean_filename(filename)
    ext = PurePath(name).suffix.lower()
    if not name or not ext:
        raise UploadError(400, "File name is missing or has no extension.")
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError(415, f"File type '{ext}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if len(data) == 0:
        raise UploadError(400, "The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(413, f"File is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    # 1. Trusted hash, calculated by the coordinator from the uploaded bytes
    t = time.perf_counter()
    trusted_hash = sha256_bytes(data)
    file_id = uuid.uuid4().hex
    document_id = document_id or file_id
    hash_ms = _ms(t)

    # 2. Replicate to all five nodes in parallel
    t = time.perf_counter()
    results = node_client.call_all("PUT", f"/files/{file_id}", data=data,
                                   timeout=node_client.file_timeout(len(data)))
    replication_ms = _ms(t)
    replicas, ok_nodes, failed_nodes = [], [], []
    for nid in NODE_IDS:
        res = results[nid]
        returned = res["body"].get("sha256") if res["ok"] else None
        if res["ok"] and returned == trusted_hash:
            ok_nodes.append(nid)
            replicas.append({"node_id": nid, "stored": True, "returned_hash": returned, "hash_match": True})
        else:
            failed_nodes.append(nid)
            replicas.append({"node_id": nid, "stored": bool(res["ok"]), "returned_hash": returned,
                             "hash_match": False, "error": res.get("error") or "returned hash did not match"})

    # 3. Need at least a quorum of good replicas, otherwise undo and report honestly
    if len(ok_nodes) < QUORUM:
        node_client.call_all("DELETE", f"/files/{file_id}", node_ids=[r["node_id"] for r in replicas if r["stored"]])
        db.log_event("error", "upload", f"Upload of '{name}' failed: only {len(ok_nodes)} replica(s) stored",
                     {"replicas": replicas})
        raise UploadError(503, f"Only {len(ok_nodes)} of 5 nodes stored a verified copy; at least {QUORUM} are required. "
                               "Upload was rolled back.", {"replicas": replicas})

    # 4. Persist the trusted metadata (written once, never overwritten)
    db.execute("""INSERT INTO files
                  (file_id, document_id, version_number, previous_file_id, name, size, sha256,
                   content_type, uploaded_at, owner_org_id)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (file_id, document_id, version_number, previous_file_id, name, len(data), trusted_hash,
                content_type, db.now(), owner_org_id))
    for r in replicas:
        db.upsert_replica(file_id, r["node_id"], "match" if r["hash_match"] else "unavailable",
                          computed_hash=r["returned_hash"], detail=r.get("error"))

    # 5. Commit FILE_UPLOADED + FILE_REPLICATED through majority voting
    t = time.perf_counter()
    now = utc_now()
    try:
        registration = (
            {"type": "FILE_VERSION_CREATED", "file_id": file_id, "document_id": document_id,
             "version_number": version_number, "previous_file_id": previous_file_id,
             "file_name": name, "size": len(data), "sha256": trusted_hash, "timestamp": now}
            if previous_file_id else
            {"type": "FILE_UPLOADED", "file_id": file_id, "document_id": document_id,
             "version_number": version_number, "file_name": name, "size": len(data),
             "sha256": trusted_hash, "timestamp": now}
        )
        proposal = consensus.propose_transactions([
            registration,
            {"type": "FILE_REPLICATED", "file_id": file_id, "sha256": trusted_hash,
             "nodes_ok": ok_nodes, "nodes_failed": failed_nodes, "timestamp": now},
        ])
    except consensus.NoQuorum as exc:
        proposal = {"outcome": "rejected", "reason": str(exc), "block": {}}
    ledger_ms = _ms(t)

    if proposal["outcome"] != "committed":
        # The ledger refused the record - roll back everything so state stays consistent
        node_client.call_all("DELETE", f"/files/{file_id}", node_ids=ok_nodes)
        db.execute("DELETE FROM replicas WHERE file_id = ?", (file_id,))
        db.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        db.log_event("error", "upload", f"Upload of '{name}' rolled back: ledger commit failed",
                     {"reason": proposal.get("reason")})
        raise UploadError(503, f"Ledger commit failed: {proposal.get('reason')}. Upload was rolled back.")

    db.execute("UPDATE files SET ledger_block = ? WHERE file_id = ?", (proposal["block"]["index"], file_id))
    level = "success" if not failed_nodes else "warning"
    db.log_event(level, "upload",
                 f"Uploaded '{name}' version {version_number} - {len(ok_nodes)}/5 verified replicas"
                 + (f" (missing on {', '.join(failed_nodes)})" if failed_nodes else ""),
                 {"file_id": file_id, "sha256": trusted_hash})
    return {
        "file_id": file_id, "document_id": document_id, "version_number": version_number,
        "previous_file_id": previous_file_id, "name": name, "size": len(data), "sha256": trusted_hash,
        "owner_org_id": owner_org_id,
        "replicas": replicas, "healthy_replicas": len(ok_nodes), "failed_replicas": len(failed_nodes),
        "fully_replicated": not failed_nodes, "ledger_block": proposal["block"]["index"],
        "proposal_id": proposal["proposal_id"],
        "timing_ms": {"hash": hash_ms, "replication": replication_ms, "ledger_commit": ledger_ms,
                      "total": _ms(t_total)},
    }


def upload_version(parent_file_id: str, expected_version: int, filename: str, content_type: str | None,
                   data: bytes, owner_org_id: str) -> dict:
    """Commit a new version only if its selected parent is still the document's latest version."""
    with _version_lock:
        parent = get_file(parent_file_id)
        if not parent or parent["owner_org_id"] != owner_org_id:
            raise UploadError(404, "File not found")
        latest = db.one(
            "SELECT file_id, version_number FROM files WHERE document_id=? ORDER BY version_number DESC LIMIT 1",
            (parent["document_id"],),
        )
        if (parent["version_number"] != expected_version or not latest
                or latest["file_id"] != parent_file_id):
            raise VersionConflict(latest or {"file_id": None, "version_number": None})
        return upload(filename, content_type, data, owner_org_id,
                      document_id=parent["document_id"], version_number=expected_version + 1,
                      previous_file_id=parent_file_id)


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------
def get_file(file_id: str) -> dict | None:
    return db.one("SELECT * FROM files WHERE file_id = ?", (file_id,))


def _fetch_and_hash(node_id: str, file_id: str, size: int) -> dict:
    """Download one node's replica and hash it HERE, on the coordinator."""
    res = node_client.call(node_id, "GET", f"/files/{file_id}", raw=True,
                           timeout=node_client.file_timeout(size))
    if res["ok"]:
        return {"available": True, "content": res["content"], "computed_hash": sha256_bytes(res["content"])}
    if res["status"] == 404:
        return {"available": True, "missing": True, "error": "node has no copy"}
    return {"available": False, "error": res.get("error")}


def check_replicas(file_id: str, record: bool = True) -> dict:
    """Compare every node's copy with the trusted hash. Returns the integrity table."""
    f = get_file(file_id)
    if not f:
        return None
    t = time.perf_counter()
    trusted = f["sha256"]
    futures = {nid: node_client._pool.submit(_fetch_and_hash, nid, file_id, f["size"]) for nid in NODE_IDS}
    reported = node_client.call_all("GET", f"/files/{file_id}/hash")
    table = []
    for nid in NODE_IDS:
        r = futures[nid].result()
        claim = reported[nid]["body"].get("sha256") if reported[nid]["ok"] else None
        if not r["available"]:
            status, action = "unavailable", "Node offline - cannot verify"
        elif r.get("missing"):
            status, action = "missing", "Replica missing - repair needed"
        elif r["computed_hash"] == trusted:
            status, action = "match", "Trusted replica"
        else:
            status, action = "mismatch", "Tampering / corruption detected"
        lied = status == "mismatch" and claim == trusted
        if lied:
            action += " (node falsely reported a matching hash)"
        table.append({
            "node_id": nid, "online": r["available"], "status": status,
            "hash_match": status == "match", "computed_hash": r.get("computed_hash"),
            "reported_hash": claim, "node_reported_falsely": lied, "action": action,
            "error": r.get("error"),
        })
        if record:
            db.upsert_replica(file_id, nid, status, r.get("computed_hash"), claim, r.get("error"))
    summary = {
        "expected": len(NODE_IDS),
        "healthy": sum(1 for x in table if x["status"] == "match"),
        "mismatched": sum(1 for x in table if x["status"] == "mismatch"),
        "missing": sum(1 for x in table if x["status"] == "missing"),
        "unavailable": sum(1 for x in table if x["status"] == "unavailable"),
    }
    return {"file_id": file_id, "name": f["name"], "trusted_hash": trusted, "replicas": table,
            "summary": summary, "duration_ms": _ms(t)}


def verify(file_id: str) -> dict | None:
    """Run an integrity check and record the result on the ledger."""
    report = check_replicas(file_id)
    if report is None:
        return None
    by_status = lambda s: [r["node_id"] for r in report["replicas"] if r["status"] == s]  # noqa: E731
    now = utc_now()
    txs = [{"type": "INTEGRITY_CHECKED", "file_id": file_id, "sha256": report["trusted_hash"],
            "matching": by_status("match"), "mismatching": by_status("mismatch"),
            "unavailable": by_status("unavailable") + by_status("missing"), "timestamp": now}]
    for r in report["replicas"]:
        if r["status"] == "mismatch":
            txs.append({"type": "MALICIOUS_ACTIVITY_DETECTED", "node_id": r["node_id"], "file_id": file_id,
                        "evidence": f"replica hash {r['computed_hash'][:16]}... != trusted {report['trusted_hash'][:16]}..."
                                    + ("; node falsely reported a matching hash" if r["node_reported_falsely"] else ""),
                        "timestamp": now})
    try:
        proposal = consensus.propose_transactions(txs)
        report["ledger"] = {"outcome": proposal["outcome"], "block": proposal["block"]["index"]}
    except consensus.NoQuorum as exc:
        report["ledger"] = {"outcome": "not recorded", "reason": str(exc)}
    s = report["summary"]
    bad = s["mismatched"] > 0
    db.log_event("warning" if bad else "success", "integrity",
                 f"Integrity check '{report['name']}': {s['healthy']} match, {s['mismatched']} mismatch, "
                 f"{s['missing']} missing, {s['unavailable']} unavailable",
                 {"file_id": file_id, "mismatching": by_status("mismatch")})
    return report


# ---------------------------------------------------------------------------
# Verified download and recovery
# ---------------------------------------------------------------------------
def fetch_verified(file_id: str, exclude_nodes: set[str] | None = None) -> dict:
    """Try the nodes one by one; return the first copy whose hash equals the trusted hash.
    A corrupted or unverifiable copy is NEVER returned."""
    f = get_file(file_id)
    attempts = []
    for nid in NODE_IDS:
        if exclude_nodes and nid in exclude_nodes:
            attempts.append({"node_id": nid, "result": "excluded"})
            continue
        r = _fetch_and_hash(nid, file_id, f["size"])
        if not r["available"]:
            attempts.append({"node_id": nid, "result": "unavailable", "error": r.get("error")})
        elif r.get("missing"):
            attempts.append({"node_id": nid, "result": "missing"})
        elif r["computed_hash"] != f["sha256"]:
            attempts.append({"node_id": nid, "result": "hash mismatch - skipped"})
        else:
            attempts.append({"node_id": nid, "result": "verified"})
            return {"ok": True, "file": f, "content": r["content"], "source_node": nid, "attempts": attempts}
    return {"ok": False, "file": f, "attempts": attempts}


def repair_node_replicas(node_id: str) -> dict:
    """Repair missing or corrupt copies on one rejoined node from another verified replica."""
    if node_id not in NODE_IDS:
        raise ValueError(f"unknown storage node '{node_id}'")

    files = db.rows("SELECT file_id, size, owner_org_id FROM files ORDER BY uploaded_at, file_id")
    results = []
    for file_record in files:
        file_id, size = file_record["file_id"], file_record["size"]
        target = _fetch_and_hash(node_id, file_id, size)
        if not target["available"]:
            results.append({"file_id": file_id, "status": "unavailable", "error": target.get("error")})
            continue
        if not target.get("missing") and target["computed_hash"] == get_file(file_id)["sha256"]:
            db.upsert_replica(file_id, node_id, "match", computed_hash=target["computed_hash"])
            results.append({"file_id": file_id, "status": "already_match"})
            continue

        source = fetch_verified(file_id, exclude_nodes={node_id})
        if not source["ok"]:
            status = "missing" if target.get("missing") else "mismatch"
            db.upsert_replica(file_id, node_id, status, computed_hash=target.get("computed_hash"),
                              detail="No other replica matched the trusted hash.")
            results.append({"file_id": file_id, "status": "no_verified_source"})
            continue

        write = node_client.call(node_id, "PUT", f"/files/{file_id}", data=source["content"],
                                 timeout=node_client.file_timeout(size))
        if not write["ok"] or write["body"].get("sha256") != get_file(file_id)["sha256"]:
            detail = write.get("error") or "node did not acknowledge the trusted SHA-256"
            db.upsert_replica(file_id, node_id, "mismatch", detail=detail)
            db.log_event("error", "recovery", f"Automatic repair failed for {file_id} on {node_id}",
                         {"node_id": node_id, "file_id": file_id, "error": detail},
                         file_record["owner_org_id"])
            results.append({"file_id": file_id, "status": "write_failed", "error": detail})
            continue

        verified = _fetch_and_hash(node_id, file_id, size)
        trusted_hash = get_file(file_id)["sha256"]
        if not verified["available"] or verified.get("missing") or verified["computed_hash"] != trusted_hash:
            detail = verified.get("error") or "post-write verification did not match the trusted SHA-256"
            db.upsert_replica(file_id, node_id, "mismatch", computed_hash=verified.get("computed_hash"),
                              detail=detail)
            db.log_event("error", "recovery", f"Automatic repair verification failed for {file_id} on {node_id}",
                         {"node_id": node_id, "file_id": file_id, "error": detail},
                         file_record["owner_org_id"])
            results.append({"file_id": file_id, "status": "verification_failed", "error": detail})
            continue

        db.upsert_replica(file_id, node_id, "match", computed_hash=verified["computed_hash"])
        repaired_nodes = [node_id]
        try:
            proposal = consensus.propose_transactions([{
                "type": "FILE_RECOVERED", "file_id": file_id, "sha256": trusted_hash,
                "source_node": source["source_node"], "repaired_nodes": repaired_nodes,
                "timestamp": utc_now()}])
            ledger_status = proposal["outcome"]
        except consensus.NoQuorum as exc:
            ledger_status = "not recorded"
            db.log_event("warning", "recovery", f"Automatic repair of {file_id} was not recorded: {exc}",
                         {"node_id": node_id, "file_id": file_id}, file_record["owner_org_id"])

        db.log_event("success", "recovery", f"Automatically repaired {file_id} on {node_id}",
                     {"node_id": node_id, "file_id": file_id, "source_node": source["source_node"],
                      "sha256": trusted_hash, "ledger_status": ledger_status}, file_record["owner_org_id"])
        results.append({"file_id": file_id, "status": "repaired", "source_node": source["source_node"],
                        "ledger_status": ledger_status})

    return {"node_id": node_id, "checked": len(files), "results": results}


def recover(file_id: str) -> dict | None:
    """Get a verified copy from an honest node and re-replicate it to every node
    that is online but has a missing or corrupted replica."""
    f = get_file(file_id)
    if not f:
        return None
    t = time.perf_counter()
    found = fetch_verified(file_id)
    if not found["ok"]:
        db.log_event("error", "recovery", f"Recovery of '{f['name']}' failed: no verified replica available",
                     {"attempts": found["attempts"]})
        return {"ok": False, "file_id": file_id, "name": f["name"], "attempts": found["attempts"],
                "message": "No node holds a copy matching the trusted hash."}

    before = check_replicas(file_id, record=False)
    to_repair = [r["node_id"] for r in before["replicas"] if r["status"] in ("mismatch", "missing")]
    repaired, failed = [], []
    for nid in to_repair:
        res = node_client.call(nid, "PUT", f"/files/{file_id}", data=found["content"],
                               timeout=node_client.file_timeout(f["size"]))
        if res["ok"] and res["body"].get("sha256") == f["sha256"]:
            repaired.append(nid)
        else:
            failed.append({"node_id": nid, "error": res.get("error")})
    after = check_replicas(file_id)          # re-verify from scratch after repair

    if repaired:
        try:
            proposal = consensus.propose_transactions([{
                "type": "FILE_RECOVERED", "file_id": file_id, "sha256": f["sha256"],
                "source_node": found["source_node"], "repaired_nodes": repaired, "timestamp": utc_now()}])
            ledger = {"outcome": proposal["outcome"], "block": proposal["block"]["index"]}
        except consensus.NoQuorum as exc:
            ledger = {"outcome": "not recorded", "reason": str(exc)}
    else:
        ledger = {"outcome": "unchanged", "detail": "No replicas needed repair."}

    db.log_event("success" if repaired else "info", "recovery",
                 (f"Recovered '{f['name']}' from {found['source_node']} (verified)"
                  + (f"; repaired {', '.join(repaired)}" if repaired else "; no repair was needed")),
                 {"file_id": file_id, "source_node": found["source_node"], "repaired": repaired,
                  "repair_failed": failed})
    return {
        "ok": True, "file_id": file_id, "name": f["name"], "trusted_hash": f["sha256"],
        "source_node": found["source_node"], "verified_hash": sha256_bytes(found["content"]),
        "attempts": found["attempts"], "repaired_nodes": repaired, "repair_failed": failed,
        "unavailable_nodes": [r["node_id"] for r in after["replicas"] if r["status"] == "unavailable"],
        "replicas_after": after["replicas"], "summary_after": after["summary"],
        "ledger": ledger, "duration_ms": _ms(t),
    }
