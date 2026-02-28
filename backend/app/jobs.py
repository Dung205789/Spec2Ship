from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.use_cases.run_pipeline import RunPipeline
from app.use_cases.swebench_eval import RunSWEbenchEval
from app.use_cases.swebench_train_lora import RunSWEbenchTrainLoRA
from app.repositories.runs import RunRepository
from app.services.directives import parse_spec2ship_directives

log = logging.getLogger(__name__)


def run_pipeline_job(run_id: str) -> None:
    """RQ job entry point."""
    run_uuid = UUID(run_id)
    db: Session = SessionLocal()
    try:
        runs = RunRepository(db)
        run = runs.get(run_uuid)
        mode, cfg = parse_spec2ship_directives(run.ticket_text if run else "")

        try:
            # Default: normal Spec2Ship patch workflow.
            if mode == "swebench_eval":
                result = RunSWEbenchEval(db, cfg).start(run_uuid)
            elif mode in {"swebench_train_lora", "swebench_train", "train_lora"}:
                result = RunSWEbenchTrainLoRA(db, cfg).start(run_uuid)
            else:
                result = RunPipeline(db).start(run_uuid)
            log.info("Job finished: ok=%s message=%s", result.ok, result.message)
        except Exception as e:
            # Ensure the UI doesn't get stuck in "running" if the worker crashes mid-step.
            err = f"Worker job crashed: {type(e).__name__}: {e}"
            log.exception(err)
            runs.set_status(run_uuid, "failed")
            raise
    finally:
        db.close()
