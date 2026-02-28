from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.step import Step


class StepRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def init_steps(self, run_id: UUID, step_names: list[str]) -> list[Step]:
        steps: list[Step] = []
        for i, name in enumerate(step_names, start=1):
            step = Step(run_id=run_id, order=i, name=name, status="pending")
            self._db.add(step)
            steps.append(step)
        self._db.commit()
        for s in steps:
            self._db.refresh(s)
        return steps

    def list_for_run(self, run_id: UUID) -> list[Step]:
        stmt = select(Step).where(Step.run_id == run_id).order_by(Step.order.asc())
        return list(self._db.execute(stmt).scalars().all())

    def reset_for_run(self, run_id: UUID) -> None:
        stmt = (
            update(Step)
            .where(Step.run_id == run_id)
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
        self._db.execute(stmt)
        self._db.commit()

    def delete_for_run(self, run_id: UUID) -> None:
        from sqlalchemy import delete
        stmt = delete(Step).where(Step.run_id == run_id)
        self._db.execute(stmt)
        self._db.commit()

    def set_running(self, step_id: UUID) -> None:
        stmt = (
            update(Step)
            .where(Step.id == step_id)
            .values(status="running", started_at=datetime.utcnow(), error="")
        )
        self._db.execute(stmt)
        self._db.commit()

    def set_waiting(self, step_id: UUID, summary: str = "") -> None:
        stmt = (
            update(Step)
            .where(Step.id == step_id)
            .values(status="waiting", summary=summary)
        )
        self._db.execute(stmt)
        self._db.commit()

    def set_success(self, step_id: UUID, summary: str = "", log_path: str = "", artifact_path: str = "") -> None:
        stmt = (
            update(Step)
            .where(Step.id == step_id)
            .values(status="success", summary=summary, finished_at=datetime.utcnow(), log_path=log_path, artifact_path=artifact_path)
        )
        self._db.execute(stmt)
        self._db.commit()

    def set_failed(self, step_id: UUID, error: str, log_path: str = "") -> None:
        stmt = (
            update(Step)
            .where(Step.id == step_id)
            .values(status="failed", error=error, finished_at=datetime.utcnow(), log_path=log_path)
        )
        self._db.execute(stmt)
        self._db.commit()


    def set_skipped(self, step_id: UUID, summary: str = "") -> None:
        stmt = (
            update(Step)
            .where(Step.id == step_id)
            .values(status="skipped", summary=summary, finished_at=datetime.utcnow(), error="")
        )
        self._db.execute(stmt)
        self._db.commit()
