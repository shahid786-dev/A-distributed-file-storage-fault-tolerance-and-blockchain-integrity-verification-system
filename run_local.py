#!/usr/bin/env python3
"""
Local-development mode WITHOUT Docker.

Starts the five storage nodes and the coordinator backend as SEPARATE operating-system
processes (separate PIDs, ports, data folders and memory). They talk only over HTTP,
just like the Docker containers do.

    python run_local.py start               # start node1..node5 (8001-8005) + backend (8000)
    python run_local.py status              # show what is running
    python run_local.py stop-node node2     # REALLY stop one node process (real failure)
    python run_local.py start-node node2    # start it again
    python run_local.py stop                # stop everything
    python run_local.py reset               # stop everything and delete ./runtime data

Logs are written to ./runtime/logs/. Works on Windows, Linux and macOS.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
LOGS = RUNTIME / "logs"
PIDS = RUNTIME / "pids.json"
NODES = {f"node{i}": 8000 + i for i in range(1, 6)}
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))


def _load_pids() -> dict:
    return json.loads(PIDS.read_text()) if PIDS.exists() else {}


def _save_pids(pids: dict):
    RUNTIME.mkdir(exist_ok=True)
    PIDS.write_text(json.dumps(pids, indent=2))


def _alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _spawn(name: str, args: list, env: dict, cwd: Path) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", *args], cwd=cwd, env={**os.environ, **env},
                            stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                            start_new_session=(os.name != "nt"))
    return proc.pid


def _wait_http(url: str, seconds: float = 15) -> bool:
    deadline = time.time() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < deadline:
        try:
            with opener.open(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def start_node(node_id: str, pids: dict | None = None):
    pids = pids if pids is not None else _load_pids()
    if node_id not in NODES:
        sys.exit(f"Unknown node {node_id}. Use one of {list(NODES)}")
    if node_id in pids and _alive(pids[node_id]):
        print(f"{node_id} already running (pid {pids[node_id]})")
        return
    port = NODES[node_id]
    pids[node_id] = _spawn(node_id, ["storage_node.node_app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                           {"NODE_ID": node_id, "NODE_DATA_DIR": str(RUNTIME / node_id)}, ROOT)
    _save_pids(pids)
    ok = _wait_http(f"http://127.0.0.1:{port}/health")
    print(f"{node_id:8} pid {pids[node_id]:<7} http://127.0.0.1:{port}  {'online' if ok else 'NOT RESPONDING - see runtime/logs'}")


def stop_process(name: str, pids: dict | None = None):
    pids = pids if pids is not None else _load_pids()
    pid = pids.pop(name, None)
    if pid and _alive(pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            if not _alive(pid):
                break
            time.sleep(0.1)
        print(f"stopped {name} (pid {pid})")
    else:
        print(f"{name} was not running")
    _save_pids(pids)


def start_all():
    pids = _load_pids()
    for nid in NODES:
        start_node(nid, pids)
    if "backend" in pids and _alive(pids["backend"]):
        print("backend already running")
    else:
        pids["backend"] = _spawn("backend", ["app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
                                 {"DB_PATH": str(RUNTIME / "backend" / "blockstore.db")}, ROOT / "backend")
        _save_pids(pids)
        ok = _wait_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
        print(f"backend  pid {pids['backend']:<7} http://127.0.0.1:{BACKEND_PORT}  {'online' if ok else 'NOT RESPONDING'}")
    print(f"\nAPI docs: http://localhost:{BACKEND_PORT}/docs")
    print("Frontend: cd frontend && npm install && npm run dev   ->  http://localhost:5173")


def status():
    pids = _load_pids()
    for name in [*NODES, "backend"]:
        pid = pids.get(name)
        print(f"{name:8} {'running pid ' + str(pid) if pid and _alive(pid) else 'stopped'}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "start":
        start_all()
    elif cmd == "status":
        status()
    elif cmd == "start-node" and arg:
        start_node(arg)
    elif cmd == "stop-node" and arg:
        stop_process(arg)
    elif cmd in ("stop", "reset"):
        for name in list(_load_pids()):
            stop_process(name)
        if cmd == "reset" and RUNTIME.exists():
            shutil.rmtree(RUNTIME)
            print("deleted ./runtime (all node data, ledgers and metadata)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
