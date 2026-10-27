"""Test setup.

Unit tests import the backend code directly.
Integration tests start a FRESH, isolated cluster - five real node processes and one
backend process on ports 9001-9005 / 9000 with temporary data folders - so they never
touch your demo data on ports 8000-8005.
"""
import os
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
_TMP = Path(tempfile.mkdtemp(prefix="blockstore5-tests-"))

# Must be set before `app` is imported by the unit tests
os.environ.setdefault("DB_PATH", str(_TMP / "unit.db"))
os.environ.setdefault("ENABLE_HEALTH_MONITOR", "0")
os.environ["TRUSTGRID_DEMO_USERS"] = json.dumps([
    {"organization": "manufacturer", "email": "manufacturer@test.invalid", "password": "Test-Password-M-2026"},
    {"organization": "logistics", "email": "logistics@test.invalid", "password": "Test-Password-L-2026"},
    {"organization": "inspection", "email": "inspection@test.invalid", "password": "Test-Password-I-2026"},
    {"organization": "distributor", "email": "distributor@test.invalid", "password": "Test-Password-D-2026"},
    {"organization": "distributor", "email": "member@test.invalid", "password": "Test-Password-Member-2026",
     "role": "member"},
])
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(ROOT))

NODE_PORTS = {f"node{i}": 9000 + i for i in range(1, 6)}
BACKEND_PORT = 9000
BASE = f"http://127.0.0.1:{BACKEND_PORT}/api"

http = requests.Session()
http.trust_env = False        # never route local test traffic through a proxy


def _wait(url, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if http.get(url, timeout=1).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.2)
    return False


class Cluster:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.procs = {}
        self.env = {k: v for k, v in os.environ.items() if k not in ("DB_PATH", "ENABLE_HEALTH_MONITOR")}

    def _spawn(self, name, args, extra, cwd):
        log = open(self.workdir / f"{name}.log", "ab")
        self.procs[name] = subprocess.Popen([sys.executable, "-m", "uvicorn", *args], cwd=cwd,
                                            env={**self.env, **extra}, stdout=log, stderr=subprocess.STDOUT)

    def start_node(self, nid):
        port = NODE_PORTS[nid]
        self._spawn(nid, ["storage_node.node_app.main:app", "--port", str(port)],
                    {"NODE_ID": nid, "NODE_DATA_DIR": str(self.workdir / nid)}, ROOT)
        assert _wait(f"http://127.0.0.1:{port}/health"), f"{nid} did not start"

    def stop_node(self, nid):
        """A REAL failure: terminate the node's operating-system process."""
        p = self.procs.pop(nid)
        p.terminate()
        p.wait(10)

    def start(self):
        for nid in NODE_PORTS:
            self.start_node(nid)
        urls = ",".join(f"{nid}=http://127.0.0.1:{port}" for nid, port in NODE_PORTS.items())
        self._spawn("backend", ["app.main:app", "--port", str(BACKEND_PORT)],
                    {"NODE_URLS": urls, "DB_PATH": str(self.workdir / "backend.db"),
                     "HEALTH_INTERVAL_SECONDS": "0.7"}, BACKEND_DIR)
        assert _wait(BASE + "/health"), "backend did not start"

    def stop(self):
        for p in self.procs.values():
            p.terminate()
        for p in self.procs.values():
            p.wait(10)


@pytest.fixture(scope="session")
def cluster():
    c = Cluster(_TMP)
    c.start()
    yield c
    c.stop()


def wait_for(predicate, timeout=15, interval=0.3):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()
