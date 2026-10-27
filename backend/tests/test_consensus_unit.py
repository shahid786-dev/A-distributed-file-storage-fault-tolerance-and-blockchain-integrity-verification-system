"""Unit tests for vote counting (no network needed)."""
from shared.blockcore import sign_vote

from app.blockchain.consensus import tally_votes
from app.config import NODE_SECRETS

PID, BH = "proposal-0001", "d" * 64


def vote(node_id, decision="accept", secret=None, block_hash=BH):
    return {"node_id": node_id, "block_hash": block_hash, "decision": decision, "reason": "test",
            "signature": sign_vote(secret or NODE_SECRETS.get(node_id, "x"), PID, node_id, block_hash, decision)}


def test_three_valid_accepts_reach_quorum():
    t = tally_votes([vote("node1"), vote("node2"), vote("node3"), vote("node4", "reject")], PID, BH)
    assert t["accept"] == 3 and t["committed"]


def test_proposal_without_quorum_is_not_committed():       # requirement 12
    t = tally_votes([vote("node1"), vote("node2"), vote("node3", "reject"), vote("node4", "reject")], PID, BH)
    assert t["accept"] == 2 and not t["committed"]


def test_duplicate_votes_are_rejected():                    # requirement 13
    t = tally_votes([vote("node3"), vote("node3"), vote("node3"), vote("node1")], PID, BH)
    assert t["accept"] == 2 and not t["committed"]
    assert sum(1 for d in t["discarded"] if d["discard_reason"].startswith("duplicate")) == 2


def test_unregistered_identity_is_ignored():
    t = tally_votes([vote("node1"), vote("node2"), vote("node99")], PID, BH)
    assert t["accept"] == 2 and t["discarded"][0]["discard_reason"] == "unregistered node identity"


def test_forged_signature_is_ignored():
    # Someone without node4's key tries to vote on its behalf
    t = tally_votes([vote("node1"), vote("node2"), vote("node4", secret="guessed-key")], PID, BH)
    assert t["accept"] == 2 and t["discarded"][0]["discard_reason"] == "invalid signature"


def test_vote_for_a_different_block_is_ignored():
    t = tally_votes([vote("node1"), vote("node2"), vote("node3", block_hash="e" * 64)], PID, BH)
    assert t["accept"] == 2 and not t["committed"]
