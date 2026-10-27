"""This node's own copy of the committed ledger, stored as ledger.json in its data dir."""
import json
import os
import threading

from shared.blockcore import genesis_block, validate_chain, validate_new_block

from .config import LEDGER_PATH

_lock = threading.Lock()


def _load() -> list:
    if not LEDGER_PATH.exists():
        chain = [genesis_block()]
        _save(chain)
        return chain
    return json.loads(LEDGER_PATH.read_text())


def _save(chain: list):
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(chain, indent=1))
    os.replace(tmp, LEDGER_PATH)


def get_chain() -> list:
    with _lock:
        return _load()


def head() -> dict:
    return get_chain()[-1]


def append(block: dict) -> str | None:
    """Validate a committed block against our own chain, then append it.
    Returns None on success or the rejection reason."""
    with _lock:
        chain = _load()
        problem = validate_new_block(block, chain)
        if problem:
            return problem
        chain.append(block)
        _save(chain)
        return None


def sync(blocks: list) -> dict:
    """Catch up after downtime: append missing blocks one by one, validating each."""
    appended = 0
    for block in blocks:
        with _lock:
            chain = _load()
            if block["index"] < len(chain):
                if chain[block["index"]]["hash"] == block.get("hash"):
                    continue          # already have it
                return {"appended": appended, "error": f"diverged at index {block['index']}"}
            problem = validate_new_block(block, chain)
            if problem:
                return {"appended": appended, "error": f"block {block['index']}: {problem}"}
            chain.append(block)
            _save(chain)
            appended += 1
    return {"appended": appended, "error": None}


def replace(new_chain: list) -> str | None:
    """Replace a damaged local copy with a full chain, but only if that chain is valid."""
    result = validate_chain(new_chain)
    if not result["valid"]:
        return f"offered chain is invalid: {result['errors'][:2]}"
    with _lock:
        _save(new_chain)
    return None


def tamper_past_block() -> dict:
    """TEST ONLY: edit a committed transaction in THIS node's ledger file directly,
    without recalculating hashes - like an attacker with disk access."""
    with _lock:
        chain = _load()
        if len(chain) < 2:
            return {"ok": False, "detail": "ledger has only the genesis block; commit something first"}
        target = chain[1]
        tx = target["transactions"][0]
        field = "sha256" if "sha256" in tx else "detail"
        old = tx.get(field)
        tx[field] = "f" * 64 if field == "sha256" else "edited by attacker"
        _save(chain)
        return {"ok": True, "block_index": 1, "field": field, "old_value": old, "new_value": tx[field]}
