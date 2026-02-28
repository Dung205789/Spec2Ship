from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings

router = APIRouter()


@router.get("/text")
def read_text(path: str) -> PlainTextResponse:
    """Read a text artifact.

    Security: only allow reading files under ARTIFACTS_DIR.
    """
    p = Path(path)

    # The DB stores absolute paths. If a client sends a relative path, resolve it under artifacts_dir.
    if not p.is_absolute():
        p = Path(settings.artifacts_dir) / p

    try:
        root = Path(settings.artifacts_dir).resolve()
        rp = p.resolve()
        if root not in rp.parents and rp != root:
            raise HTTPException(status_code=403, detail="Access denied")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if not rp.exists() or not rp.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return PlainTextResponse(rp.read_text(encoding="utf-8", errors="replace"))
