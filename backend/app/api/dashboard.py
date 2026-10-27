"""Overview endpoints: service health, dashboard metrics and the event log."""
import json

from fastapi import APIRouter, Depends

from shared.blockcore import NODE_IDS, QUORUM

from ..blockchain import ledger_view
from ..database import db
from ..services.auth import require_user
from ..services.auth_service import visible_file_ids
from .nodes import node_summaries

public_router = APIRouter(prefix="/api", tags=["overview"])
router = APIRouter(prefix="/api", tags=["overview"], dependencies=[Depends(require_user)])


@public_router.get("/health", summary="Coordinator health")
def health():
    nodes = node_summaries()
    online = sum(1 for n in nodes if n["online"])
    return {"service": "blockstore5-backend", "status": "ok", "nodes_online": online,
            "nodes_total": len(NODE_IDS), "write_quorum_available": online >= QUORUM}


@router.get("/dashboard", summary="Numbers for the overview page (all computed from live state)")
def dashboard(user: dict = Depends(require_user)):
    nodes = node_summaries()
    view = ledger_view.committed_view()
    file_ids = visible_file_ids(user["organization_id"])
    if file_ids:
        marks = ",".join("?" for _ in file_ids)
        params = tuple(file_ids)
        files = db.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM files WHERE file_id IN ({marks})",
                       params)
        rep = {r["status"]: r["n"] for r in db.rows(
            f"SELECT status, COUNT(*) AS n FROM replicas WHERE file_id IN ({marks}) GROUP BY status", params)}
    else:
        files, rep = {"n": 0, "bytes": 0}, {}
    recoveries = db.rows("""SELECT ts, level, message FROM events
                           WHERE category='recovery' AND organization_id=? ORDER BY id DESC LIMIT 5""",
                         (user["organization_id"],))
    online = sum(1 for n in nodes if n["online"])
    return {
        "total_files": files["n"],
        "total_bytes": files["bytes"],
        "total_nodes": len(NODE_IDS),
        "online_nodes": online,
        "offline_nodes": len(NODE_IDS) - online,
        "malicious_nodes": [n["node_id"] for n in nodes if n["malicious_simulation"]],
        "verified_replicas": rep.get("match", 0),
        "integrity_failures": rep.get("mismatch", 0),
        "missing_replicas": rep.get("missing", 0) + rep.get("unavailable", 0),
        "latest_recoveries": recoveries,
        "blockchain": {
            "status": ("valid" if view["all_nodes_agree"] else
                       "valid (some nodes inconsistent)" if view["has_quorum"] else "no quorum"),
            "has_quorum": view["has_quorum"],
            "height": view["committed_height"],
            "head_hash": view["committed_head"],
            "agreeing_nodes": view["agreeing_nodes"],
            "node_states": {nid: v["state"] for nid, v in view["nodes"].items()},
        },
        "nodes": nodes,
    }


@router.get("/events", summary="Organization-scoped event log (newest first)")
def events(limit: int = 100, category: str | None = None, user: dict = Depends(require_user)):
    limit = max(1, min(limit, 500))
    if category:
        result = db.rows("""SELECT * FROM events WHERE organization_id=? AND category=?
                            ORDER BY id DESC LIMIT ?""",
                         (user["organization_id"], category, limit))
    else:
        result = db.rows("SELECT * FROM events WHERE organization_id=? ORDER BY id DESC LIMIT ?",
                         (user["organization_id"], limit))
    for e in result:
        e["details"] = json.loads(e["details"]) if e["details"] else None
    return result
