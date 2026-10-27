"""SQLite metadata store for the coordinator.

Holds the TRUSTED original hash of every file (the trust anchor), the latest
replica check results, consensus proposals and the application event log.
File contents are never stored here - they live on the five nodes.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from ..config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    created_at     TEXT NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    file_id      TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL DEFAULT '',
    version_number INTEGER NOT NULL DEFAULT 1,
    previous_file_id TEXT,
    name         TEXT NOT NULL,
    size         INTEGER NOT NULL,
    sha256       TEXT NOT NULL,          -- trusted original hash, written once at upload
    content_type TEXT,
    uploaded_at  TEXT NOT NULL,
    ledger_block INTEGER,
    owner_org_id TEXT NOT NULL DEFAULT 'manufacturer' REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS file_shares (
    file_id       TEXT NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    permission    TEXT NOT NULL CHECK (permission IN ('read')),
    created_by    TEXT NOT NULL REFERENCES users(user_id),
    created_at    TEXT NOT NULL,
    PRIMARY KEY (file_id, organization_id)
);
CREATE TABLE IF NOT EXISTS replicas (
    file_id       TEXT NOT NULL,
    node_id       TEXT NOT NULL,
    status        TEXT NOT NULL,         -- match | mismatch | missing | unavailable
    computed_hash TEXT,                  -- hash the COORDINATOR calculated from the bytes
    reported_hash TEXT,                  -- hash the node claimed (not trusted)
    detail        TEXT,
    checked_at    TEXT NOT NULL,
    PRIMARY KEY (file_id, node_id)
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    level     TEXT NOT NULL,             -- info | success | warning | error
    category  TEXT NOT NULL,             -- upload | integrity | recovery | node | consensus | simulation
    message   TEXT NOT NULL,
    details   TEXT,
    organization_id TEXT REFERENCES organizations(id)
);
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id    TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    proposer       TEXT NOT NULL,
    kind           TEXT NOT NULL,        -- normal | manual | simulation
    block          TEXT NOT NULL,
    votes          TEXT NOT NULL,
    accept_count   INTEGER NOT NULL,
    reject_count   INTEGER NOT NULL,
    outcome        TEXT NOT NULL,        -- committed | rejected
    reason         TEXT,
    commit_results TEXT,
    heads_before   TEXT,
    heads_after    TEXT
);
CREATE TABLE IF NOT EXISTS health_stats (
    node_id TEXT PRIMARY KEY,
    ok      INTEGER NOT NULL DEFAULT 0,
    failed  INTEGER NOT NULL DEFAULT 0
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        file_columns = {row["name"] for row in conn.execute("PRAGMA table_info(files)")}
        if "document_id" not in file_columns:
            conn.execute("ALTER TABLE files ADD COLUMN document_id TEXT NOT NULL DEFAULT ''")
        if "version_number" not in file_columns:
            conn.execute("ALTER TABLE files ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1")
        if "previous_file_id" not in file_columns:
            conn.execute("ALTER TABLE files ADD COLUMN previous_file_id TEXT")
        if "owner_org_id" not in file_columns:
            conn.execute("ALTER TABLE files ADD COLUMN owner_org_id TEXT NOT NULL DEFAULT 'manufacturer'")
        conn.execute("UPDATE files SET document_id=file_id WHERE document_id=''")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_files_document_version
                        ON files(document_id, version_number)""")
        event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
        if "organization_id" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN organization_id TEXT")
        now_value = now()
        conn.executemany("INSERT OR IGNORE INTO organizations (id, name, created_at) VALUES (?,?,?)", [
            ("manufacturer", "Northstar Manufacturing", now_value),
            ("logistics", "Wayline Logistics", now_value),
            ("inspection", "Clearview Quality Inspection", now_value),
            ("distributor", "Harborlight Distribution", now_value),
        ])
        _seed_initial_users(conn, now_value)


def _seed_initial_users(conn: sqlite3.Connection, created_at: str) -> None:
    """Seed explicitly configured demo users once; never replace existing accounts."""
    raw = os.environ.get("TRUSTGRID_DEMO_USERS", "")
    if not raw:
        return
    try:
        users = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TRUSTGRID_DEMO_USERS must be a JSON array") from exc
    if not isinstance(users, list):
        raise RuntimeError("TRUSTGRID_DEMO_USERS must be a JSON array")
    from ..services.auth_service import hash_password

    for user in users:
        if (not isinstance(user, dict)
                or not {"organization", "email", "password"} <= set(user)
                or set(user) - {"organization", "email", "password", "role"}):
            raise RuntimeError("Each demo user requires organization, email, password, and optional role fields")
        organization = user["organization"]
        email = user["email"].strip().lower() if isinstance(user["email"], str) else ""
        password = user["password"]
        role = user.get("role", "admin")
        if organization not in {"manufacturer", "logistics", "inspection", "distributor"}:
            raise RuntimeError(f"Unknown demo organization '{organization}'")
        if not email or not isinstance(password, str) or len(password) < 12:
            raise RuntimeError("Demo users require an email and a password of at least 12 characters")
        if len(password) > 256 or role not in {"admin", "member"}:
            raise RuntimeError("Demo user password or role is invalid")
        conn.execute(
            """INSERT OR IGNORE INTO users
               (user_id, organization_id, email, password_hash, role, created_at)
               VALUES (lower(hex(randomblob(16))),?,?,?,?,?)""",
            (organization, email, hash_password(password), role, created_at),
        )


def rows(query: str, params=()) -> list:
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def one(query: str, params=()):
    result = rows(query, params)
    return result[0] if result else None


def execute(query: str, params=()):
    with connect() as conn:
        conn.execute(query, params)


# --- helpers used by several services -------------------------------------
def log_event(level: str, category: str, message: str, details: dict | None = None,
              organization_id: str | None = None):
    execute("""INSERT INTO events (ts, level, category, message, details, organization_id)
               VALUES (?,?,?,?,?,?)""",
            (now(), level, category, message, json.dumps(details) if details else None, organization_id))


def upsert_replica(file_id, node_id, status, computed_hash=None, reported_hash=None, detail=None):
    execute("""INSERT INTO replicas (file_id, node_id, status, computed_hash, reported_hash, detail, checked_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(file_id, node_id) DO UPDATE SET status=excluded.status,
                 computed_hash=excluded.computed_hash, reported_hash=excluded.reported_hash,
                 detail=excluded.detail, checked_at=excluded.checked_at""",
            (file_id, node_id, status, computed_hash, reported_hash, detail, now()))


def count_health(node_id: str, ok: bool):
    column = "ok" if ok else "failed"
    execute(f"""INSERT INTO health_stats (node_id, {column}) VALUES (?, 1)
                ON CONFLICT(node_id) DO UPDATE SET {column} = {column} + 1""", (node_id,))
