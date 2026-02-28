from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.run import Run


class RunRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, title: str, ticket_text: str, workspace: str) -> Run:
        run = Run(title=title, ticket_text=ticket_text, workspace=workspace)
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        return run

    def get(self, run_id: UUID) -> Run | None:
        return self._db.get(Run, run_id)

    def list(self, limit: int = 50) -> list[Run]:
        stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def delete(self, run_id: UUID) -> None:
        from sqlalchemy import delete
        stmt = delete(Run).where(Run.id == run_id)
        self._db.execute(stmt)
        self._db.commit()

    def set_status(self, run_id: UUID, status: str) -> None:
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(status=status, updated_at=datetime.utcnow())
        )
        self._db.execute(stmt)
        self._db.commit()

    def set_patch_approved(self, run_id: UUID, approved: bool) -> None:
        self.set_patch_decision(run_id, "yes" if approved else "no")

    def set_patch_decision(self, run_id: UUID, decision: str) -> None:
        decision = (decision or "no").strip().lower()
        if decision not in {"no", "yes", "rejected"}:
            decision = "no"
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(patch_approved=decision, updated_at=datetime.utcnow())
        )
        self._db.execute(stmt)
        self._db.commit()
