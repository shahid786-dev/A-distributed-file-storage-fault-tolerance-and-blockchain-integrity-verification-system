"""All HTTP communication from the coordinator to the five storage nodes.

Every call has a timeout, and failures are returned as data ({"ok": False, ...})
instead of crashing, so an offline node is simply reported as unavailable.
"""
from concurrent.futures import ThreadPoolExecutor

import requests

from ..config import CONTROL_TOKEN, HEALTH_TIMEOUT, NODE_TIMEOUT, NODE_URLS

_HEADERS = {"X-Control-Token": CONTROL_TOKEN}
_pool = ThreadPoolExecutor(max_workers=10)
_session = requests.Session()
_session.trust_env = False   # nodes are on the local/Docker network: never use an HTTP proxy


def call(node_id: str, method: str, path: str, *, json=None, data=None, timeout=None,
         raw=False) -> dict:
    """Make one request. Returns {"ok", "status", "body" | "content", "error"}."""
    url = NODE_URLS[node_id] + path
    try:
        resp = _session.request(method, url, json=json, data=data, headers=_HEADERS,
                                timeout=timeout or NODE_TIMEOUT)
    except requests.Timeout:
        return {"ok": False, "status": None, "error": "timeout"}
    except requests.ConnectionError:
        return {"ok": False, "status": None, "error": "connection refused / unreachable"}
    result = {"ok": resp.ok, "status": resp.status_code}
    if raw and resp.ok:
        result["content"] = resp.content
    else:
        try:
            result["body"] = resp.json()
        except ValueError:
            result["body"] = {"detail": resp.text[:200]}
    if not resp.ok:
        result["error"] = (result.get("body") or {}).get("detail", f"HTTP {resp.status_code}")
    return result


def call_all(method: str, path_fn, node_ids=None, **kwargs) -> dict:
    """Run the same kind of request against several nodes IN PARALLEL.
    path_fn may be a string or a function node_id -> path."""
    node_ids = node_ids or list(NODE_URLS)
    futures = {
        nid: _pool.submit(call, nid, method, path_fn(nid) if callable(path_fn) else path_fn, **kwargs)
        for nid in node_ids
    }
    return {nid: f.result() for nid, f in futures.items()}


def health(node_id: str) -> dict:
    return call(node_id, "GET", "/health", timeout=HEALTH_TIMEOUT)


def ledger(node_id: str) -> dict:
    return call(node_id, "GET", "/ledger")


def file_timeout(size: int) -> float:
    """Bigger files get a bit more time (minimum NODE_TIMEOUT seconds)."""
    return NODE_TIMEOUT + size / (5 * 1024 * 1024)
