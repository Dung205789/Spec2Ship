from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.core.config import settings
from app.services.workspaces import reset_sample_workspace, list_workspaces, import_workspace_zip
from pathlib import Path
import shutil
import os

router = APIRouter()


@router.post("/sample/reset")
def reset_sample() -> dict:
    """Reset the sample workspace back to its known starting state."""
    try:
        reset_sample_workspace(settings.workspace_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")
    return {"ok": True}


@router.get("/")
def get_workspaces() -> list[dict]:
    """List available workspaces.

    Includes:
    - sample_workspace
    - customer-uploaded workspaces under WORKSPACES_ROOT
    """
    infos = list_workspaces(settings.workspace_path, settings.workspaces_root)
    return [{"name": w.name, "path": w.path, "exists": w.exists} for w in infos]


@router.post("/upload")
async def upload_workspace(
    file: UploadFile = File(...),
    name: str | None = Form(None),
) -> dict:
    """Upload a ZIP archive and import it as a new workspace.

    The extracted workspace becomes selectable in the web UI.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported")

    # Save upload to /data/uploads
    uploads_dir = Path("/data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = uploads_dir / f"upload_{os.getpid()}_{file.filename}"

    # Stream to disk with a hard cap.
    total = 0
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.workspace_upload_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload too large (>{settings.workspace_upload_max_bytes} bytes)",
                    )
                out.write(chunk)

        res = import_workspace_zip(
            str(tmp_path),
            requested_name=name,
            workspaces_root=settings.workspaces_root,
            max_files=settings.workspace_extract_max_files,
            max_total_bytes=settings.workspace_extract_max_bytes,
            max_file_bytes=settings.workspace_extract_max_file_bytes,
        )
        return {
            "ok": True,
            "name": res.name,
            "path": res.path,
            "file_count": res.file_count,
            "extracted_bytes": res.extracted_bytes,
            "skipped_files": res.skipped_files,
            "note": res.note,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload/import failed: {e}")
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


@router.delete("/{workspace_name}")
def delete_workspace(workspace_name: str) -> dict:
    """Delete an uploaded workspace (sample_workspace cannot be deleted)."""
    if workspace_name == "sample_workspace":
        raise HTTPException(status_code=400, detail="Cannot delete sample_workspace")
    # Only allow simple folder names.
    if "/" in workspace_name or "\\" in workspace_name or ".." in workspace_name:
        raise HTTPException(status_code=400, detail="Invalid workspace name")
    target = Path(settings.workspaces_root) / workspace_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a workspace directory")
    shutil.rmtree(target, ignore_errors=True)
    return {"ok": True}
