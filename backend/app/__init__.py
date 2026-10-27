"""BlockStore-5 coordinator backend."""
import sys
from pathlib import Path

# Make `shared.blockcore` importable from the repo root, or from /app inside Docker
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
