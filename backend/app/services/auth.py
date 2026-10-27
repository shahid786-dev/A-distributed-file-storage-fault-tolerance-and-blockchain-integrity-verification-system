"""FastAPI dependencies for authenticated, organization-scoped API access."""
from fastapi import Depends, Header, HTTPException

from ..database import db
from .auth_service import session_user


def require_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    user = session_user(token) if token else None
    if not user:
        raise HTTPException(401, "Session is invalid or expired", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        db.log_event("warning", "access", "Organization member attempted an administrator action",
                     {"user_id": user["user_id"]}, user["organization_id"])
        raise HTTPException(403, "Organization administrator role required")
    return user
