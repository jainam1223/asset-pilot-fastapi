"""Pydantic DTOs for the read-only IT handover audit view (API §12)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import HandoverStatus


class HandoverListItem(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    owner_id: uuid.UUID
    borrower_id: uuid.UUID
    requested_duration_hours: int | None
    status: HandoverStatus
    requested_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    item_name: str
    owner_name: str
    borrower_name: str
