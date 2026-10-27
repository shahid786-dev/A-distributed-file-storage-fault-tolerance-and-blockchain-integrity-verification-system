"""Per-node configuration, read from environment variables.

Each of the five node processes/containers runs the same code with different values:
  NODE_ID        node1 .. node5   (its identity)
  NODE_DATA_DIR  where this node keeps its own files and ledger
  NODE_SECRET    this node's private vote-signing key
  CONTROL_TOKEN  shared token the coordinator must send for write/control requests
"""
import os
import sys
from pathlib import Path

# Make the shared blockchain module importable (repo root or /app in Docker)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.blockcore import NODE_IDS  # noqa: E402

NODE_ID = os.environ.get("NODE_ID", "node1")
if NODE_ID not in NODE_IDS:
    raise SystemExit(f"NODE_ID must be one of {NODE_IDS}, got {NODE_ID!r}")

DATA_DIR = Path(os.environ.get("NODE_DATA_DIR", f"./runtime/{NODE_ID}")).resolve()
FILES_DIR = DATA_DIR / "files"
LEDGER_PATH = DATA_DIR / "ledger.json"
NODE_SECRET = os.environ.get("NODE_SECRET", f"demo-secret-{NODE_ID}")
CONTROL_TOKEN = os.environ.get("CONTROL_TOKEN", "blockstore5-demo-token")
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", str(10 * 1024 * 1024)))

FILES_DIR.mkdir(parents=True, exist_ok=True)
