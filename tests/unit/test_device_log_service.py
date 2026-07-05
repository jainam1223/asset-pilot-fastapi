"""`DeviceLogService` logic exercised against an in-memory fake repository
(no DB, no HTTP) — mirrors `tests/unit/test_auth_service.py`'s pattern.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.models.device_log import DeviceLog
from app.models.enums import ActorRole, DeviceLogEvent
from app.repositories.device_log_repository import DeviceLogRepository, DeviceLogRow
from app.services.device_log_service import EVENT_MILESTONE_MAP, DeviceLogService
from app.utils.pagination import PaginationParams

pytestmark = pytest.mark.unit


class FakeDeviceLogRepository(DeviceLogRepository):
    """In-memory stand-in proving `DeviceLogService` only depends on
    `create`/`list_for_item` — no real session is ever touched.
    """

    def __init__(
        self, logs: Iterable[DeviceLog] = (), actor_names: dict[uuid.UUID | None, str] | None = None
    ) -> None:
        self._logs: list[DeviceLog] = list(logs)
        self._actor_names = actor_names or {}

    async def create(self, entity: DeviceLog) -> DeviceLog:
        if entity.id is None:
            entity.id = uuid.uuid4()
        if entity.occurred_at is None:
            entity.occurred_at = _next_timestamp()
        self._logs.append(entity)
        return entity

    async def list_for_item(
        self, item_id: uuid.UUID, *, milestones_only: bool, pagination: PaginationParams | None = None
    ) -> list[DeviceLogRow]:
        logs = [log for log in self._logs if log.item_id == item_id]
        if milestones_only:
            logs = [log for log in logs if log.is_milestone]
        logs = sorted(logs, key=lambda log: log.occurred_at)
        return [DeviceLogRow(device_log=log, actor_name=self._actor_names.get(log.actor_id)) for log in logs]


_timestamp_seconds = itertools.count(1)


def _next_timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_timestamp_seconds))


def test_event_milestone_map_covers_every_event() -> None:
    assert set(EVENT_MILESTONE_MAP) == set(DeviceLogEvent)


async def test_append_derives_milestone_flag_from_map() -> None:
    service = DeviceLogService(FakeDeviceLogRepository())
    item_id = uuid.uuid4()

    milestone_entry = await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.ASSIGNED,
        actor_id=uuid.uuid4(),
        actor_role=ActorRole.IT_ADMIN,
    )
    non_milestone_entry = await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.DEVICE_EDITED,
        actor_id=uuid.uuid4(),
        actor_role=ActorRole.IT_ADMIN,
    )

    assert milestone_entry.is_milestone is True
    assert non_milestone_entry.is_milestone is False


async def test_append_respects_explicit_is_milestone_override() -> None:
    service = DeviceLogService(FakeDeviceLogRepository())

    entry = await service.append(
        item_id=uuid.uuid4(),
        event_type=DeviceLogEvent.DEVICE_EDITED,
        actor_id=None,
        actor_role=ActorRole.SYSTEM,
        is_milestone=True,
    )

    assert entry.is_milestone is True


async def test_get_timeline_milestones_only_filters_and_orders() -> None:
    repository = FakeDeviceLogRepository()
    service = DeviceLogService(repository)
    item_id = uuid.uuid4()

    await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.DEVICE_CREATED,
        actor_id=uuid.uuid4(),
        actor_role=ActorRole.IT_ADMIN,
    )
    await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.ASSIGNED,
        actor_id=uuid.uuid4(),
        actor_role=ActorRole.IT_ADMIN,
    )
    await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.RETIRED,
        actor_id=uuid.uuid4(),
        actor_role=ActorRole.IT_ADMIN,
    )

    milestones = await service.get_timeline(item_id, milestones_only=True)
    full = await service.get_timeline(item_id, milestones_only=False)

    assert [entry.event_type for entry in milestones] == [DeviceLogEvent.ASSIGNED, DeviceLogEvent.RETIRED]
    assert [entry.event_type for entry in full] == [
        DeviceLogEvent.DEVICE_CREATED,
        DeviceLogEvent.ASSIGNED,
        DeviceLogEvent.RETIRED,
    ]
    assert all(entry.occurred_at <= full[i + 1].occurred_at for i, entry in enumerate(full[:-1]))


async def test_get_timeline_resolves_actor_name() -> None:
    item_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    repository = FakeDeviceLogRepository(actor_names={actor_id: "Arjun Mehta"})
    service = DeviceLogService(repository)

    await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.ASSIGNED,
        actor_id=actor_id,
        actor_role=ActorRole.IT_ADMIN,
    )
    await service.append(
        item_id=item_id,
        event_type=DeviceLogEvent.RETIRED,
        actor_id=None,
        actor_role=ActorRole.SYSTEM,
    )

    timeline = await service.get_timeline(item_id, milestones_only=False)

    assert timeline[0].actor_name == "Arjun Mehta"
    assert timeline[1].actor_name is None
