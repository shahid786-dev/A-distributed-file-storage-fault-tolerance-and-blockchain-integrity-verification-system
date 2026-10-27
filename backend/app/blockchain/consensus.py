"""
Simplified, coordinator-based majority voting (educational - NOT production BFT).

Round for one block:
  1. PROPOSE  The coordinator (or, in a simulation, a node) produces a candidate block.
  2. VOTE     The block is sent to all five nodes over HTTP. Each node checks it against
              its own ledger copy and returns a signed ACCEPT/REJECT vote.
  3. TALLY    The coordinator counts only votes that (a) come from a registered node id,
              (b) carry a valid HMAC signature for that node, (c) refer to this exact block
              hash, and (d) are the first vote from that node. Duplicates are discarded.
  4. COMMIT   With >= 3 valid ACCEPT votes the block is sent to every node, and each node
              validates it AGAIN before appending it. Otherwise nothing changes.

Known simplifications (documented in docs/limitations.md): the coordinator is a single
point of failure, only one proposal runs at a time (a lock), and there is no protection
against a malicious coordinator, network partitions or equivocation.
"""
import json
import threading
import uuid

from shared.blockcore import NODE_IDS, QUORUM, make_block, verify_vote_signature

from ..config import NODE_SECRETS
from ..database import db
from ..services import node_client
from . import ledger_view

_round_lock = threading.Lock()   # one consensus round at a time


class NoQuorum(Exception):
    """Fewer than 3 nodes agree on the committed ledger, so no block can be proposed."""


def tally_votes(votes: list, proposal_id: str, block_hash: str) -> dict:
    """Count votes safely. Pure function - unit-tested in tests/test_consensus_unit.py."""
    seen, counted, discarded = set(), [], []
    for vote in votes:
        nid = vote.get("node_id")
        if nid not in NODE_IDS:
            discarded.append({**vote, "discard_reason": "unregistered node identity"})
        elif nid in seen:
            discarded.append({**vote, "discard_reason": "duplicate vote from this node"})
        elif vote.get("block_hash") != block_hash:
            discarded.append({**vote, "discard_reason": "vote is for a different block"})
        elif not verify_vote_signature(NODE_SECRETS[nid], vote, proposal_id):
            discarded.append({**vote, "discard_reason": "invalid signature"})
        elif vote.get("decision") not in ("accept", "reject"):
            discarded.append({**vote, "discard_reason": "decision must be accept or reject"})
        else:
            seen.add(nid)
            counted.append(vote)
    accepts = sum(1 for v in counted if v["decision"] == "accept")
    rejects = sum(1 for v in counted if v["decision"] == "reject")
    return {"counted": counted, "discarded": discarded, "accept": accepts, "reject": rejects,
            "committed": accepts >= QUORUM}


def current_head() -> dict:
    view = ledger_view.committed_view()
    if not view["has_quorum"]:
        raise NoQuorum("fewer than 3 nodes hold the same valid ledger - cannot propose")
    return view["committed_chain"][-1]


def _heads() -> dict:
    res = node_client.call_all("GET", "/health")
    return {nid: (r["body"]["ledger_head_hash"] if r["ok"] else None) for nid, r in res.items()}


def run_round(block: dict, proposer: str, kind: str) -> dict:
    """Collect votes for a block, tally them, and commit if the quorum is reached."""
    proposal_id = uuid.uuid4().hex
    heads_before = _heads()

    # --- VOTE: ask every node, in parallel, over HTTP ---
    responses = node_client.call_all("POST", "/consensus/vote",
                                     json={"proposal_id": proposal_id, "block": block})
    votes, no_response = [], []
    for nid, res in responses.items():
        if res["ok"]:
            votes.append(res["body"])
        else:
            no_response.append({"node_id": nid, "decision": "no response", "reason": res.get("error")})

    tally = tally_votes(votes, proposal_id, block.get("hash", ""))

    # --- COMMIT only with quorum ---
    commit_results = {}
    if tally["committed"]:
        responses = node_client.call_all("POST", "/consensus/commit", json={
            "proposal_id": proposal_id, "block": block, "accept_votes": tally["accept"]})
        commit_results = {nid: ({"ok": True} if r["ok"] else {"ok": False, "error": r.get("error")})
                          for nid, r in responses.items()}
        outcome, reason = "committed", f"{tally['accept']} of 5 valid votes accepted (quorum is {QUORUM})"
    else:
        reject_reasons = [v["reason"] for v in tally["counted"] if v["decision"] == "reject"]
        outcome = "rejected"
        reason = (reject_reasons[0] if reject_reasons else "not enough nodes responded") + \
                 f" - only {tally['accept']} accept vote(s), quorum is {QUORUM}"

    heads_after = _heads()
    all_votes = tally["counted"] + no_response + tally["discarded"]
    db.execute("""INSERT INTO proposals (proposal_id, created_at, proposer, kind, block, votes,
                  accept_count, reject_count, outcome, reason, commit_results, heads_before, heads_after)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (proposal_id, db.now(), proposer, kind, json.dumps(block), json.dumps(all_votes),
                tally["accept"], tally["reject"], outcome, reason, json.dumps(commit_results),
                json.dumps(heads_before), json.dumps(heads_after)))
    db.log_event("success" if outcome == "committed" else "warning", "consensus",
                 f"Block #{block.get('index')} from {proposer} {outcome} ({tally['accept']}/5 accept)",
                 {"proposal_id": proposal_id, "types": [t.get("type") for t in block.get("transactions", [])]})
    return get_proposal(proposal_id)


def propose_transactions(transactions: list, kind: str = "normal") -> dict:
    """Normal path: the coordinator builds the next block on the committed head and runs a round."""
    with _round_lock:
        head = current_head()
        block = make_block(head["index"] + 1, head["hash"], transactions, "coordinator")
        return run_round(block, "coordinator", kind)


def propose_prebuilt(block: dict, proposer: str, kind: str = "simulation") -> dict:
    """Simulation path: a block built by a (malicious) node is put to the vote unchanged."""
    with _round_lock:
        return run_round(block, proposer, kind)


def get_proposal(proposal_id: str) -> dict | None:
    row = db.one("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
    if not row:
        return None
    for key in ("block", "votes", "commit_results", "heads_before", "heads_after"):
        row[key] = json.loads(row[key]) if row[key] else None
    row["ledger_unchanged"] = row["heads_before"] == row["heads_after"]
    return row
