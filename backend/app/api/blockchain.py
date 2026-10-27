"""Blockchain explorer, validation, proposals and ledger repair."""
from fastapi import APIRouter, Depends, HTTPException

from shared.blockcore import NODE_IDS, utc_now

from ..blockchain import consensus, ledger_view
from ..database import db
from ..models.schemas import ProposeRequest
from ..services import health_monitor
from ..services.auth import require_admin, require_user
from ..services.auth_service import visible_file_ids

router = APIRouter(prefix="/api/blockchain", tags=["blockchain"], dependencies=[Depends(require_user)])


def _visible_proposal(proposal: dict, visible_ids: set[str]) -> dict:
    if not proposal:
        return proposal
    block = proposal["block"]
    private = any(tx.get("file_id") and tx["file_id"] not in visible_ids
                  for tx in block.get("transactions", []))
    block["transactions"] = [tx for tx in block.get("transactions", [])
                             if not tx.get("file_id") or tx["file_id"] in visible_ids]
    if private:
        proposal["reason"] = "Proposal includes transactions not visible to this organization."
        for vote in proposal["votes"]:
            vote["reason"] = "Details hidden for organization privacy."
    return proposal


@router.get("/blocks", summary="The committed ledger (held by at least 3 of 5 nodes)")
def blocks(user: dict = Depends(require_user)):
    view = ledger_view.committed_view()
    visible_ids = visible_file_ids(user["organization_id"])
    blocks = []
    for block in reversed(view["committed_chain"] or []):
        blocks.append({**block, "transactions": [
            tx for tx in block["transactions"]
            if not tx.get("file_id") or tx["file_id"] in visible_ids
        ]})
    return {
        "has_quorum": view["has_quorum"],
        "committed_height": view["committed_height"],
        "committed_head": view["committed_head"],
        "agreeing_nodes": view["agreeing_nodes"],
        "blocks": blocks,   # newest first; private organization transactions are redacted
        "nodes": view["nodes"],
    }


@router.get("/validate", summary="Validate all five ledger copies and check agreement")
def validate():
    view = ledger_view.committed_view()
    return {
        "checked_at": utc_now(),
        "has_quorum": view["has_quorum"],
        "committed_height": view["committed_height"],
        "committed_head": view["committed_head"],
        "all_nodes_agree": view["all_nodes_agree"],
        "agreeing_nodes": view["agreeing_nodes"],
        "nodes": view["nodes"],
        "status": ("valid" if view["all_nodes_agree"] else
                   "valid with inconsistent nodes" if view["has_quorum"] else "no quorum"),
    }


@router.post("/propose", summary="Propose one transaction; nodes validate and vote")
def propose(req: ProposeRequest):
    tx = dict(req.transaction)
    tx.setdefault("timestamp", utc_now())
    try:
        return consensus.propose_transactions([tx], kind="manual")
    except consensus.NoQuorum as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/proposals", summary="Recent proposals")
def proposals(limit: int = 20, user: dict = Depends(require_user)):
    ids = db.rows("SELECT proposal_id FROM proposals ORDER BY created_at DESC LIMIT ?", (min(limit, 100),))
    visible_ids = visible_file_ids(user["organization_id"])
    return [_visible_proposal(consensus.get_proposal(r["proposal_id"]), visible_ids) for r in ids]


@router.get("/proposals/{proposal_id}", summary="One proposal with every vote")
def proposal(proposal_id: str, user: dict = Depends(require_user)):
    p = consensus.get_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _visible_proposal(p, visible_file_ids(user["organization_id"]))


@router.post("/repair", summary="Re-sync nodes whose ledger copy is behind, invalid or diverged")
def repair(user: dict = Depends(require_admin)):
    view = ledger_view.committed_view()
    if not view["has_quorum"]:
        raise HTTPException(status_code=503, detail="No quorum ledger to repair from")
    results = [health_monitor.sync_node(nid, view, allow_replace=True)
               for nid in NODE_IDS if view["nodes"][nid]["state"] in ("behind", "invalid", "diverged")]
    db.log_event("info", "consensus", f"Ledger repair: {len(results)} node(s) re-synchronised", {"results": results})
    return {"repaired": results, "after": validate()}
