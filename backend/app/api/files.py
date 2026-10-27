"""File endpoints: upload, list, details, replicas, verify, download, recover."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from ..config import MAX_UPLOAD_BYTES
from ..database import db
from ..models.schemas import FILE_ID_PATTERN, ShareRequest
from ..services.auth import require_admin, require_user
from ..services import file_service

router = APIRouter(prefix="/api/files", tags=["files"])
FileIdPath = Path(..., pattern=FILE_ID_PATTERN, description="32-character file id")


def _require(file_id: str, user: dict, write: bool = False) -> dict:
    f = file_service.get_file(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    if f["owner_org_id"] == user["organization_id"]:
        f["access"] = "owner"
        return f
    if write or not db.one(
            """SELECT 1 FROM files shared_file JOIN file_shares s ON s.file_id=shared_file.file_id
               WHERE shared_file.document_id=? AND s.organization_id=?""",
            (f["document_id"], user["organization_id"])):
        db.log_event("warning", "access", "Organization attempted to access an unauthorized document",
                     {"file_id": file_id, "user_id": user["user_id"]}, user["organization_id"])
        raise HTTPException(status_code=404, detail="File not found")
    f["access"] = "shared"
    return f


@router.post("/upload", summary="Upload a file and replicate it to the five nodes")
async def upload(file: UploadFile = File(...), user: dict = Depends(require_user)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        result = file_service.upload(file.filename, file.content_type, data, user["organization_id"])
        db.log_event("success", "upload", f"Uploaded '{result['name']}'",
                     {"file_id": result["file_id"], "sha256": result["sha256"]}, user["organization_id"])
        return result
    except file_service.UploadError as exc:
        db.log_event("error", "upload", f"Upload rejected: {exc.message}",
                     {"name": file.filename}, user["organization_id"])
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, **(exc.details or {})})


@router.get("", summary="List uploaded files with replica counts")
def list_files(user: dict = Depends(require_user)):
    files = db.rows(
        """SELECT DISTINCT f.*,
                  CASE WHEN f.owner_org_id=? THEN 'owner' ELSE 'shared' END AS access,
                  CASE WHEN f.version_number=(SELECT MAX(latest.version_number) FROM files latest
                                               WHERE latest.document_id=f.document_id)
                       THEN 1 ELSE 0 END AS is_latest
           FROM files f
           WHERE f.owner_org_id=? OR EXISTS (
               SELECT 1 FROM files shared_file JOIN file_shares s ON s.file_id=shared_file.file_id
               WHERE shared_file.document_id=f.document_id AND s.organization_id=?
           )
           ORDER BY f.uploaded_at DESC""",
        (user["organization_id"], user["organization_id"], user["organization_id"]))
    visible_ids = [f["file_id"] for f in files]
    if not visible_ids:
        return []
    marks = ",".join("?" for _ in visible_ids)
    reps = db.rows(f"""SELECT file_id, status, COUNT(*) AS n FROM replicas
                       WHERE file_id IN ({marks}) GROUP BY file_id, status""", visible_ids)
    for f in files:
        counts = {r["status"]: r["n"] for r in reps if r["file_id"] == f["file_id"]}
        f["replica_counts"] = {k: counts.get(k, 0) for k in ("match", "mismatch", "missing", "unavailable")}
    return files


@router.post("/{file_id}/versions", summary="Create the next immutable version of an owned document")
async def create_version(file_id: str = FileIdPath, expected_version: int = Query(..., ge=1),
                         file: UploadFile = File(...), user: dict = Depends(require_user)):
    parent = _require(file_id, user, write=True)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        result = file_service.upload_version(file_id, expected_version, file.filename, file.content_type,
                                            data, user["organization_id"])
        db.log_event("success", "version", f"Created version {result['version_number']} of '{result['name']}'",
                     {"file_id": result["file_id"], "document_id": result["document_id"],
                      "previous_file_id": file_id}, user["organization_id"])
        return result
    except file_service.VersionConflict as exc:
        db.log_event("warning", "version", f"Stale version request for document {parent['document_id']}",
                     {"selected_parent": file_id, "latest": exc.latest}, user["organization_id"])
        raise HTTPException(status_code=409, detail={
            "message": str(exc), "latest_file_id": exc.latest["file_id"],
            "latest_version": exc.latest["version_number"],
        }) from exc
    except file_service.UploadError as exc:
        db.log_event("error", "version", f"Version upload rejected: {exc.message}",
                     {"parent_file_id": file_id, "name": file.filename}, user["organization_id"])
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, **(exc.details or {})})


@router.get("/{file_id}", summary="File details and last known replica status")
def file_details(file_id: str = FileIdPath, user: dict = Depends(require_user)):
    f = _require(file_id, user)
    f["replicas"] = db.rows("SELECT * FROM replicas WHERE file_id = ? ORDER BY node_id", (file_id,))
    return f


@router.get("/{file_id}/replicas", summary="Live replica check (does not write to the ledger)")
def replicas(file_id: str = FileIdPath, user: dict = Depends(require_user)):
    _require(file_id, user)
    return file_service.check_replicas(file_id)


@router.post("/{file_id}/verify", summary="Integrity check on all five nodes, recorded on the ledger")
def verify(file_id: str = FileIdPath, user: dict = Depends(require_user)):
    _require(file_id, user)
    report = file_service.verify(file_id)
    db.log_event("info", "integrity", f"Integrity check requested for {file_id}",
                 {"file_id": file_id}, user["organization_id"])
    return report


@router.get("/{file_id}/download", summary="Download a copy verified against the trusted hash")
def download(file_id: str = FileIdPath, user: dict = Depends(require_user)):
    f = _require(file_id, user)
    found = file_service.fetch_verified(file_id)
    if not found["ok"]:
        db.log_event("error", "recovery", f"Download of '{f['name']}' failed: no verified replica",
                     {"file_id": file_id, "attempts": found["attempts"]}, user["organization_id"])
        raise HTTPException(status_code=503, detail={"message": "No verified replica is available",
                                                     "attempts": found["attempts"]})
    db.log_event("info", "download", f"Downloaded '{f['name']}' from a hash-verified replica",
                 {"file_id": file_id, "source_node": found["source_node"]}, user["organization_id"])
    skipped = [a for a in found["attempts"] if a["result"] != "verified"]
    if skipped:
        db.log_event("info", "recovery",
                     f"Download of '{f['name']}' served by {found['source_node']} after skipping "
                     + ", ".join(f"{a['node_id']} ({a['result']})" for a in skipped))
    return Response(
        content=found["content"],
        media_type=f["content_type"] or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f['name'])}",
            "X-BlockStore-Source-Node": found["source_node"],
            "X-BlockStore-Verified-SHA256": f["sha256"],
            "X-BlockStore-Skipped": ",".join(f"{a['node_id']}:{a['result']}" for a in skipped),
            "Access-Control-Expose-Headers": "X-BlockStore-Source-Node, X-BlockStore-Verified-SHA256, X-BlockStore-Skipped",
        },
    )


@router.post("/{file_id}/recover", summary="Recover from an honest node and repair bad replicas")
def recover(file_id: str = FileIdPath, user: dict = Depends(require_admin)):
    _require(file_id, user, write=True)
    result = file_service.recover(file_id)
    if not result["ok"]:
        return JSONResponse(status_code=503, content=result)
    db.log_event("info", "recovery", f"Organization requested recovery for {file_id}",
                 {"file_id": file_id}, user["organization_id"])
    return result


@router.get("/{file_id}/shares", summary="List organizations with read access (owner only)")
def list_shares(file_id: str = FileIdPath, user: dict = Depends(require_admin)):
    f = _require(file_id, user, write=True)
    return db.rows(
        """SELECT s.organization_id AS organization, o.name, s.permission, s.created_at
           FROM file_shares s JOIN organizations o ON o.id=s.organization_id
           JOIN files shared_file ON shared_file.file_id=s.file_id
           WHERE shared_file.document_id=? GROUP BY s.organization_id ORDER BY s.organization_id""",
        (f["document_id"],))


@router.post("/{file_id}/shares", summary="Grant an organization read access (owner only)")
def share_file(req: ShareRequest, file_id: str = FileIdPath, user: dict = Depends(require_admin)):
    f = _require(file_id, user, write=True)
    if req.organization == user["organization_id"]:
        raise HTTPException(400, "Choose a different organization to share with")
    db.execute(
        """INSERT INTO file_shares (file_id, organization_id, permission, created_by, created_at)
           VALUES (?,?,?,?,?) ON CONFLICT(file_id, organization_id) DO UPDATE SET
           permission=excluded.permission, created_by=excluded.created_by, created_at=excluded.created_at""",
        (f["file_id"], req.organization, req.permission, user["user_id"], db.now()))
    db.log_event("success", "access", f"Shared {file_id} with {req.organization}",
                 {"file_id": file_id, "target_organization": req.organization, "permission": req.permission},
                 user["organization_id"])
    return {"file_id": file_id, "organization": req.organization, "permission": req.permission}


@router.delete("/{file_id}/shares/{organization}", summary="Revoke an organization's read access (owner only)")
def revoke_share(file_id: str = FileIdPath, organization: str = Path(..., pattern="^(manufacturer|logistics|inspection|distributor)$"),
                 user: dict = Depends(require_admin)):
    f = _require(file_id, user, write=True)
    db.execute(
        """DELETE FROM file_shares WHERE organization_id=? AND file_id IN
           (SELECT file_id FROM files WHERE document_id=?)""",
        (organization, f["document_id"]))
    db.log_event("info", "access", f"Revoked {organization} access to {file_id}",
                 {"file_id": file_id, "target_organization": organization}, user["organization_id"])
    return {"file_id": file_id, "organization": organization, "revoked": True}
