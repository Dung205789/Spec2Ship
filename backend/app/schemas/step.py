from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StepOut(BaseModel):
    id: UUID
    run_id: UUID
    order: int
    name: str
    status: str
    summary: str
    log_path: str
    artifact_path: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str

    class Config:
        from_attributes = True
