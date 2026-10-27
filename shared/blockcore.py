"""
blockcore.py - the small educational blockchain shared by the backend and the nodes.

Both the coordinator (backend) and every storage node import this one file, so they
compute block hashes and validate transactions in exactly the same way.

Key ideas (easy to explain in a viva):
  * A block = index + timestamp + previous_hash + transactions + proposer.
  * block_hash = SHA-256 of the block's fields serialised as canonical JSON
    (sorted keys, no extra spaces). Same input -> same hash on every machine.
  * Every block stores the hash of the block before it, so changing an old block
    changes its hash and breaks the link to the next block. That makes tampering
    DETECTABLE - it does not make it impossible.
  * There is no mining and no cryptocurrency. Blocks are agreed by majority vote
    (see backend/app/blockchain/consensus.py).
"""
import hashlib
import json
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NODE_IDS = ["node1", "node2", "node3", "node4", "node5"]   # the five registered identities
QUORUM = 3                                                # votes needed out of 5
ZERO_HASH = "0" * 64
MAX_TX_BYTES = 2048          # transactions hold metadata only, never file contents
FORBIDDEN_TX_FIELDS = {"content", "data", "file_bytes", "payload"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Required fields for each supported transaction type
TX_SCHEMAS = {
    "FILE_UPLOADED": ["file_id", "file_name", "size", "sha256"],
    "FILE_VERSION_CREATED": ["file_id", "document_id", "version_number", "previous_file_id",
                             "file_name", "size", "sha256"],
    "FILE_REPLICATED": ["file_id", "sha256", "nodes_ok", "nodes_failed"],
    "INTEGRITY_CHECKED": ["file_id", "sha256", "matching", "mismatching", "unavailable"],
    "NODE_FAILURE": ["node_id", "detail"],
    "FILE_RECOVERED": ["file_id", "sha256", "source_node", "repaired_nodes"],
    "MALICIOUS_ACTIVITY_DETECTED": ["node_id", "evidence"],
    "NODE_REJOINED": ["node_id"],
}


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string (used for block/tx timestamps)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys and no whitespace, so every node hashes identical bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
def compute_block_hash(block: dict) -> str:
    """SHA-256 over every block field except the 'hash' field itself."""
    content = {
        "index": block["index"],
        "timestamp": block["timestamp"],
        "previous_hash": block["previous_hash"],
        "transactions": block["transactions"],
        "proposer": block["proposer"],
    }
    return sha256_bytes(canonical_json(content).encode("utf-8"))


def make_block(index: int, previous_hash: str, transactions: list, proposer: str,
               timestamp: str | None = None) -> dict:
    block = {
        "index": index,
        "timestamp": timestamp or utc_now(),
        "previous_hash": previous_hash,
        "transactions": transactions,
        "proposer": proposer,
    }
    block["hash"] = compute_block_hash(block)
    return block


def genesis_block() -> dict:
    """Identical on all five nodes because every field is fixed."""
    return make_block(
        index=0,
        previous_hash=ZERO_HASH,
        transactions=[{"type": "GENESIS", "note": "BlockStore-5 educational ledger"}],
        proposer="genesis",
        timestamp="2026-01-01T00:00:00.000Z",
    )


GENESIS_HASH = genesis_block()["hash"]


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def validate_transaction(tx: dict, chain: list) -> str | None:
    """Return None if the transaction is acceptable, otherwise a human-readable reason."""
    if not isinstance(tx, dict):
        return "transaction is not an object"
    ttype = tx.get("type")
    if ttype not in TX_SCHEMAS:
        return f"unknown transaction type '{ttype}'"
    if "timestamp" not in tx:
        return f"{ttype}: missing timestamp"
    missing = [f for f in TX_SCHEMAS[ttype] if f not in tx]
    if missing:
        return f"{ttype}: missing field(s) {missing}"
    if FORBIDDEN_TX_FIELDS & set(tx.keys()):
        return f"{ttype}: transactions must not carry file contents"
    if len(canonical_json(tx)) > MAX_TX_BYTES:
        return f"{ttype}: transaction larger than {MAX_TX_BYTES} bytes"
    if "sha256" in tx and not SHA256_RE.match(str(tx["sha256"])):
        return f"{ttype}: sha256 is not a 64-character lowercase hex string"
    for key in ("node_id", "source_node"):
        if key in tx and tx[key] not in NODE_IDS:
            return f"{ttype}: '{tx[key]}' is not a registered node identity"
    for key in ("nodes_ok", "nodes_failed", "matching", "mismatching", "unavailable", "repaired_nodes"):
        if key in tx:
            if not isinstance(tx[key], list) or any(n not in NODE_IDS for n in tx[key]):
                return f"{ttype}: '{key}' must be a list of registered node ids"

    # Semantic rules checked against the committed history
    known = known_files(chain)
    if ttype == "FILE_UPLOADED":
        if tx["file_id"] in known:
            # This is how a forged record trying to replace a trusted hash is caught.
            return (f"FILE_UPLOADED: file_id {tx['file_id']} already committed with hash "
                    f"{known[tx['file_id']][:12]}... - a trusted hash cannot be overwritten")
        if not isinstance(tx["size"], int) or tx["size"] < 0:
            return "FILE_UPLOADED: size must be a non-negative integer"
        if tx.get("document_id", tx["file_id"]) != tx["file_id"] or tx.get("version_number", 1) != 1:
            return "FILE_UPLOADED: initial version must use its file_id as document_id and version_number 1"
    elif ttype == "FILE_VERSION_CREATED":
        if tx["file_id"] in known:
            return f"FILE_VERSION_CREATED: file_id {tx['file_id']} is already committed"
        if any(not FILE_ID_RE.fullmatch(str(tx[key]))
               for key in ("file_id", "document_id", "previous_file_id")):
            return "FILE_VERSION_CREATED: file and document ids must be 32-character lowercase hex strings"
        if type(tx["version_number"]) is not int or tx["version_number"] < 2:
            return "FILE_VERSION_CREATED: version_number must be an integer greater than 1"
        if not isinstance(tx["size"], int) or tx["size"] < 0:
            return "FILE_VERSION_CREATED: size must be a non-negative integer"
        versions = known_file_versions(chain)
        parent = versions.get(tx["previous_file_id"])
        if parent is None:
            return "FILE_VERSION_CREATED: previous_file_id has no committed document version"
        latest_file_id = max(
            ((file_id, version["version_number"]) for file_id, version in versions.items()
             if version["document_id"] == parent["document_id"]),
            key=lambda entry: entry[1],
        )[0]
        if tx["previous_file_id"] != latest_file_id:
            return "FILE_VERSION_CREATED: previous_file_id must reference the latest committed version"
        if tx["document_id"] != parent["document_id"]:
            return "FILE_VERSION_CREATED: document_id does not match the parent version"
        if tx["version_number"] != parent["version_number"] + 1:
            return "FILE_VERSION_CREATED: version_number must increment the parent version by one"
    elif ttype in ("FILE_REPLICATED", "INTEGRITY_CHECKED", "FILE_RECOVERED"):
        expected = known.get(tx["file_id"])
        if expected is None:
            return (f"{ttype}: file_id {tx['file_id']} has no committed FILE_UPLOADED or "
                    "FILE_VERSION_CREATED record")
        if tx["sha256"] != expected:
            return f"{ttype}: sha256 does not match the committed trusted hash"
    return None


def known_files(chain: list) -> dict:
    """file_id -> trusted sha256 for every committed document version."""
    files = {}
    for block in chain:
        for tx in block.get("transactions", []):
            if tx.get("type") in ("FILE_UPLOADED", "FILE_VERSION_CREATED"):
                files[tx["file_id"]] = tx["sha256"]
    return files


def known_file_versions(chain: list) -> dict:
    """file_id -> immutable logical-document and version metadata."""
    versions = {}
    for block in chain:
        for tx in block.get("transactions", []):
            if tx.get("type") == "FILE_UPLOADED":
                versions[tx["file_id"]] = {
                    "document_id": tx.get("document_id", tx["file_id"]),
                    "version_number": tx.get("version_number", 1),
                }
            elif tx.get("type") == "FILE_VERSION_CREATED":
                versions[tx["file_id"]] = {
                    "document_id": tx["document_id"],
                    "version_number": tx["version_number"],
                }
    return versions


def validate_new_block(block: dict, chain: list) -> str | None:
    """
    Check a proposed block against a node's own committed chain.
    Returns None when valid, otherwise the reason for rejection.
    """
    required = ["index", "timestamp", "previous_hash", "transactions", "proposer", "hash"]
    if not isinstance(block, dict) or any(k not in block for k in required):
        return "block is missing required fields"
    head = chain[-1]
    if block["index"] != head["index"] + 1:
        return f"index {block['index']} is not sequential (expected {head['index'] + 1})"
    if block["previous_hash"] != head["hash"]:
        return (f"previous_hash {str(block['previous_hash'])[:12]}... does not match "
                f"committed head {head['hash'][:12]}...")
    if block["hash"] != compute_block_hash(block):
        return "stored block hash does not match the recalculated SHA-256 hash"
    if block["proposer"] not in NODE_IDS + ["coordinator"]:
        return f"proposer '{block['proposer']}' is not a registered identity"
    if not isinstance(block["transactions"], list) or not block["transactions"]:
        return "block has no transactions"
    # Validate transactions one by one, letting later ones see earlier ones in this block.
    # Each earlier tx must be treated as part of the chain seen by the next validation step.
    working_chain = list(chain)
    pending_transactions = []
    for i, tx in enumerate(block["transactions"]):
        problem = validate_transaction(tx, working_chain + [{"transactions": pending_transactions}])
        if problem:
            return f"transaction {i}: {problem}"
        pending_transactions.append(tx)
    return None


def validate_chain(chain: list) -> dict:
    """
    Full verification of a ledger copy:
      1. genesis block is the expected one
      2. indexes are sequential
      3. each stored hash equals the recalculated hash
      4. each previous_hash equals the hash of the block before
      5. every transaction is valid against the history before it
    Returns {"valid": bool, "errors": [...], "height": n, "head_hash": "..."}.
    """
    errors = []
    if not chain:
        return {"valid": False, "errors": ["ledger is empty"], "height": 0, "head_hash": None}
    try:
        genesis_valid = (isinstance(chain[0], dict)
                         and chain[0].get("hash") == GENESIS_HASH
                         and compute_block_hash(chain[0]) == GENESIS_HASH)
    except (KeyError, TypeError):
        genesis_valid = False
    if not genesis_valid:
        errors.append({"index": 0, "problem": "genesis block is not the expected genesis block"})
    for i in range(1, len(chain)):
        try:
            problem = validate_new_block(chain[i], chain[:i])
        except (KeyError, TypeError, IndexError) as exc:
            problem = f"malformed block: {exc}"
        if problem:
            errors.append({"index": i, "problem": problem})
    return {
        "valid": not errors,
        "errors": errors,
        "height": len(chain),
        "head_hash": chain[-1].get("hash"),
    }


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------
import hmac  # noqa: E402  (kept next to the code that uses it)


def vote_message(proposal_id: str, node_id: str, block_hash: str, decision: str) -> bytes:
    return f"{proposal_id}|{node_id}|{block_hash}|{decision}".encode("utf-8")


def sign_vote(secret: str, proposal_id: str, node_id: str, block_hash: str, decision: str) -> str:
    """
    Each node owns a secret key. A vote carries an HMAC-SHA256 tag made with that key,
    so the coordinator can check that the vote really came from the registered node
    and was not invented by someone else (for example by the frontend).
    """
    return hmac.new(secret.encode("utf-8"),
                    vote_message(proposal_id, node_id, block_hash, decision),
                    hashlib.sha256).hexdigest()


def verify_vote_signature(secret: str, vote: dict, proposal_id: str) -> bool:
    expected = sign_vote(secret, proposal_id, vote.get("node_id", ""),
                         vote.get("block_hash", ""), vote.get("decision", ""))
    return hmac.compare_digest(expected, str(vote.get("signature", "")))
