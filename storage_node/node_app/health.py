"""Runtime state of this node: simulated failure and malicious-simulation flags.

Both flags live in memory only, so restarting the node process/container always
brings it back as an honest, healthy node (simulations are reversible).
"""
import threading
import time

_lock = threading.Lock()
_state = {
    "simulated_failure": False,   # True -> node refuses every request with HTTP 503
    "malicious": False,           # True -> node behaves dishonestly (opt-in test mode)
    "started_at": time.time(),
}


def get(key):
    with _lock:
        return _state[key]


def set_flag(key, value: bool):
    with _lock:
        _state[key] = bool(value)


def uptime_seconds() -> float:
    return round(time.time() - _state["started_at"], 1)
