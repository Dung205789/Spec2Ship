from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact


class ArtifactRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, run_id: UUID, kind: str, path: str) -> Artifact:
        artifact = Artifact(run_id=run_id, kind=kind, path=path)
        self._db.add(artifact)
        self._db.commit()
        self._db.refresh(artifact)
        return artifact

    def list_for_run(self, run_id: UUID) -> list[Artifact]:
        stmt = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
        return list(self._db.execute(stmt).scalars().all())

    def delete_for_run(self, run_id: UUID) -> int:
        stmt = delete(Artifact).where(Artifact.run_id == run_id)
        res = self._db.execute(stmt)
        self._db.commit()
        return int(res.rowcount or 0)
