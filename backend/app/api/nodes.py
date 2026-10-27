"""Node monitoring endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from shared.blockcore import NODE_IDS

from ..config import NODE_URLS
from ..database import db
from ..services import health_monitor, node_client
from ..services.auth import require_user
from ..services.auth_service import visible_file_ids

router = APIRouter(prefix="/api/nodes", tags=["nodes"], dependencies=[Depends(require_user)])


def _check_node(node_id: str):
    if node_id not in NODE_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown node '{node_id}'. Registered: {NODE_IDS}")


def node_summaries() -> list:
    snap = health_monitor.snapshot()
    stats = {r["node_id"]: r for r in db.rows("SELECT * FROM health_stats")}
    bad = {r["node_id"]: r["n"] for r in
           db.rows("SELECT node_id, COUNT(*) AS n FROM replicas WHERE status='mismatch' GROUP BY node_id")}
    out = []
    for nid in NODE_IDS:
        s, h = snap[nid], snap[nid]["health"] or {}
        out.append({
            "node_id": nid,
            "url": NODE_URLS[nid],
            "online": bool(s["online"]),
            "last_checked": s["last_checked"],
            "last_error": s["last_error"],
            "file_count": h.get("file_count"),
            "ledger_height": h.get("ledger_height"),
            "ledger_head_hash": h.get("ledger_head_hash"),
            "malicious_simulation": h.get("malicious_simulation", False),
            "uptime_seconds": h.get("uptime_seconds"),
            "corrupted_replicas": bad.get(nid, 0),
            "integrity_status": "issues found" if bad.get(nid) else "ok",
            "health_checks_ok": stats.get(nid, {}).get("ok", 0),
            "health_checks_failed": stats.get(nid, {}).get("failed", 0),
        })
    return out


@router.get("", summary="Health and state of all five nodes")
def list_nodes():
    health_monitor.check_once()
    return node_summaries()


@router.get("/{node_id}/health", summary="Live health check of one node")
def node_health(node_id: str):
    _check_node(node_id)
    res = node_client.health(node_id)
    return {"node_id": node_id, "online": res["ok"], "health": res.get("body") if res["ok"] else None,
            "error": res.get("error")}


@router.get("/{node_id}/files", summary="Files stored on one node, compared with trusted hashes")
def node_files(node_id: str, user: dict = Depends(require_user)):
    _check_node(node_id)
    res = node_client.call(node_id, "GET", "/files")
    if not res["ok"]:
        raise HTTPException(status_code=503, detail=f"{node_id} unavailable: {res.get('error')}")
    visible_ids = visible_file_ids(user["organization_id"])
    trusted = {r["file_id"]: r for r in db.rows("SELECT file_id, name, sha256 FROM files")}
    files = []
    for item in res["body"]["files"]:
        if item["file_id"] not in visible_ids:
            continue
        t = trusted.get(item["file_id"])
        files.append({**item, "name": t["name"] if t else "(unknown)",
                      "trusted_hash": t["sha256"] if t else None,
                      "hash_match": bool(t) and item["sha256"] == t["sha256"]})
    return {"node_id": node_id, "files": files}


@router.get("/{node_id}/ledger", summary="One node's ledger copy")
def node_ledger(node_id: str, user: dict = Depends(require_user)):
    _check_node(node_id)
    res = node_client.ledger(node_id)
    if not res["ok"]:
        raise HTTPException(status_code=503, detail=f"{node_id} unavailable: {res.get('error')}")
    visible_ids = visible_file_ids(user["organization_id"])
    body = res["body"]
    body["chain"] = [
        {**block, "transactions": [tx for tx in block.get("transactions", [])
                                   if not tx.get("file_id") or tx["file_id"] in visible_ids]}
        for block in body["chain"]
    ]
    return body
