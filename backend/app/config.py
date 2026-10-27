"""Coordinator configuration (environment variables with safe local defaults)."""
import os
import sys
from pathlib import Path

# Make `shared.blockcore` importable from the repo root or from /app in Docker
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.blockcore import NODE_IDS  # noqa: E402


def _node_urls() -> dict:
    """NODE_URLS="node1=http://node1:8000,node2=..." (Docker) or local ports 8001-8005."""
    raw = os.environ.get("NODE_URLS", "")
    if raw:
        pairs = dict(item.split("=", 1) for item in raw.split(",") if item.strip())
    else:
        pairs = {f"node{i}": f"http://127.0.0.1:{8000 + i}" for i in range(1, 6)}
    if sorted(pairs) != sorted(NODE_IDS):
        raise SystemExit(f"NODE_URLS must define exactly {NODE_IDS}")
    return pairs


NODE_URLS = _node_urls()

# The registry of node identities: each node's vote-signing secret.
# Votes are only counted if their HMAC tag matches the registered secret.
NODE_SECRETS = {nid: os.environ.get(f"{nid.upper()}_SECRET", f"demo-secret-{nid}") for nid in NODE_IDS}

CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "blockstore5-demo-token")
DB_PATH = Path(os.environ.get("DB_PATH", "./runtime/backend/blockstore.db")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".pdf", ".png", ".jpg", ".jpeg",
                      ".gif", ".docx", ".xlsx", ".pptx", ".zip"}

NODE_TIMEOUT = float(os.environ.get("NODE_TIMEOUT_SECONDS", "3"))       # per request
HEALTH_TIMEOUT = float(os.environ.get("HEALTH_TIMEOUT_SECONDS", "1.5"))
HEALTH_INTERVAL = float(os.environ.get("HEALTH_INTERVAL_SECONDS", "2"))
ENABLE_MONITOR = os.environ.get("ENABLE_HEALTH_MONITOR", "1") == "1"

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
