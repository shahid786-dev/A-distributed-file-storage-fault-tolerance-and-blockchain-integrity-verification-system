# Benchmark results

- Environment: Docker Compose, 5 node containers + backend, Linux VM with 2 vCPU / 8 GB RAM (development sandbox)
- Machine: Linux 6.18.44-fc-v139, Python 3.13.16
- Measured: 2026-10-21T21:59:32
- Runs per size: 3 (mean, with min–max in brackets, all in milliseconds)

| File size | Upload (client) | Upload (server) | Replication to 5 nodes | Ledger vote + commit | Integrity verification | Recovery of 1 corrupted replica |
|---|---|---|---|---|---|---|
| 1 KB | 89.4 (78.4–99.6) | 85.6 (75.7–94.1) | 11.4 (10.4–13.3) | 61.6 (56.0–65.4) | 85.9 (80.5–94.9) | 114.1 (103.1–120.3) |
| 100 KB | 103.9 (89.8–120.4) | 100.2 (85.9–117.0) | 12.6 (11.6–13.7) | 73.2 (56.9–90.1) | 90.6 (86.4–96.2) | 111.8 (110.7–113.2) |
| 1 MB | 132.9 (127.3–138.8) | 123.1 (119.4–125.2) | 29.6 (22.9–35.3) | 77.2 (69.5–88.8) | 130.8 (126.8–134.4) | 186.1 (150.5–217.8) |
| 5 MB | 227.0 (197.5–254.4) | 191.7 (178.3–200.9) | 90.6 (74.9–101.2) | 81.4 (74.9–88.9) | 195.9 (188.1–210.6) | 382.2 (338.2–414.3) |

## Valid replicas around a simulated failure of node2

| Before | During failure | After restart | Download during failure served by |
|---|---|---|---|
| 5 | 4 | 5 | node1 |

## Health checks counted by the coordinator since it started

| Node | Successful | Failed |
|---|---|---|
| node1 | 69 | 0 |
| node2 | 67 | 2 |
| node3 | 69 | 0 |
| node4 | 68 | 1 |
| node5 | 69 | 0 |

Failed checks come from the deliberate node stops and simulated failures in the test runs.
