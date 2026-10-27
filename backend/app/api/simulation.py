"""Simulation endpoints - clearly labelled TEST operations.

Only predefined actions are possible. There is no shell access and no Docker
control: a real container stop/start is done by the presenter in a terminal
(`docker compose stop node2`), and is detected by the same health checks.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..blockchain import consensus
from ..database import db
from ..models.schemas import (CorruptRequest, InvalidBlockRequest, MaliciousRequest, NodeRequest,
                              TamperLedgerRequest)
from ..services import file_service, health_monitor, node_client
from ..services.auth import require_admin
from .nodes import node_summaries

router = APIRouter(prefix="/api/simulation", tags=["simulation (tests)"],
                   dependencies=[Depends(require_admin)])


def _node_call(node_id: str, path: str, json=None) -> dict:
    res = node_client.call(node_id, "POST", path, json=json)
    if not res["ok"]:
        status = res["status"] or 503
        raise HTTPException(status_code=status if status in (400, 403, 404) else 503,
                            detail=f"{node_id}: {res.get('error')}")
    return res["body"]


@router.post("/node-failure", summary="TEST: simulated application-level failure (node answers 503)")
def node_failure(req: NodeRequest):
    body = _node_call(req.node_id, "/simulation/fail")
    db.log_event("warning", "simulation", f"TEST: simulated failure activated on {req.node_id}")
    health_monitor.check_once()
    return {"mode": "simulated application-level failure", **body}


@router.post("/node-restart", summary="TEST: end a simulated failure and re-check the node")
def node_restart(req: NodeRequest):
    res = node_client.call(req.node_id, "POST", "/simulation/recover")
    if not res["ok"]:
        raise HTTPException(status_code=503, detail=(
            f"{req.node_id} is not reachable at all, so it was really stopped (not simulated). "
            f"Start it again from a terminal, e.g. `docker compose start {req.node_id}` "
            f"or `python run_local.py start-node {req.node_id}`."))
    db.log_event("info", "simulation", f"TEST: simulated failure cleared on {req.node_id}")
    health_monitor.check_once()          # triggers rejoin + ledger sync immediately
    return {"node_id": req.node_id, "simulated_failure": False,
            "node": next(n for n in node_summaries() if n["node_id"] == req.node_id)}


@router.post("/malicious-node", summary="TEST: switch malicious-simulation mode on/off for a node")
def malicious(req: MaliciousRequest):
    body = _node_call(req.node_id, "/simulation/malicious", {"enabled": req.enabled})
    db.log_event("warning" if req.enabled else "info", "simulation",
                 f"TEST: malicious simulation {'ENABLED' if req.enabled else 'disabled'} on {req.node_id}")
    health_monitor.check_once()
    return body


@router.post("/corrupt-replica", summary="TEST: tamper with ONE node's copy of a file")
def corrupt(req: CorruptRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Destructive test: set confirm=true to proceed")
    if not file_service.get_file(req.file_id):
        raise HTTPException(status_code=404, detail="File not found")
    body = _node_call(req.node_id, f"/simulation/corrupt/{req.file_id}")
    db.log_event("warning", "simulation", f"TEST: {req.node_id} modified its replica of {req.file_id[:8]}...",
                 body)
    return {**body, "note": "Trusted hash in metadata and ledger is unchanged. Run Verify to detect this."}


@router.post("/invalid-block", summary="TEST: malicious node proposes an invalid block")
def invalid_block(req: InvalidBlockRequest):
    built = _node_call(req.node_id, "/simulation/propose-invalid",
                       {"attack": req.attack, "file_id": req.file_id})
    proposal = consensus.propose_prebuilt(built["block"], proposer=req.node_id, kind="simulation")
    db.log_event("warning", "simulation",
                 f"TEST: {req.node_id} proposed invalid block ({req.attack}) -> {proposal['outcome']}")
    return {"attack": req.attack, "description": built["description"], "proposal": proposal}


@router.post("/tamper-ledger", summary="TEST: edit a past block in one node's local ledger file")
def tamper_ledger(req: TamperLedgerRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Destructive test: set confirm=true to proceed")
    body = _node_call(req.node_id, "/simulation/tamper-ledger")
    db.log_event("warning", "simulation", f"TEST: {req.node_id} edited its local ledger copy", body)
    return {**body, "note": "Run Validate Ledger: the recalculated hash of that block no longer matches."}
