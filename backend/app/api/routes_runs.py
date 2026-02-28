from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.jobs import run_pipeline_job
from app.models.step import Step
from app.repositories.artifacts import ArtifactRepository
from app.repositories.runs import RunRepository
from app.repositories.steps import StepRepository
from app.schemas.artifact import ArtifactOut
from app.schemas.run import RunCreate, RunOut
from app.schemas.step import StepOut
from app.services.run_overrides import load_run_overrides, save_run_overrides
from app.services.run_workspaces import cleanup_run_workspace, reset_run_workspace
from app.services.workspaces import resolve_workspace_path

log = logging.getLogger(__name__)
router = APIRouter()


def _queue() -> Queue:
    redis = Redis.from_url(settings.redis_url)
    return Queue("default", connection=redis)


def _enqueue(run_id: UUID) -> None:
    q = _queue()
    q.enqueue(
        run_pipeline_job,
        str(run_id),
        job_timeout=settings.rq_job_timeout_seconds,
        result_ttl=86400,
        failure_ttl=86400,
    )


def _ensure_mutable(run_status: str) -> None:
    if run_status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Run is executing. Cancel first.")


@router.post("/", response_model=RunOut)
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> RunOut:
    runs = RunRepository(db)
    run = runs.create(title=payload.title, ticket_text=payload.ticket_text, workspace=payload.workspace)
    return RunOut.model_validate(run)


@router.get("/", response_model=list[RunOut])
def list_runs(limit: int = 50, db: Session = Depends(get_db)) -> list[RunOut]:
    runs = RunRepository(db)
    return [RunOut.model_validate(r) for r in runs.list(limit=limit)]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> RunOut:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunOut.model_validate(run)


@router.get("/{run_id}/steps", response_model=list[StepOut])
def get_steps(run_id: UUID, db: Session = Depends(get_db)) -> list[StepOut]:
    steps = StepRepository(db).list_for_run(run_id)
    return [StepOut.model_validate(s) for s in steps]


@router.get("/{run_id}/artifacts", response_model=list[ArtifactOut])
def get_artifacts(run_id: UUID, db: Session = Depends(get_db)) -> list[ArtifactOut]:
    artifacts = ArtifactRepository(db).list_for_run(run_id)
    return [ArtifactOut.model_validate(a) for a in artifacts]


@router.post("/{run_id}/start")
def start_run(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _ensure_mutable(run.status)
    runs.set_patch_decision(run_id, "no")
    runs.set_status(run_id, "queued")
    _enqueue(run_id)
    return {"ok": True, "message": "queued"}


@router.post("/{run_id}/patch_decision")
def patch_decision(
    run_id: UUID,
    decision: str = Query(..., pattern="^(yes|no|rejected)$"),
    db: Session = Depends(get_db),
) -> dict:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status == "completed":
        raise HTTPException(status_code=409, detail="Run already completed")

    runs.set_patch_decision(run_id, decision)

    if decision == "yes":
        if run.status not in {"queued", "running"}:
            runs.set_status(run_id, "queued")
            _enqueue(run_id)
        return {"ok": True, "message": "approved and queued"}

    if decision == "rejected":
        runs.set_status(run_id, "failed")
        return {"ok": True, "message": "rejected"}

    runs.set_status(run_id, "waiting_approval")
    return {"ok": True, "message": "set to no"}


def _reset_steps_from(db: Session, run_id: UUID, from_order: int) -> None:
    from sqlalchemy import update
    stmt = (
        update(Step)
        .where(Step.run_id == run_id)
        .where(Step.order >= from_order)
        .values(
            status="pending",
            summary="",
            log_path="",
            artifact_path="",
            started_at=None,
            finished_at=None,
            error="",
        )
    )
    db.execute(stmt)
    db.commit()


@router.post("/{run_id}/retry_step")
def retry_step(
    run_id: UUID,
    step: str = Query(..., description="Step name or order number"),
    reset_workspace: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _ensure_mutable(run.status)

    steps_repo = StepRepository(db)
    steps = steps_repo.list_for_run(run_id)
    if not steps:
        raise HTTPException(status_code=409, detail="No steps initialized. Click Start first.")

    target = None
    if step.isdigit():
        target = next((s for s in steps if s.order == int(step)), None)
    else:
        target = next((s for s in steps if s.name.lower() == step.strip().lower()), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Step '{step}' not found")

    if reset_workspace:
        base_ws = resolve_workspace_path(settings.workspace_path, run.workspace, settings.workspaces_root)
        reset_run_workspace(str(run_id), base_ws)

    _reset_steps_from(db, run_id, target.order)

    if target.name in {"Propose patch", "Waiting for approval"} or target.order <= 7:
        runs.set_patch_decision(run_id, "no")

    runs.set_status(run_id, "queued")
    _enqueue(run_id)
    return {"ok": True, "message": f"retry from step {target.order}: {target.name}"}


@router.post("/{run_id}/regenerate_patch")
def regenerate_patch(
    run_id: UUID,
    from_step: str = Query("Propose patch"),
    db: Session = Depends(get_db),
) -> dict:
    # Always reset workspace when regenerating — without this, the new patch would
    # be proposed and applied on top of the (possibly broken) previous patch.
    return retry_step(run_id=run_id, step=from_step, reset_workspace=True, db=db)  # type: ignore[arg-type]


@router.post("/{run_id}/switch_patcher")
def switch_patcher(
    run_id: UUID,
    mode: str = Query(..., pattern="^(rules|ollama|hf)$"),
    db: Session = Depends(get_db),
) -> dict:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _ensure_mutable(run.status)
    ov = load_run_overrides(str(run_id))
    ov["patcher_mode"] = mode
    save_run_overrides(str(run_id), ov)
    return {"ok": True, "message": f"patcher_mode set to {mode}"}


@router.post("/{run_id}/retry")
def retry_run(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    runs = RunRepository(db)
    steps = StepRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _ensure_mutable(run.status)
    steps.reset_for_run(run_id)
    runs.set_patch_decision(run_id, "no")
    runs.set_status(run_id, "queued")
    _enqueue(run_id)
    return {"ok": True, "message": "queued (full retry)"}


@router.post("/{run_id}/cancel")
def cancel_run(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    runs.set_status(run_id, "canceled")
    return {"ok": True, "message": "canceled"}


@router.post("/{run_id}/delete")
def delete_run(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    runs = RunRepository(db)
    steps = StepRepository(db)
    artifacts = ArtifactRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _ensure_mutable(run.status)
    run_dir = Path(settings.artifacts_dir) / str(run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    cleanup_run_workspace(str(run_id))
    artifacts.delete_for_run(run_id)
    steps.delete_for_run(run_id)
    runs.delete(run_id)
    return {"ok": True, "message": "deleted"}


@router.delete("/{run_id}")
def delete_run_http(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    return delete_run(run_id=run_id, db=db)  # type: ignore[misc]


@router.get("/{run_id}/download")
def download_run_zip(run_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = Path(settings.artifacts_dir) / str(run_id)
    run_ws = Path(settings.run_workspaces_dir) / str(run_id)

    if not run_dir.exists() and not run_ws.exists():
        raise HTTPException(status_code=404, detail="No output found for this run")

    tmp = tempfile.mkdtemp(prefix="spec2ship_run_")
    zip_path = Path(tmp) / f"run_{run_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Include artifacts (report, logs, diff, etc.)
        if run_dir.exists():
            for p in run_dir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(Path("artifacts") / p.relative_to(run_dir)))

        # Include patched workspace source so users can deploy/download modified code directly.
        if run_ws.exists():
            for p in run_ws.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(Path("workspace") / p.relative_to(run_ws)))

    return FileResponse(path=str(zip_path), filename=zip_path.name, media_type="application/zip")


@router.get("/{run_id}/summary")
def run_summary(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Lightweight summary: run + step statuses + key artifact names."""
    runs = RunRepository(db)
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = StepRepository(db).list_for_run(run_id)
    artifacts = ArtifactRepository(db).list_for_run(run_id)
    return {
        "id": str(run.id),
        "title": run.title,
        "status": run.status,
        "workspace": run.workspace,
        "steps": [{"name": s.name, "status": s.status, "summary": s.summary, "error": s.error} for s in steps],
        "artifact_kinds": [a.kind for a in artifacts],
    }


@router.get("/{run_id}/live_log")
def live_log(run_id: UUID, kind: str = Query("post_checks_log"), db: Session = Depends(get_db)) -> dict:
    """Return latest content of a log artifact — for polling-based live view."""
    artifacts = ArtifactRepository(db)
    arts = artifacts.list_for_run(run_id)
    match = next((a for a in arts if a.kind == kind), None)
    if not match or not match.path:
        return {"content": "", "found": False}
    try:
        content = Path(match.path).read_text(encoding="utf-8", errors="replace")
        return {"content": content, "found": True, "path": match.path}
    except Exception as e:
        return {"content": f"(read error: {e})", "found": True}


@router.get("/{run_id}/signals")
def get_signals(run_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Return parsed signals JSON for this run."""
    arts = ArtifactRepository(db).list_for_run(run_id)
    match = next((a for a in arts if a.kind == "signals_json"), None)
    if not match or not match.path:
        return {"signals": [], "found": False}
    try:
        import json
        data = json.loads(Path(match.path).read_text(encoding="utf-8"))
        return {**data, "found": True}
    except Exception as e:
        return {"signals": [], "found": False, "error": str(e)}
