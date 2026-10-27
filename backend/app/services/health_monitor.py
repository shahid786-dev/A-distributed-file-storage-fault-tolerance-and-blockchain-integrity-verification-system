"""Background health monitor.

Every HEALTH_INTERVAL seconds the coordinator calls GET /health on all five nodes.
  * online -> offline : the node is marked unavailable, an event is logged and a
                        NODE_FAILURE record is committed by the remaining nodes.
  * offline -> online : the node's ledger is synchronised (missing blocks are sent
                        and the node validates each one), then NODE_REJOINED is committed.
  * a node that is merely BEHIND (e.g. it missed a block) is caught up automatically.
A node whose ledger copy is INVALID or DIVERGED is not auto-repaired, so the
tampering can be shown on the dashboard; use POST /api/blockchain/repair for that.
"""
import logging
import threading
import time

from shared.blockcore import NODE_IDS, utc_now

from ..blockchain import consensus, ledger_view
from ..config import HEALTH_INTERVAL, HEALTH_TIMEOUT
from ..database import db
from . import file_service, node_client

log = logging.getLogger("blockstore.monitor")

_state_lock = threading.Lock()
_state = {nid: {"online": None, "last_checked": None, "last_error": None, "health": None}
          for nid in NODE_IDS}
_stop = threading.Event()


def snapshot() -> dict:
    with _state_lock:
        return {nid: dict(s) for nid, s in _state.items()}


def sync_node(node_id: str, view: dict | None = None, allow_replace: bool = False) -> dict:
    """Bring one node's ledger in line with the committed ledger."""
    view = view or ledger_view.committed_view()
    if not view["has_quorum"]:
        return {"node_id": node_id, "action": "none", "detail": "no committed quorum ledger"}
    info = view["nodes"][node_id]
    committed = view["committed_chain"]
    if info["state"] == "behind":
        missing = committed[info["height"]:]
        res = node_client.call(node_id, "POST", "/ledger/sync", json={"blocks": missing})
        detail = res["body"] if res["ok"] else res.get("error")
        return {"node_id": node_id, "action": "sync", "blocks_sent": len(missing), "result": detail}
    if info["state"] in ("invalid", "diverged") and allow_replace:
        res = node_client.call(node_id, "POST", "/ledger/replace", json={"chain": committed})
        detail = res["body"] if res["ok"] else res.get("error")
        return {"node_id": node_id, "action": "replace", "result": detail}
    return {"node_id": node_id, "action": "none", "state": info["state"]}


_check_lock = threading.Lock()


def check_once():
    """One monitoring round (also called directly after a simulation action)."""
    with _check_lock:
        _check_once()


def _check_once():
    results = node_client.call_all("GET", "/health", timeout=HEALTH_TIMEOUT)   # parallel
    transitions = []
    startup_nodes = []
    with _state_lock:
        for nid, res in results.items():
            s = _state[nid]
            was_online = s["online"]
            s["online"] = res["ok"]
            s["last_checked"] = utc_now()
            s["last_error"] = None if res["ok"] else res.get("error")
            s["health"] = res["body"] if res["ok"] else None
            if was_online is not None and was_online != res["ok"]:
                transitions.append((nid, res["ok"], s["last_error"]))
            elif was_online is None and not res["ok"]:
                transitions.append((nid, False, s["last_error"]))
            elif was_online is None and res["ok"]:
                startup_nodes.append(nid)
    for nid, res in results.items():
        db.count_health(nid, res["ok"])

    for nid, online, error in transitions:
        if online:
            db.log_event("success", "node", f"{nid} is reachable again - synchronising its ledger")
            sync = sync_node(nid)
            db.log_event("info", "node", f"{nid} ledger sync: {sync.get('action')}", sync)
            _commit_quietly([{"type": "NODE_REJOINED", "node_id": nid, "timestamp": utc_now()}])
            try:
                repairs = file_service.repair_node_replicas(nid)
                db.log_event("info", "recovery", f"Automatic rejoin repair checked {repairs['checked']} file(s) on {nid}",
                             repairs)
            except Exception:
                log.exception("Automatic replica repair failed for rejoined node %s", nid)
        else:
            db.log_event("error", "node", f"{nid} failed its health check: {error}")
            _commit_quietly([{"type": "NODE_FAILURE", "node_id": nid, "detail": str(error)[:200],
                              "timestamp": utc_now()}])

    # Also reconcile replicas when the coordinator starts after storage nodes.
    for nid in startup_nodes:
        try:
            repairs = file_service.repair_node_replicas(nid)
            db.log_event("info", "recovery", f"Startup replica reconciliation checked {repairs['checked']} file(s) on {nid}",
                         repairs)
        except Exception:
            log.exception("Startup replica reconciliation failed for node %s", nid)

    # Automatically catch up nodes that are simply behind (missed a block while busy/offline)
    view = None
    for nid, res in results.items():
        if res["ok"]:
            view = view or ledger_view.committed_view()
            if view["nodes"][nid]["state"] == "behind":
                sync_node(nid, view)


def _commit_quietly(transactions):
    try:
        consensus.propose_transactions(transactions)
    except consensus.NoQuorum as exc:
        db.log_event("warning", "consensus", f"Could not record {transactions[0]['type']}: {exc}")


def _loop():
    while not _stop.is_set():
        try:
            check_once()
        except Exception:   # the monitor must never die
            log.exception("health check round failed")
        _stop.wait(HEALTH_INTERVAL)


def start():
    threading.Thread(target=_loop, name="health-monitor", daemon=True).start()


def stop():
    _stop.set()
