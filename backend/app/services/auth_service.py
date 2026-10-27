"""Password hashing and opaque bearer sessions for organization accounts."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from ..database import db

_PBKDF2_ROUNDS = 600_000
_SESSION_LIFETIME = timedelta(hours=8)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ROUNDS, base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$")
        rounds = int(rounds)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= rounds <= 2_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def find_user(email: str) -> dict | None:
    return db.one(
        """SELECT u.user_id, u.organization_id, u.email, u.password_hash, u.role, u.active,
                  o.name AS organization_name
           FROM users u JOIN organizations o ON o.id = u.organization_id
           WHERE u.email = ?""",
        (email.strip().lower(),),
    )


def create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + _SESSION_LIFETIME).isoformat(timespec="seconds").replace("+00:00", "Z")
    db.execute("INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)",
               (token_hash, user_id, expires_at, db.now()))
    return token, expires_at


def session_user(token: str) -> dict | None:
    try:
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    except UnicodeEncodeError:
        return None
    row = db.one(
        """SELECT u.user_id, u.organization_id, u.email, u.role, o.name AS organization_name,
                  s.token_hash AS session_token_hash
           FROM auth_sessions s JOIN users u ON u.user_id = s.user_id
           JOIN organizations o ON o.id = u.organization_id
           WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1""",
        (token_hash, db.now()),
    )
    if row:
        row["organization"] = row["organization_id"]
    return row


def visible_file_ids(organization_id: str) -> set[str]:
    rows = db.rows(
        """SELECT f.file_id FROM files f
           WHERE f.owner_org_id=? OR EXISTS (
               SELECT 1 FROM files shared_file JOIN file_shares s ON s.file_id=shared_file.file_id
               WHERE shared_file.document_id=f.document_id AND s.organization_id=?
           )""",
        (organization_id, organization_id),
    )
    return {row["file_id"] for row in rows}
