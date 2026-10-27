#!/usr/bin/env python3
"""
Quick end-to-end check of a RUNNING BlockStore-5 system (Docker or local mode).

    python scripts/smoke_test.py --mode docker      # after: docker compose up -d
    python scripts/smoke_test.py --mode local       # after: python run_local.py start

It uploads a file, checks all five replicas, corrupts node3's copy (test mode),
rejects an invalid block, really stops node2 (docker compose stop / process kill),
downloads a verified copy, restarts node2 and checks that the ledgers agree again.
Exit code 0 means every step passed. Uses only the Python standard library.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
BASE = f"http://127.0.0.1:{os.environ.get('BACKEND_PORT', '8000')}/api"
failures = []
TOKEN = None


def call(method, path, body=None, raw=False, form_file=None):
    headers, data = {}, None
    if TOKEN:
        headers["Authorization"] = " ".join(("Bearer", TOKEN))
    if form_file:
        boundary = uuid.uuid4().hex
        name, content = form_file
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with OPENER.open(req, timeout=60) as r:
            content = r.read()
            return r.status, (content if raw else json.loads(content)), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), {}


def check(label, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def wait(predicate, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def add_auth_arguments(parser):
    parser.add_argument("--organization", default=os.environ.get("TRUSTGRID_ORGANIZATION", "manufacturer"))
    parser.add_argument("--email", default=os.environ.get("TRUSTGRID_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("TRUSTGRID_PASSWORD"))


def authenticate(args):
    global TOKEN
    if not args.email:
        args.email = input(f"Email for {args.organization}: ").strip()
    if not args.password:
        args.password = getpass("Password: ")
    status, result, _ = call("POST", "/auth/login", {
        "organization": args.organization, "email": args.email, "password": args.password,
    })
    if status != 200 or not result.get("access_token"):
        sys.exit(f"Organization login failed (HTTP {status}): {result}")
    TOKEN = result["access_token"]


def node_states():
    return {n["node_id"]: n["online"] for n in call("GET", "/nodes")[1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["docker", "local"], required=True)
    add_auth_arguments(ap)
    args = ap.parse_args()
    authenticate(args)
    stop = (["docker", "compose", "stop", "node2"] if args.mode == "docker"
            else [sys.executable, "run_local.py", "stop-node", "node2"])
    start = (["docker", "compose", "start", "node2"] if args.mode == "docker"
             else [sys.executable, "run_local.py", "start-node", "node2"])

    print("1. Five nodes reachable")
    check("all five nodes online", wait(lambda: all(node_states().values())), str(node_states()))

    print("2. Upload and replicate")
    content = f"smoke test {time.time()}\n".encode() * 20
    status, up, _ = call("POST", "/files/upload", form_file=("smoke.txt", content))
    check("upload accepted", status == 200, str(status))
    if status != 200:
        return
    fid = up["file_id"]
    check("5 verified replicas", up["healthy_replicas"] == 5)
    check("trusted hash = local SHA-256", up["sha256"] == hashlib.sha256(content).hexdigest())

    print("2a. Immutable version and stale-parent conflict")
    next_content = content + b"version two\n"
    status, version, _ = call("POST", f"/files/{fid}/versions?expected_version=1",
                              form_file=("smoke.txt", next_content))
    check("version 2 committed with the same document id",
          status == 200 and version.get("document_id") == up["document_id"]
          and version.get("version_number") == 2 and version.get("previous_file_id") == fid, str(status))
    stale_status, stale, _ = call("POST", f"/files/{fid}/versions?expected_version=1",
                                  form_file=("smoke.txt", b"stale competing version"))
    check("stale version parent rejected with HTTP 409",
          stale_status == 409 and stale.get("detail", {}).get("latest_version") == 2, str(stale_status))

    print("3. Attack A: tamper node3's replica")
    call("POST", "/simulation/malicious-node", {"node_id": "node3", "enabled": True})
    call("POST", "/simulation/corrupt-replica", {"node_id": "node3", "file_id": fid, "confirm": True})
    _, v, _ = call("POST", f"/files/{fid}/verify")
    st = {r["node_id"]: r["status"] for r in v["replicas"]}
    check("node3 detected as mismatch", st["node3"] == "mismatch", str(st))
    check("other four still match", all(st[n] == "match" for n in ("node1", "node2", "node4", "node5")))

    print("4. Attack B: invalid block from node3")
    _, b, _ = call("POST", "/simulation/invalid-block", {"node_id": "node3", "attack": "wrong_previous_hash"})
    p = b["proposal"]
    check("proposal rejected", p["outcome"] == "rejected", f"{p['accept_count']} accept")
    check("ledger unchanged", p["ledger_unchanged"])
    call("POST", "/simulation/malicious-node", {"node_id": "node3", "enabled": False})

    print("5. Recover tampered replica")
    _, r, _ = call("POST", f"/files/{fid}/recover")
    check("node3 repaired", "node3" in r.get("repaired_nodes", []), str(r.get("repaired_nodes")))

    print("6. REAL failure of node2: " + " ".join(stop))
    subprocess.run(stop, cwd=ROOT, check=False, capture_output=True)
    check("node2 reported offline", wait(lambda: node_states()["node2"] is False))
    status, data, headers = call("GET", f"/files/{fid}/download", raw=True)
    check("download still works", status == 200 and data == content,
          f"served by {headers.get('X-BlockStore-Source-Node') or headers.get('x-blockstore-source-node')}")
    catchup_content = b"uploaded while node2 is offline\n" * 20
    status, catchup_upload, _ = call("POST", "/files/upload",
                                     form_file=("rejoin-catchup.txt", catchup_content))
    check("upload succeeds with node2 offline", status == 200, str(status))
    if status != 200:
        return
    catchup_id = catchup_upload["file_id"]
    check("offline node is reported as a missing replica",
          catchup_upload["healthy_replicas"] == 4, str(catchup_upload["healthy_replicas"]))

    print("7. Restart node2: " + " ".join(start))
    subprocess.run(start, cwd=ROOT, check=False, capture_output=True)
    check("node2 back online", wait(lambda: node_states()["node2"] is True, 30))
    def catchup_repaired():
        status, report, _ = call("GET", f"/files/{catchup_id}/replicas")
        return (status == 200 and report["summary"]["healthy"] == 5
                and next(r for r in report["replicas"] if r["node_id"] == "node2")["status"] == "match")

    check("missed replica repaired automatically after rejoin", wait(catchup_repaired, 30))
    check("all ledgers agree after sync",
          wait(lambda: call("GET", "/blockchain/validate")[1]["all_nodes_agree"], 20))

    print("\nRESULT:", "ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")


if __name__ == "__main__":
    main()
    sys.exit(1 if failures else 0)
