#!/usr/bin/env python3
"""
Small performance evaluation of a RUNNING BlockStore-5 system.

    python scripts/benchmark.py --runs 3 --label "Docker, my laptop"

For several file sizes it measures (milliseconds):
  upload total, replication to 5 nodes, ledger vote+commit, integrity verification,
  and recovery of one corrupted replica. It also reports health-check counts and
  the number of valid replicas before / during / after a simulated node failure.
Results are written to docs/results/benchmark.md and benchmark.json.
Every number in the output comes from this run - nothing is estimated.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import add_auth_arguments, authenticate, call  # noqa: E402  (same tiny HTTP helper)

ROOT = Path(__file__).resolve().parents[1]
SIZES = [("1 KB", 1024), ("100 KB", 100 * 1024), ("1 MB", 1024 * 1024), ("5 MB", 5 * 1024 * 1024)]


def ms(t0):
    return (time.perf_counter() - t0) * 1000


def stats(values):
    return {"mean": round(statistics.mean(values), 1), "min": round(min(values), 1), "max": round(max(values), 1)}


def healthy(fid):
    return call("GET", f"/files/{fid}/replicas")[1]["summary"]["healthy"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="")
    add_auth_arguments(ap)
    args = ap.parse_args()
    authenticate(args)

    results = []
    for label, size in SIZES:
        rows = {k: [] for k in ("client_upload", "server_total", "replication", "ledger", "verify", "recover")}
        for run in range(args.runs):
            content = os.urandom(size // 2).hex().encode()[:size]           # random text, exact size
            t0 = time.perf_counter()
            status, up, _ = call("POST", "/files/upload", form_file=(f"bench_{label.replace(' ', '')}_{run}.txt", content))
            client = ms(t0)
            if status != 200:
                sys.exit(f"upload failed: {up}")
            fid = up["file_id"]
            rows["client_upload"].append(client)
            rows["server_total"].append(up["timing_ms"]["total"])
            rows["replication"].append(up["timing_ms"]["replication"])
            rows["ledger"].append(up["timing_ms"]["ledger_commit"])
            t0 = time.perf_counter()
            call("POST", f"/files/{fid}/verify")
            rows["verify"].append(ms(t0))
            # corrupt one replica, then time the recovery (fetch verified copy + repair + re-verify + commit)
            call("POST", "/simulation/malicious-node", {"node_id": "node3", "enabled": True})
            call("POST", "/simulation/corrupt-replica", {"node_id": "node3", "file_id": fid, "confirm": True})
            call("POST", "/simulation/malicious-node", {"node_id": "node3", "enabled": False})
            t0 = time.perf_counter()
            _, rec, _ = call("POST", f"/files/{fid}/recover")
            rows["recover"].append(ms(t0))
            assert rec["repaired_nodes"] == ["node3"], rec
        results.append({"size": label, "bytes": size, "runs": args.runs, **{k: stats(v) for k, v in rows.items()}})
        print(f"{label:>7}: upload {results[-1]['client_upload']['mean']} ms, verify {results[-1]['verify']['mean']} ms, "
              f"recover {results[-1]['recover']['mean']} ms")

    # Replica availability before / during / after a simulated failure of node2
    _, up, _ = call("POST", "/files/upload", form_file=("availability.txt", b"availability test\n" * 100))
    fid = up["file_id"]
    before = healthy(fid)
    call("POST", "/simulation/node-failure", {"node_id": "node2"})
    during = healthy(fid)
    _, dl, h = call("GET", f"/files/{fid}/download", raw=True)
    served_by = h.get("X-BlockStore-Source-Node") or h.get("x-blockstore-source-node")
    call("POST", "/simulation/node-restart", {"node_id": "node2"})
    after = healthy(fid)
    nodes = call("GET", "/nodes")[1]

    out = {
        "label": args.label, "measured_at": datetime.now().isoformat(timespec="seconds"),
        "machine": f"{platform.system()} {platform.release()}, Python {platform.python_version()}",
        "results": results,
        "availability": {"valid_replicas_before": before, "during_node2_failure": during, "after_restart": after,
                         "download_during_failure_served_by": served_by},
        "health_checks": {n["node_id"]: {"ok": n["health_checks_ok"], "failed": n["health_checks_failed"]} for n in nodes},
    }
    res_dir = ROOT / "docs" / "results"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "benchmark.json").write_text(json.dumps(out, indent=2))

    lines = [f"# Benchmark results", "", f"- Environment: {args.label or 'not labelled'}",
             f"- Machine: {out['machine']}", f"- Measured: {out['measured_at']}",
             f"- Runs per size: {args.runs} (mean, with min–max in brackets, all in milliseconds)", "",
             "| File size | Upload (client) | Upload (server) | Replication to 5 nodes | Ledger vote + commit | Integrity verification | Recovery of 1 corrupted replica |",
             "|---|---|---|---|---|---|---|"]
    fmt = lambda s: f"{s['mean']} ({s['min']}–{s['max']})"  # noqa: E731
    for r in results:
        lines.append(f"| {r['size']} | {fmt(r['client_upload'])} | {fmt(r['server_total'])} | {fmt(r['replication'])} | "
                     f"{fmt(r['ledger'])} | {fmt(r['verify'])} | {fmt(r['recover'])} |")
    a = out["availability"]
    lines += ["", "## Valid replicas around a simulated failure of node2", "",
              "| Before | During failure | After restart | Download during failure served by |", "|---|---|---|---|",
              f"| {a['valid_replicas_before']} | {a['during_node2_failure']} | {a['after_restart']} | {a['download_during_failure_served_by']} |",
              "", "## Health checks counted by the coordinator since it started", "",
              "| Node | Successful | Failed |", "|---|---|---|"]
    for nid, h in out["health_checks"].items():
        lines.append(f"| {nid} | {h['ok']} | {h['failed']} |")
    lines += ["", "Failed checks come from the deliberate node stops and simulated failures in the test runs.", ""]
    (res_dir / "benchmark.md").write_text("\n".join(lines))
    print("written docs/results/benchmark.md")


if __name__ == "__main__":
    main()
