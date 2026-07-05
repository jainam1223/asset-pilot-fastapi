import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ActorRole, DeviceLogEvent


class DeviceLogEntryResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    event_type: DeviceLogEvent
    actor_id: uuid.UUID | None
    actor_name: str | None
    actor_role: ActorRole
    request_id: uuid.UUID | None
    support_request_id: uuid.UUID | None
    extension_request_id: uuid.UUID | None
    handover_request_id: uuid.UUID | None
    from_value: str | None
    to_value: str | None
    note: str | None
    metadata: dict[str, Any]
    is_milestone: bool
    occurred_at: datetime
