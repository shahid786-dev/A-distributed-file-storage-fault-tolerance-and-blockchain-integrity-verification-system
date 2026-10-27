"""Read the five ledger copies and work out the COMMITTED ledger.

The coordinator keeps no ledger of its own. The committed ledger is the chain that
at least 3 of the 5 nodes hold, where each copy passes full validation
(genesis, sequential indexes, recalculated hashes, previous-hash links).
"""
from collections import Counter

from shared.blockcore import NODE_IDS, QUORUM, validate_chain

from ..services import node_client


def collect_ledgers() -> dict:
    """node_id -> {"online", "chain", "validation", "error"}"""
    results = node_client.call_all("GET", "/ledger")
    out = {}
    for nid, res in results.items():
        if res["ok"]:
            chain = res["body"]["chain"]
            # Validate here ourselves - never trust the node's own validation report
            out[nid] = {"online": True, "chain": chain, "validation": validate_chain(chain), "error": None}
        else:
            out[nid] = {"online": False, "chain": None, "validation": None, "error": res.get("error")}
    return out


def committed_view(ledgers: dict | None = None) -> dict:
    ledgers = ledgers or collect_ledgers()
    valid_heads = Counter(
        info["validation"]["head_hash"]
        for info in ledgers.values() if info["online"] and info["validation"]["valid"]
    )
    committed_chain, committed_head = None, None
    if valid_heads:
        head, count = valid_heads.most_common(1)[0]
        if count >= QUORUM:
            committed_head = head
            committed_chain = next(info["chain"] for info in ledgers.values()
                                   if info["online"] and info["validation"]["valid"]
                                   and info["validation"]["head_hash"] == head)

    per_node = {}
    for nid in NODE_IDS:
        info = ledgers[nid]
        if not info["online"]:
            per_node[nid] = {"state": "unreachable", "height": None, "head_hash": None,
                             "valid": None, "errors": [], "detail": info["error"]}
            continue
        v = info["validation"]
        state = "consistent"
        if not v["valid"]:
            state = "invalid"
        elif committed_chain is None:
            state = "unknown"
        elif v["head_hash"] != committed_head:
            chain = info["chain"]
            is_prefix = (len(chain) < len(committed_chain)
                         and committed_chain[len(chain) - 1]["hash"] == chain[-1]["hash"])
            state = "behind" if is_prefix else "diverged"
        per_node[nid] = {"state": state, "height": v["height"], "head_hash": v["head_hash"],
                         "valid": v["valid"], "errors": v["errors"], "detail": None}

    agreeing = [nid for nid, p in per_node.items() if p["state"] == "consistent"]
    return {
        "has_quorum": committed_chain is not None,
        "committed_height": len(committed_chain) if committed_chain else None,
        "committed_head": committed_head,
        "committed_chain": committed_chain,
        "agreeing_nodes": agreeing,
        "nodes": per_node,
        "all_nodes_agree": len(agreeing) == len(NODE_IDS),
    }
