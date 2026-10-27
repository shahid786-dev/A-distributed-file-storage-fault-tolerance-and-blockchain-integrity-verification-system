"""BlockStore-5 storage node package."""
import sys
from pathlib import Path

# Make `shared.blockcore` importable whether we run from the repo or inside Docker (/app)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
