"""End-to-end tests against a live cluster of five real node processes + the backend.
Tests run in file order and build on each other (upload -> attack -> recover ...)."""
import hashlib
import os

import pytest

from conftest import BASE, NODE_PORTS, http, wait_for

pytestmark = pytest.mark.usefixtures("cluster")
STATE = {}
TOKENS = {}
CONTENT = b"BlockStore-5 integration test document\n" * 50
TRUSTED = hashlib.sha256(CONTENT).hexdigest()


def _token(organization):
    if organization not in TOKENS:
        credentials = {
            "manufacturer": ("manufacturer", "manufacturer@test.invalid", "Test-Password-M-2026"),
            "logistics": ("logistics", "logistics@test.invalid", "Test-Password-L-2026"),
            "inspection": ("inspection", "inspection@test.invalid", "Test-Password-I-2026"),
            "distributor": ("distributor", "distributor@test.invalid", "Test-Password-D-2026"),
            "distributor_member": ("distributor", "member@test.invalid", "Test-Password-Member-2026"),
        }
        org_id, email, password = credentials[organization]
        response = http.post(BASE + "/auth/login",
                             json={"email": email, "password": password, "organization": org_id},
                             timeout=30)
        assert response.status_code == 200, response.text
        TOKENS[organization] = response.json()["access_token"]
    return TOKENS[organization]


def api(method, path, organization="manufacturer", **kw):
    headers = dict(kw.pop("headers", {}))
    headers.setdefault("Authorization", f"Bearer {_token(organization)}")
    return http.request(method, BASE + path, headers=headers, timeout=30, **kw)


def node(nid, path):
    return http.get(f"http://127.0.0.1:{NODE_PORTS[nid]}{path}",
                    headers={"X-Control-Token": os.environ.get("CONTROL_TOKEN", "blockstore5-demo-token")},
                    timeout=5)


def heads():
    return {nid: node(nid, "/health").json()["ledger_head_hash"] for nid in NODE_PORTS}


def all_online():
    return all(n["online"] for n in api("GET", "/nodes").json())


# --- 1-3 upload, replication, trusted hash ---------------------------------------------------
def test_01_upload_succeeds():
    assert wait_for(all_online)
    r = api("POST", "/files/upload", files={"file": ("report.txt", CONTENT, "text/plain")})
    assert r.status_code == 200, r.text
    STATE["file"] = r.json()


def test_01a_organization_login_isolation_and_sharing():
    file_id = STATE["file"]["file_id"]
    assert http.get(BASE + "/files", timeout=5).status_code == 401
    distributor_files = api("GET", "/files", organization="distributor").json()
    assert file_id not in {f["file_id"] for f in distributor_files}
    assert api("GET", f"/files/{file_id}", organization="distributor").status_code == 404

    shared = api("POST", f"/files/{file_id}/shares",
                 json={"organization": "distributor", "permission": "read"})
    assert shared.status_code == 200, shared.text
    assert api("GET", f"/files/{file_id}", organization="distributor").status_code == 200
    assert api("GET", f"/files/{file_id}/download", organization="distributor").status_code == 200
    assert api("POST", f"/files/{file_id}/recover", organization="distributor").status_code == 404

    revoked = api("DELETE", f"/files/{file_id}/shares/distributor")
    assert revoked.status_code == 200, revoked.text
    assert api("GET", f"/files/{file_id}", organization="distributor").status_code == 404
    private_blocks = api("GET", "/blockchain/blocks", organization="distributor").json()["blocks"]
    assert all(tx.get("file_id") != file_id for block in private_blocks for tx in block["transactions"])

    member_upload = api(
        "POST", "/files/upload", organization="distributor_member",
        files={"file": ("member-private.txt", b"member-owned test document", "text/plain")})
    assert member_upload.status_code == 200, member_upload.text
    member_id = member_upload.json()["file_id"]
    assert api("POST", f"/files/{member_id}/shares", organization="distributor_member",
               json={"organization": "inspection"}).status_code == 403
    assert api("POST", f"/files/{member_id}/recover", organization="distributor_member").status_code == 403
    assert http.get(f"http://127.0.0.1:{NODE_PORTS['node1']}/files/{file_id}", timeout=5).status_code == 401


def test_01b_immutable_document_versions_and_stale_parent_conflict():
    first_response = api("POST", "/files/upload",
                         files={"file": ("release.txt", b"version one", "text/plain")})
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    second_response = api(
        "POST", f"/files/{first['file_id']}/versions?expected_version=1",
        files={"file": ("release.txt", b"version two", "text/plain")},
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["document_id"] == first["document_id"] == first["file_id"]
    assert second["version_number"] == 2
    assert second["previous_file_id"] == first["file_id"]
    assert second["sha256"] == hashlib.sha256(b"version two").hexdigest()

    stale = api(
        "POST", f"/files/{first['file_id']}/versions?expected_version=1",
        files={"file": ("release.txt", b"stale competing version", "text/plain")},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["latest_file_id"] == second["file_id"]
    assert stale.json()["detail"]["latest_version"] == 2
    assert api("GET", "/files").json()
    file_rows = {row["file_id"]: row for row in api("GET", "/files").json()}
    assert file_rows[first["file_id"]]["is_latest"] == 0
    assert file_rows[second["file_id"]]["is_latest"] == 1

    block_rows = api("GET", "/blockchain/blocks").json()["blocks"]
    version_records = [tx for block in block_rows for tx in block["transactions"]
                       if tx["type"] == "FILE_VERSION_CREATED" and tx["file_id"] == second["file_id"]]
    assert len(version_records) == 1
    assert version_records[0]["previous_file_id"] == first["file_id"]
    assert api("POST", f"/files/{second['file_id']}/shares",
               json={"organization": "distributor", "permission": "read"}).status_code == 200
    assert api("GET", f"/files/{first['file_id']}", organization="distributor").status_code == 200
    assert api("GET", f"/files/{second['file_id']}", organization="distributor").status_code == 200
    assert api("DELETE", f"/files/{first['file_id']}/shares/distributor").status_code == 200
    assert api("GET", f"/files/{first['file_id']}", organization="distributor").status_code == 404
    assert api("GET", f"/files/{second['file_id']}", organization="distributor").status_code == 404


def test_02_file_replicated_to_all_five_nodes():
    f = STATE["file"]
    assert f["healthy_replicas"] == 5 and f["fully_replicated"]
    for nid in NODE_PORTS:                         # ask each node directly, not the backend
        body = node(nid, f"/files/{f['file_id']}").content
        assert hashlib.sha256(body).hexdigest() == TRUSTED


def test_03_original_hash_recorded_in_metadata_and_ledger():
    f = STATE["file"]
    assert f["sha256"] == TRUSTED
    assert api("GET", f"/files/{f['file_id']}").json()["sha256"] == TRUSTED
    blocks = api("GET", "/blockchain/blocks").json()["blocks"]
    uploads = [tx for b in blocks for tx in b["transactions"] if tx["type"] == "FILE_UPLOADED"]
    assert any(tx["file_id"] == f["file_id"] and tx["sha256"] == TRUSTED for tx in uploads)


def test_rejects_bad_upload_types():
    assert api("POST", "/files/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert api("POST", "/files/upload", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 400


# --- 4-6, 9 integrity -------------------------------------------------------------------------
def test_04_healthy_file_passes_verification():
    r = api("POST", f"/files/{STATE['file']['file_id']}/verify").json()
    assert r["summary"]["healthy"] == 5 and r["summary"]["mismatched"] == 0


def test_corruption_requires_malicious_mode_and_confirmation():
    fid = STATE["file"]["file_id"]
    assert api("POST", "/simulation/corrupt-replica", json={"node_id": "node3", "file_id": fid, "confirm": False}).status_code == 400
    assert api("POST", "/simulation/corrupt-replica", json={"node_id": "node3", "file_id": fid, "confirm": True}).status_code == 403


def test_05_modified_replica_fails_verification():
    fid = STATE["file"]["file_id"]
    assert api("POST", "/simulation/malicious-node", json={"node_id": "node3", "enabled": True}).ok
    assert api("POST", "/simulation/corrupt-replica", json={"node_id": "node3", "file_id": fid, "confirm": True}).ok
    r = api("POST", f"/files/{fid}/verify").json()
    row = {x["node_id"]: x for x in r["replicas"]}
    assert row["node3"]["status"] == "mismatch" and not row["node3"]["hash_match"]
    # The malicious node lies about its hash; the coordinator is not fooled
    assert row["node3"]["reported_hash"] == TRUSTED and row["node3"]["node_reported_falsely"]
    STATE["verify"] = r


def test_06_four_unchanged_replicas_remain_valid():
    rows = {x["node_id"]: x for x in STATE["verify"]["replicas"]}
    assert [n for n, x in rows.items() if x["status"] == "match"] == ["node1", "node2", "node4", "node5"]
    assert api("GET", f"/files/{STATE['file']['file_id']}").json()["sha256"] == TRUSTED   # trusted hash untouched


def test_09_corrupted_replica_never_returned():
    # Make node3 the ONLY copy holder that is reachable: stop the honest copies' service by simulation
    fid = STATE["file"]["file_id"]
    for nid in ("node1", "node2", "node4", "node5"):
        assert api("POST", "/simulation/node-failure", json={"node_id": nid}).ok
    r = api("GET", f"/files/{fid}/download")
    assert r.status_code == 503
    assert "No verified replica" in r.text
    rec = api("POST", f"/files/{fid}/recover")
    assert rec.status_code == 503 and not rec.json()["ok"]
    for nid in ("node1", "node2", "node4", "node5"):
        assert api("POST", "/simulation/node-restart", json={"node_id": nid}).ok
    assert wait_for(all_online)


def test_recover_repairs_the_tampered_replica():
    fid = STATE["file"]["file_id"]
    r = api("POST", f"/files/{fid}/recover").json()
    assert r["ok"] and r["source_node"] in ("node1", "node2", "node4", "node5")
    assert r["repaired_nodes"] == ["node3"] and r["summary_after"]["healthy"] == 5
    assert hashlib.sha256(node("node3", f"/files/{fid}").content).hexdigest() == TRUSTED


# --- 15 invalid proposals, 14 convergence -----------------------------------------------------
@pytest.mark.parametrize("attack", ["wrong_previous_hash", "bad_block_hash", "overwrite_trusted_hash"])
def test_15_invalid_proposal_leaves_ledger_unchanged(attack):
    before = heads()
    r = api("POST", "/simulation/invalid-block",
            json={"node_id": "node3", "attack": attack, "file_id": STATE["file"]["file_id"]}).json()
    p = r["proposal"]
    assert p["outcome"] == "rejected" and p["accept_count"] == 1
    votes = {v["node_id"]: v["decision"] for v in p["votes"]}
    assert votes == {"node1": "reject", "node2": "reject", "node3": "accept", "node4": "reject", "node5": "reject"}
    assert p["ledger_unchanged"] and heads() == before


def test_invalid_manual_transaction_rejected_by_honest_nodes():
    p = api("POST", "/blockchain/propose", json={"transaction": {"type": "MINT_COINS", "amount": 1}}).json()
    assert p["outcome"] == "rejected"


def test_14_ledgers_converge_after_valid_commit():
    assert api("POST", "/simulation/malicious-node", json={"node_id": "node3", "enabled": False}).ok
    before = api("GET", "/blockchain/validate").json()["committed_height"]
    p = api("POST", "/blockchain/propose", json={"transaction": {"type": "NODE_REJOINED", "node_id": "node1"}}).json()
    assert p["outcome"] == "committed" and p["accept_count"] == 5
    v = api("GET", "/blockchain/validate").json()
    assert v["all_nodes_agree"] and v["committed_height"] == before + 1
    assert len(set(heads().values())) == 1


def test_tampered_local_ledger_detected_and_repaired():
    api("POST", "/simulation/malicious-node", json={"node_id": "node5", "enabled": True})
    assert api("POST", "/simulation/tamper-ledger", json={"node_id": "node5", "confirm": True}).json()["ok"]
    v = api("GET", "/blockchain/validate").json()
    assert v["nodes"]["node5"]["state"] == "invalid" and v["has_quorum"]
    assert api("POST", "/blockchain/repair").json()["after"]["all_nodes_agree"]
    api("POST", "/simulation/malicious-node", json={"node_id": "node5", "enabled": False})


# --- 7, 8, 16 real node failure, recovery and rejoin ------------------------------------------
def test_07_offline_node_reported_unavailable(cluster):
    fid = STATE["file"]["file_id"]
    assert api("POST", "/simulation/malicious-node", json={"node_id": "node2", "enabled": True}).ok
    assert api("POST", "/simulation/corrupt-replica",
               json={"node_id": "node2", "file_id": fid, "confirm": True}).ok
    assert api("POST", "/simulation/malicious-node", json={"node_id": "node2", "enabled": False}).ok
    cluster.stop_node("node2")                  # really terminate the process
    n2 = wait_for(lambda: next((n for n in api("GET", "/nodes").json()
                                if n["node_id"] == "node2" and not n["online"]), None), 10)
    assert n2 and n2["last_error"]
    r = api("GET", f"/files/{STATE['file']['file_id']}/replicas").json()
    assert {x["node_id"]: x["status"] for x in r["replicas"]}["node2"] == "unavailable"
    # The rest of the system still works: a new upload reaches the 4 healthy nodes
    up = api("POST", "/files/upload", files={"file": ("while-down.txt", b"written while node2 was down", "text/plain")}).json()
    assert up["healthy_replicas"] == 4 and up["replicas"][1]["hash_match"] is False
    STATE["while_down"] = up


def test_08_file_recovered_from_healthy_replica():
    r = api("GET", f"/files/{STATE['file']['file_id']}/download")
    assert r.status_code == 200 and r.content == CONTENT
    assert r.headers["X-BlockStore-Source-Node"] != "node2"
    assert hashlib.sha256(r.content).hexdigest() == r.headers["X-BlockStore-Verified-SHA256"] == TRUSTED


def test_16_restarted_node_synchronises_ledger(cluster):
    committed = api("GET", "/blockchain/validate").json()["committed_height"]
    cluster.start_node("node2")                 # fresh process, same data folder
    def synced():
        api("GET", "/nodes")
        v = api("GET", "/blockchain/validate").json()
        return v if v["nodes"]["node2"]["state"] == "consistent" else None
    v = wait_for(synced, 15)
    assert v and v["nodes"]["node2"]["height"] >= committed
    def repaired():
        targets = (STATE["file"]["file_id"], STATE["while_down"]["file_id"])
        for fid in targets:
            details = api("GET", f"/files/{fid}").json()
            replica = next(r for r in details["replicas"] if r["node_id"] == "node2")
            if replica["status"] != "match":
                return False
        return True
    assert wait_for(repaired, 20), "node2 did not automatically repair its corrupt/missing replicas"
    # NODE_FAILURE and NODE_REJOINED were recorded on the ledger
    types = [tx["type"] for b in api("GET", "/blockchain/blocks").json()["blocks"] for tx in b["transactions"]]
    assert "NODE_FAILURE" in types and "NODE_REJOINED" in types
    # Explicit recovery after automatic repair is idempotent.
    rec = api("POST", f"/files/{STATE['while_down']['file_id']}/recover").json()
    assert rec["repaired_nodes"] == [] and rec["summary_after"]["healthy"] == 5


def test_api_validates_node_ids_and_file_ids():
    assert api("POST", "/simulation/malicious-node", json={"node_id": "node9", "enabled": True}).status_code == 422
    assert api("GET", "/files/not-a-valid-id").status_code == 422
    assert api("GET", "/files/" + "0" * 32).status_code == 404
    assert api("GET", "/nodes/node7/health").status_code == 404
