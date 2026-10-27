# Installation and setup

## Requirements (all free)

| Tool | Version | Needed for |
|---|---|---|
| Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux) | recent | Option A |
| Python | 3.11 or newer | Option B, tests, scripts |
| Node.js + npm | 18 or newer (20 LTS recommended) | Option B frontend, frontend tests |
| Git | any | optional |

## Option A — Docker Compose (recommended for the presentation)

### Windows PowerShell

```powershell
cd C:\path\to\BlockStore-5
Copy-Item .env.example .env
# Edit .env: replace demo secrets and configure TRUSTGRID_DEMO_USERS (see below).
docker compose up --build -d       # first build takes a few minutes
docker compose ps                  # all 7 containers should be "Up"; nodes become "(healthy)"
```

### Linux / macOS

```bash
cd ~/BlockStore-5
cp .env.example .env               # edit demo secrets and TRUSTGRID_DEMO_USERS first
docker compose up --build -d
docker compose ps
```

### URLs

| What | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| Backend API docs (Swagger) | http://localhost:8000/docs |
| Backend health | http://localhost:8000/api/health |
| Node 1 … 5 health | http://localhost:8001/health … http://localhost:8005/health |

### Useful commands

```bash
docker compose logs -f backend     # watch the coordinator
docker compose stop node2          # REAL failure of node 2 (container stopped)
docker compose start node2         # bring it back; its ledger is re-synced automatically
docker compose restart             # restart everything (data is kept in volumes)
docker compose down                # stop and remove containers, keep data
docker compose down -v             # stop and DELETE all files, ledgers and metadata
```

## Option B — local mode without Docker

Five nodes and the backend still run as **six separate processes** talking over HTTP.

### Windows PowerShell

```powershell
cd C:\path\to\BlockStore-5
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python run_local.py start          # nodes 8001-8005 + backend 8000 (logs in runtime\logs)

# second terminal
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### Linux / macOS

```bash
cd ~/BlockStore-5
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python run_local.py start
cd frontend && npm install && npm run dev
```

### Local-mode commands

```bash
python run_local.py status
python run_local.py stop-node node2    # REAL failure: the node process is terminated
python run_local.py start-node node2
python run_local.py stop               # stop all six processes
python run_local.py reset              # stop and delete ./runtime (all data)
```

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip the
virtual environment.

## Initial organization accounts

The API does not ship with hard-coded passwords. Configure one or more initial users using the
`TRUSTGRID_DEMO_USERS` JSON-array environment variable before the backend starts. For a Docker deployment, set it in
`.env`; for local Windows PowerShell, set it in the backend terminal before `run_local.py start`:

```powershell
$env:TRUSTGRID_DEMO_USERS='[{"organization":"manufacturer","email":"manufacturer@example.test","password":"REPLACE-WITH-A-UNIQUE-STRONG-PASSWORD"},{"organization":"logistics","email":"logistics@example.test","password":"REPLACE-WITH-A-UNIQUE-STRONG-PASSWORD"},{"organization":"inspection","email":"inspection@example.test","password":"REPLACE-WITH-A-UNIQUE-STRONG-PASSWORD"},{"organization":"distributor","email":"distributor@example.test","password":"REPLACE-WITH-A-UNIQUE-STRONG-PASSWORD"}]'
```

Use distinct passwords of at least 12 characters; keep real passwords out of source control, screenshots, and shell
history. For local Windows runs, collect them without echoing and construct the JSON in memory:

```powershell
$accounts = @()
foreach ($entry in @(
  @{ organization = "manufacturer"; email = "manufacturer@example.test" },
  @{ organization = "logistics"; email = "logistics@example.test" },
  @{ organization = "inspection"; email = "inspection@example.test" },
  @{ organization = "distributor"; email = "distributor@example.test" }
)) {
  $secure = Read-Host "Password for $($entry.organization)" -AsSecureString
  $password = [System.Net.NetworkCredential]::new("", $secure).Password
  $accounts += @{ organization = $entry.organization; email = $entry.email; password = $password }
}
$env:TRUSTGRID_DEMO_USERS = ConvertTo-Json -InputObject $accounts -Compress
Remove-Variable accounts, password, secure
```

Use `"role":"member"` for a non-administrator account; the default is `admin`. Passwords are stored as salted
PBKDF2-SHA256 hashes. Seeding is insert-only and will not reset or overwrite an existing account. To run the host-side
smoke script, set `TRUSTGRID_ORGANIZATION`, `TRUSTGRID_EMAIL`, and `TRUSTGRID_PASSWORD` in that terminal or pass
`--organization`, `--email`, and `--password`; missing credentials are prompted for interactively.

## Health checks

```bash
curl http://localhost:8000/api/health       # {"status":"ok","nodes_online":5,...}
curl http://localhost:8003/health           # one node directly
python scripts/smoke_test.py --mode docker  # prompts for a configured account if env vars are unset
```
PowerShell: use `Invoke-RestMethod http://localhost:8000/api/health` or `curl.exe`.

## Running the tests

```bash
cd backend
python -m pytest -v        # unit tests + a live cluster on ports 9000-9005 (does not touch your demo data)
cd ../frontend
npm test
```

## Configuration

| Variable | Where | Default | Meaning |
|---|---|---|---|
| `NODE1_SECRET` … `NODE5_SECRET` | `.env` | `demo-secret-nodeN` | per-node vote-signing keys (backend and node must match) |
| `CONTROL_TOKEN` | `.env` | `blockstore5-demo-token` | token the backend uses for node write/control calls |
| `NODE_URLS` | backend | local ports 8001-8005 | where the five nodes are |
| `MAX_UPLOAD_BYTES` | backend | 10 MB | upload limit |
| `HEALTH_INTERVAL_SECONDS` | backend | 2 | health-check period |
| `NODE_TIMEOUT_SECONDS` | backend | 3 | per-request timeout to a node |
| `BACKEND_URL` | Vite dev server | `http://127.0.0.1:8000` | where `/api` is forwarded |
| `TRUSTGRID_DEMO_USERS` | backend / Compose `.env` | unset | insert-only JSON array of initial organization accounts |
| `TRUSTGRID_ORGANIZATION`, `TRUSTGRID_EMAIL`, `TRUSTGRID_PASSWORD` | host terminal | unset | smoke/benchmark script login; omitted values prompt interactively |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another program uses the port. Windows: `netstat -ano \| findstr :8000` then `taskkill /PID <pid> /F`. Linux/macOS: `lsof -i :8000`. Or change the left side of the port mapping in `docker-compose.yml` (e.g. `"9000:8000"`) and, for local mode, `BACKEND_PORT=9000`. |
| Dashboard red banner "cannot reach the coordinator" | Backend not running or still starting. Check `docker compose ps` / `python run_local.py status` and `runtime/logs/backend.log`. |
| A node keeps showing offline | `docker compose logs node3`; in local mode see `runtime/logs/node3.log`. |
| Upload fails with "at least 3 are required" | Fewer than 3 nodes online — start them again. |
| `npm run dev` says port 5173 in use | `npm run dev -- --port 5174` |
| Docker build cannot download images | Docker needs internet for the first build (python:3.12-slim, node:20-alpine, nginx). Use Option B offline. |
| Want a clean demo | `docker compose down -v && docker compose up -d` or `python run_local.py reset && python run_local.py start` |
