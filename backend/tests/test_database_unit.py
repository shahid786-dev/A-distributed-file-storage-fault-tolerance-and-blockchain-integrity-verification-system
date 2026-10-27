import sqlite3

from app.database import db


def test_init_db_migrates_existing_files_to_first_document_version(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    file_id = "a" * 32
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE files (
                   file_id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
                   sha256 TEXT NOT NULL, content_type TEXT, uploaded_at TEXT NOT NULL,
                   ledger_block INTEGER)"""
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_id, "legacy.txt", 6, "b" * 64, "text/plain", "2026-01-01T00:00:00Z", 1),
        )
    monkeypatch.setattr(db, "DB_PATH", str(database))
    monkeypatch.setenv("TRUSTGRID_DEMO_USERS", "")

    db.init_db()

    migrated = db.one("SELECT document_id, version_number, previous_file_id FROM files WHERE file_id=?",
                      (file_id,))
    assert migrated == {"document_id": file_id, "version_number": 1, "previous_file_id": None}

