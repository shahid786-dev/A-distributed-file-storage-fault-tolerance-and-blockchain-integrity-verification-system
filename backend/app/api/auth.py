"""Organization login, logout, and current-user endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from ..database import db
from ..models.schemas import LoginRequest
from ..services.auth import require_user
from ..services.auth_service import create_session, find_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("invalid-user-placeholder")


@router.get("/organizations", summary="Organizations available for sign-in")
def organizations():
    return db.rows("SELECT id, name FROM organizations ORDER BY id")


@router.post("/login", summary="Create an eight-hour organization session")
def login(req: LoginRequest):
    user = find_user(req.email)
    if user and user["organization_id"] != req.organization:
        user = None
    password_ok = verify_password(req.password, user["password_hash"] if user else _DUMMY_PASSWORD_HASH)
    if not user or not password_ok:
        db.log_event("warning", "auth", "Organization sign-in failed",
                     {"organization_id": user["organization_id"]} if user else None,
                     user["organization_id"] if user else None)
        raise HTTPException(401, "Invalid email or password")
    if not user["active"]:
        raise HTTPException(403, "Account is disabled")

    token, expires_at = create_session(user["user_id"])
    db.log_event("success", "auth", "Organization user signed in",
                 {"user_id": user["user_id"]}, user["organization_id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "role": user["role"],
            "organization": user["organization_id"],
            "organization_name": user["organization_name"],
        },
    }


@router.get("/me", summary="Return the authenticated organization user")
def me(user: dict = Depends(require_user)):
    return {key: user[key] for key in
            ("user_id", "email", "role", "organization", "organization_name")}


@router.post("/logout", summary="Revoke the current bearer session")
def logout(user: dict = Depends(require_user)):
    db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (user["session_token_hash"],))
    db.log_event("info", "auth", "Organization user signed out",
                 {"user_id": user["user_id"]}, user["organization_id"])
    return {"ok": True}
