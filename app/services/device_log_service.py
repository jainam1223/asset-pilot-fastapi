"""Shared device audit-log writer + timeline reader.

Every device-touching write across modules (M5, M7-M11) calls
`DeviceLogService.append(...)` within its own request/session so the
`device_log` insert lands in the same transaction as the write it's
recording. `EVENT_MILESTONE_MAP` is the single source of truth for which
event types surface in the milestone-only timeline view.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.device_log import DeviceLog
from app.models.enums import ActorRole, DeviceLogEvent
from app.repositories.device_log_repository import DeviceLogRepository

EVENT_MILESTONE_MAP: dict[DeviceLogEvent, bool] = {
    DeviceLogEvent.DEVICE_CREATED: False,
    DeviceLogEvent.DEVICE_EDITED: False,
    DeviceLogEvent.ASSIGNED: True,
    DeviceLogEvent.CLIENT_ASSIGNED: True,
    DeviceLogEvent.SHIP_OUTBOUND_INITIATED: False,
    DeviceLogEvent.SHIP_OUTBOUND_COMPLETED: False,
    DeviceLogEvent.RETURN_SHIP_INITIATED: False,
    DeviceLogEvent.RETURN_RECEIVED: True,
    DeviceLogEvent.ASSIGNMENT_COMPLETED: True,
    DeviceLogEvent.STATUS_CHANGED: True,
    DeviceLogEvent.SUPPORT_OPENED: True,
    DeviceLogEvent.SUPPORT_RESOLVED: True,
    DeviceLogEvent.SUPPORT_AUTO_CLOSED: False,
    DeviceLogEvent.EXTENSION_REQUESTED: False,
    DeviceLogEvent.EXTENSION_APPROVED: False,
    DeviceLogEvent.EXTENSION_REJECTED: False,
    DeviceLogEvent.HANDOVER_REQUESTED: False,
    DeviceLogEvent.HANDOVER_ACCEPTED: True,
    DeviceLogEvent.HANDOVER_REJECTED: False,
    DeviceLogEvent.HANDOVER_CANCELLED: False,
    DeviceLogEvent.HANDOVER_COMPLETED: True,
    DeviceLogEvent.MARKED_LOST: True,
    DeviceLogEvent.RETIRED: True,
    DeviceLogEvent.RETURNED_TO_CLIENT: True,
    DeviceLogEvent.SWAPPED_OUT: False,
    DeviceLogEvent.SWAPPED_IN: False,
}


@dataclass
class DeviceLogEntry:
    id: uuid.UUID
    item_id: uuid.UUID
    event_type: DeviceLogEvent
    actor_id: uuid.UUID | None
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


def _entry_from(log: DeviceLog) -> DeviceLogEntry:
    return DeviceLogEntry(
        id=log.id,
        item_id=log.item_id,
        event_type=log.event_type,
        actor_id=log.actor_id,
        actor_role=log.actor_role,
        request_id=log.request_id,
        support_request_id=log.support_request_id,
        extension_request_id=log.extension_request_id,
        handover_request_id=log.handover_request_id,
        from_value=log.from_value,
        to_value=log.to_value,
        note=log.note,
        metadata=log.log_metadata,
        is_milestone=log.is_milestone,
        occurred_at=log.occurred_at,
    )


class DeviceLogService:
    def __init__(self, device_log_repository: DeviceLogRepository) -> None:
        self.device_log_repository = device_log_repository

    async def append(
        self,
        *,
        item_id: uuid.UUID,
        event_type: DeviceLogEvent,
        actor_id: uuid.UUID | None,
        actor_role: ActorRole,
        request_id: uuid.UUID | None = None,
        support_request_id: uuid.UUID | None = None,
        extension_request_id: uuid.UUID | None = None,
        handover_request_id: uuid.UUID | None = None,
        from_value: str | None = None,
        to_value: str | None = None,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_milestone: bool | None = None,
    ) -> DeviceLogEntry:
        log = DeviceLog(
            item_id=item_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            request_id=request_id,
            support_request_id=support_request_id,
            extension_request_id=extension_request_id,
            handover_request_id=handover_request_id,
            from_value=from_value,
            to_value=to_value,
            note=note,
            log_metadata=metadata or {},
            is_milestone=is_milestone if is_milestone is not None else EVENT_MILESTONE_MAP[event_type],
        )
        created = await self.device_log_repository.create(log)
        return _entry_from(created)

    async def get_timeline(self, item_id: uuid.UUID, *, milestones_only: bool) -> list[DeviceLogEntry]:
        logs = await self.device_log_repository.list_for_item(item_id, milestones_only=milestones_only)
        return [_entry_from(log) for log in logs]
