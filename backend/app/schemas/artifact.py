from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    id: UUID
    run_id: UUID
    kind: str
    path: str
    created_at: datetime

    class Config:
        from_attributes = True
