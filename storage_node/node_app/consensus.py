"""How this node votes on proposed blocks, and (test mode only) how a malicious
node builds invalid proposals.

Honest node: re-checks the proposed block against ITS OWN committed ledger copy
(sequential index, previous hash, recalculated block hash, transaction rules) and
votes ACCEPT only if everything is valid.

Malicious node (simulation): votes ACCEPT on anything without checking. It can also
build deliberately invalid proposals so we can watch the honest majority reject them.
"""
import secrets

from shared.blockcore import (compute_block_hash, known_files, make_block, sign_vote,
                              utc_now, validate_new_block)

from . import health, ledger
from .config import NODE_ID, NODE_SECRET


def vote(proposal_id: str, block: dict) -> dict:
    chain = ledger.get_chain()
    if health.get("malicious"):
        decision, reason = "accept", "malicious node: accepted without validating"
    else:
        problem = validate_new_block(block, chain)
        decision, reason = ("reject", problem) if problem else ("accept", "block is valid")
    block_hash = str(block.get("hash", ""))
    return {
        "proposal_id": proposal_id,
        "node_id": NODE_ID,
        "block_hash": block_hash,
        "decision": decision,
        "reason": reason,
        "voter_ledger_height": len(chain),
        "signature": sign_vote(NODE_SECRET, proposal_id, NODE_ID, block_hash, decision),
    }


ATTACKS = {
    "wrong_previous_hash": "Block points to a previous hash that is not the committed head",
    "bad_block_hash": "Block content was changed after its hash was calculated",
    "overwrite_trusted_hash": "Well-formed block that tries to re-register an existing file with a different hash",
}


def build_invalid_block(attack: str, file_id: str | None = None) -> dict:
    """TEST ONLY - build one of three kinds of invalid block."""
    chain = ledger.get_chain()
    head = chain[-1]
    now = utc_now()

    if attack == "wrong_previous_hash":
        tx = {"type": "NODE_FAILURE", "node_id": "node1", "detail": "false accusation by malicious node",
              "timestamp": now}
        return make_block(head["index"] + 1, secrets.token_hex(32), [tx], NODE_ID)

    if attack == "bad_block_hash":
        tx = {"type": "NODE_REJOINED", "node_id": NODE_ID, "timestamp": now}
        block = make_block(head["index"] + 1, head["hash"], [tx], NODE_ID)
        # Change content AFTER hashing -> stored hash no longer matches
        block["transactions"][0]["node_id"] = "node1"
        return block

    if attack == "overwrite_trusted_hash":
        files = known_files(chain)
        if not files:
            raise ValueError("no committed files yet - upload a file first")
        target = file_id if file_id in files else next(iter(files))
        tx = {"type": "FILE_UPLOADED", "file_id": target, "file_name": "replaced-by-attacker.txt",
              "size": 1, "sha256": "e" * 64, "timestamp": now}
        block = make_block(head["index"] + 1, head["hash"], [tx], NODE_ID)
        assert block["hash"] == compute_block_hash(block)
        return block

    raise ValueError(f"unknown attack '{attack}'. Choose one of {list(ATTACKS)}")
