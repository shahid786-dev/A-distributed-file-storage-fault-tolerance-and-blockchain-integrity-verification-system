"""File storage for ONE node. Every node has its own directory / Docker volume.

Layout inside NODE_DATA_DIR/files:
  <file_id>.bin   the stored bytes (this node's replica)
  <file_id>.json  small record written at store time (size, hash at store time)
"""
import json
import os
import re
from datetime import datetime, timezone

from shared.blockcore import sha256_bytes

from .config import FILES_DIR

FILE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def valid_file_id(file_id: str) -> bool:
    return bool(FILE_ID_RE.match(file_id))


def _paths(file_id: str):
    return FILES_DIR / f"{file_id}.bin", FILES_DIR / f"{file_id}.json"


def save(file_id: str, data: bytes) -> dict:
    data_path, meta_path = _paths(file_id)
    tmp = data_path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, data_path)           # atomic: no half-written replicas
    meta = {
        "file_id": file_id,
        "size": len(data),
        "sha256_at_store": sha256_bytes(data),
        "stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta))
    return meta


def exists(file_id: str) -> bool:
    return _paths(file_id)[0].exists()


def read(file_id: str) -> bytes:
    return _paths(file_id)[0].read_bytes()


def meta(file_id: str) -> dict:
    return json.loads(_paths(file_id)[1].read_text())


def current_hash(file_id: str) -> str:
    """Hash of the bytes on disk right now."""
    return sha256_bytes(read(file_id))


def delete(file_id: str) -> bool:
    removed = False
    for p in _paths(file_id):
        if p.exists():
            p.unlink()
            removed = True
    return removed


def list_files() -> list:
    out = []
    for p in sorted(FILES_DIR.glob("*.bin")):
        fid = p.stem
        out.append({"file_id": fid, "size": p.stat().st_size, "sha256": current_hash(fid)})
    return out


def corrupt(file_id: str) -> dict:
    """TEST ONLY: change this node's replica so its hash no longer matches."""
    data = read(file_id)
    before = sha256_bytes(data)
    tampered = data + b"\n[TAMPERED BY MALICIOUS-NODE SIMULATION]\n"
    data_path, _ = _paths(file_id)
    data_path.write_bytes(tampered)        # note: the .json record is NOT updated
    return {"before": before, "after": sha256_bytes(tampered), "bytes_added": len(tampered) - len(data)}
