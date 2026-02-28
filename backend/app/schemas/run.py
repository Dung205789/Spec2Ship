from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    title: str = Field(..., max_length=200)
    ticket_text: str
    workspace: str = "sample_workspace"


class RunOut(BaseModel):
    id: UUID
    title: str
    ticket_text: str
    workspace: str
    status: str
    patch_approved: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
