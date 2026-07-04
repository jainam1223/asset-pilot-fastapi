"""`SupportService` guard logic exercised against in-memory fake
repositories (no DB, no HTTP) — mirrors `tests/unit/test_assignment_service.py`'s
pattern. Queue listing/detail joins live in `SupportRequestRepository` and
are covered by the integration tests.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.device_log import DeviceLog
from app.models.enums import (
    DeviceLogEvent,
    DeviceStatus,
    OwnerType,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
)
from app.models.item import Item
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.repositories.device_log_repository import DeviceLogRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import SupportRequestRepository
from app.services.device_log_service import DeviceLogService
from app.services.support_service import SupportService

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


class FakeSupportRequestRepository(SupportRequestRepository):
    def __init__(self, tickets: Iterable[SupportRequest] = ()) -> None:
        self._tickets: dict[uuid.UUID, SupportRequest] = {t.id: t for t in tickets}

    async def get_by_id(self, id_: uuid.UUID) -> SupportRequest | None:
        return self._tickets.get(id_)

    async def update(self, entity: SupportRequest) -> SupportRequest:
        entity.updated_at = _next_ts()
        self._tickets[entity.id] = entity
        return entity


class FakeItemRepository(ItemRepository):
    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._items: dict[uuid.UUID, Item] = {item.id: item for item in items}

    async def get_by_id(self, id_: uuid.UUID) -> Item | None:
        return self._items.get(id_)

    async def update(self, entity: Item) -> Item:
        entity.updated_at = _next_ts()
        self._items[entity.id] = entity
        return entity


class FakeRequestRepository(RequestRepository):
    def __init__(self, requests: Iterable[Request] = ()) -> None:
        self._requests: dict[uuid.UUID, Request] = {r.id: r for r in requests}

    async def get_by_id(self, id_: uuid.UUID) -> Request | None:
        return self._requests.get(id_)

    async def update(self, entity: Request) -> Request:
        entity.updated_at = _next_ts()
        self._requests[entity.id] = entity
        return entity


class FakeDeviceLogRepository(DeviceLogRepository):
    def __init__(self) -> None:
        self.created: list[DeviceLog] = []

    async def create(self, entity: DeviceLog) -> DeviceLog:
        self.created.append(entity)
        return entity


def _make_item(*, category_id: uuid.UUID, **overrides: object) -> Item:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        name="Laptop",
        serial_no=f"SN-{uuid.uuid4().hex[:8]}",
        category_id=category_id,
        owner_type=OwnerType.COMPANY,
        client_name=None,
        status=DeviceStatus.ASSIGNED,
        current_owner_id=None,
        purchase_date=None,
        qr_code_token=uuid.uuid4(),
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Item(**defaults)


def _make_request(*, category_id: uuid.UUID, **overrides: object) -> Request:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        requester_id=uuid.uuid4(),
        category_id=category_id,
        requested_from=_next_ts(),
        requested_to=_next_ts(),
        status=RequestStatus.ASSIGNED,
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Request(**defaults)


def _make_ticket(*, item_id: uuid.UUID, **overrides: object) -> SupportRequest:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        item_id=item_id,
        requester_id=uuid.uuid4(),
        type=SupportType.DAMAGE,
        description="Screen cracked",
        status=SupportStatus.OPEN,
        filed_at=_next_ts(),
        auto_closed=False,
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return SupportRequest(**defaults)


def _build_service(
    *,
    tickets: Iterable[SupportRequest] = (),
    items: Iterable[Item] = (),
    requests: Iterable[Request] = (),
) -> tuple[SupportService, FakeDeviceLogRepository]:
    device_log_repository = FakeDeviceLogRepository()
    service = SupportService(
        FakeSupportRequestRepository(tickets),
        FakeItemRepository(items),
        FakeRequestRepository(requests),
        DeviceLogService(device_log_repository),
    )
    return service, device_log_repository


async def test_start_missing_ticket_raises_not_found() -> None:
    service, _ = _build_service()

    with pytest.raises(NotFoundException):
        await service.start(uuid.uuid4(), actor_id=uuid.uuid4())


async def test_start_already_started_raises_conflict() -> None:
    item = _make_item(category_id=uuid.uuid4())
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS)
    service, _ = _build_service(tickets=[ticket], items=[item])

    with pytest.raises(ConflictException):
        await service.start(ticket.id, actor_id=uuid.uuid4())


async def test_start_damage_ticket_moves_item_under_repair_and_logs() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.ASSIGNED)
    ticket = _make_ticket(item_id=item.id, type=SupportType.DAMAGE)
    service, device_logs = _build_service(tickets=[ticket], items=[item])

    result = await service.start(ticket.id, actor_id=uuid.uuid4())

    assert result.status == SupportStatus.IN_PROGRESS
    assert item.status == DeviceStatus.UNDER_REPAIR
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.STATUS_CHANGED
    assert log.from_value == DeviceStatus.ASSIGNED.value
    assert log.to_value == DeviceStatus.UNDER_REPAIR.value
    assert log.support_request_id == ticket.id


async def test_start_non_damage_ticket_does_not_touch_item() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.ASSIGNED)
    ticket = _make_ticket(item_id=item.id, type=SupportType.UPDATE)
    service, device_logs = _build_service(tickets=[ticket], items=[item])

    result = await service.start(ticket.id, actor_id=uuid.uuid4())

    assert result.status == SupportStatus.IN_PROGRESS
    assert item.status == DeviceStatus.ASSIGNED
    assert device_logs.created == []


async def test_resolve_already_resolved_raises_conflict() -> None:
    item = _make_item(category_id=uuid.uuid4())
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.RESOLVED)
    service, _ = _build_service(tickets=[ticket], items=[item])

    with pytest.raises(ConflictException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.REMOTE_RESOLVED,
            it_note=None,
            swapped_to_item_id=None,
            old_item_next_status=None,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_remote_resolved_leaves_item_untouched() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.ASSIGNED)
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS, type=SupportType.UPDATE)
    service, device_logs = _build_service(tickets=[ticket], items=[item])

    result = await service.resolve(
        ticket.id,
        resolution=SupportResolution.REMOTE_RESOLVED,
        it_note="Resolved over a call",
        swapped_to_item_id=None,
        old_item_next_status=None,
        actor_id=uuid.uuid4(),
    )

    assert result.status == SupportStatus.RESOLVED
    assert result.resolution == SupportResolution.REMOTE_RESOLVED
    assert item.status == DeviceStatus.ASSIGNED
    assert [log.event_type for log in device_logs.created] == [DeviceLogEvent.SUPPORT_RESOLVED]


async def test_resolve_repaired_in_place_requires_under_repair() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.ASSIGNED)
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS)
    service, _ = _build_service(tickets=[ticket], items=[item])

    with pytest.raises(ConflictException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.REPAIRED_IN_PLACE,
            it_note=None,
            swapped_to_item_id=None,
            old_item_next_status=None,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_repaired_in_place_moves_item_back_to_assigned() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.UNDER_REPAIR)
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS)
    service, device_logs = _build_service(tickets=[ticket], items=[item])

    result = await service.resolve(
        ticket.id,
        resolution=SupportResolution.REPAIRED_IN_PLACE,
        it_note="Fixed on-site",
        swapped_to_item_id=None,
        old_item_next_status=None,
        actor_id=uuid.uuid4(),
    )

    assert result.status == SupportStatus.RESOLVED
    assert item.status == DeviceStatus.ASSIGNED
    assert [log.event_type for log in device_logs.created] == [
        DeviceLogEvent.STATUS_CHANGED,
        DeviceLogEvent.SUPPORT_RESOLVED,
    ]
    status_log = device_logs.created[0]
    assert status_log.from_value == DeviceStatus.UNDER_REPAIR.value
    assert status_log.to_value == DeviceStatus.ASSIGNED.value


async def test_resolve_swap_no_tied_request_raises_conflict() -> None:
    category_id = uuid.uuid4()
    old_item = _make_item(category_id=category_id, status=DeviceStatus.UNDER_REPAIR)
    new_item = _make_item(category_id=category_id, status=DeviceStatus.AVAILABLE)
    ticket = _make_ticket(item_id=old_item.id, status=SupportStatus.IN_PROGRESS, request_id=None)
    service, _ = _build_service(tickets=[ticket], items=[old_item, new_item])

    with pytest.raises(ConflictException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.SWAPPED,
            it_note=None,
            swapped_to_item_id=new_item.id,
            old_item_next_status=DeviceStatus.UNDER_REPAIR,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_swap_wrong_category_raises_validation_error() -> None:
    old_item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.UNDER_REPAIR)
    new_item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.AVAILABLE)
    request = _make_request(category_id=old_item.category_id)
    ticket = _make_ticket(item_id=old_item.id, status=SupportStatus.IN_PROGRESS, request_id=request.id)
    service, _ = _build_service(tickets=[ticket], items=[old_item, new_item], requests=[request])

    with pytest.raises(ValidationException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.SWAPPED,
            it_note=None,
            swapped_to_item_id=new_item.id,
            old_item_next_status=DeviceStatus.UNDER_REPAIR,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_swap_target_not_available_raises_conflict() -> None:
    category_id = uuid.uuid4()
    old_item = _make_item(category_id=category_id, status=DeviceStatus.UNDER_REPAIR)
    new_item = _make_item(category_id=category_id, status=DeviceStatus.ASSIGNED)
    request = _make_request(category_id=category_id)
    ticket = _make_ticket(item_id=old_item.id, status=SupportStatus.IN_PROGRESS, request_id=request.id)
    service, _ = _build_service(tickets=[ticket], items=[old_item, new_item], requests=[request])

    with pytest.raises(ConflictException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.SWAPPED,
            it_note=None,
            swapped_to_item_id=new_item.id,
            old_item_next_status=DeviceStatus.UNDER_REPAIR,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_swap_success_repoints_request_and_transitions_both_items() -> None:
    category_id = uuid.uuid4()
    requester_id = uuid.uuid4()
    old_item = _make_item(
        category_id=category_id, status=DeviceStatus.UNDER_REPAIR, current_owner_id=requester_id
    )
    new_item = _make_item(category_id=category_id, status=DeviceStatus.AVAILABLE)
    request = _make_request(
        category_id=category_id, requester_id=requester_id, assigned_item_id=old_item.id
    )
    ticket = _make_ticket(item_id=old_item.id, status=SupportStatus.IN_PROGRESS, request_id=request.id)
    service, device_logs = _build_service(
        tickets=[ticket], items=[old_item, new_item], requests=[request]
    )
    actor_id = uuid.uuid4()

    result = await service.resolve(
        ticket.id,
        resolution=SupportResolution.SWAPPED,
        it_note="Faulty unit swapped",
        swapped_to_item_id=new_item.id,
        old_item_next_status=DeviceStatus.RETIRED,
        actor_id=actor_id,
    )

    assert result.status == SupportStatus.RESOLVED
    assert result.swapped_to_item_id == new_item.id
    assert request.assigned_item_id == new_item.id
    assert old_item.status == DeviceStatus.RETIRED
    assert old_item.current_owner_id is None
    assert new_item.status == DeviceStatus.ASSIGNED
    assert new_item.current_owner_id == requester_id

    events = [log.event_type for log in device_logs.created]
    assert events == [DeviceLogEvent.SWAPPED_OUT, DeviceLogEvent.SWAPPED_IN, DeviceLogEvent.SUPPORT_RESOLVED]

    swapped_out_log, swapped_in_log, _ = device_logs.created
    assert swapped_out_log.item_id == old_item.id
    assert swapped_out_log.is_milestone is True
    assert swapped_out_log.log_metadata == {"swapped_to_item_id": str(new_item.id)}
    assert swapped_in_log.item_id == new_item.id
    assert swapped_in_log.is_milestone is True
    assert swapped_in_log.log_metadata == {"swapped_from_item_id": str(old_item.id)}


async def test_resolve_marked_lost_no_tied_request_raises_conflict() -> None:
    item = _make_item(category_id=uuid.uuid4(), status=DeviceStatus.ASSIGNED)
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS, request_id=None)
    service, _ = _build_service(tickets=[ticket], items=[item])

    with pytest.raises(ConflictException):
        await service.resolve(
            ticket.id,
            resolution=SupportResolution.MARKED_LOST,
            it_note=None,
            swapped_to_item_id=None,
            old_item_next_status=None,
            actor_id=uuid.uuid4(),
        )


async def test_resolve_marked_lost_sets_item_lost_and_completes_request_with_null_next_status() -> None:
    category_id = uuid.uuid4()
    item = _make_item(category_id=category_id, status=DeviceStatus.ASSIGNED)
    request = _make_request(category_id=category_id, assigned_item_id=item.id)
    ticket = _make_ticket(item_id=item.id, status=SupportStatus.IN_PROGRESS, request_id=request.id)
    service, device_logs = _build_service(tickets=[ticket], items=[item], requests=[request])
    actor_id = uuid.uuid4()

    result = await service.resolve(
        ticket.id,
        resolution=SupportResolution.MARKED_LOST,
        it_note="Device never returned",
        swapped_to_item_id=None,
        old_item_next_status=None,
        actor_id=actor_id,
    )

    assert result.status == SupportStatus.RESOLVED
    assert result.resolution == SupportResolution.MARKED_LOST
    assert item.status == DeviceStatus.LOST
    assert request.status == RequestStatus.COMPLETED
    assert request.completed_next_status is None
    assert request.completed_by == actor_id

    events = [log.event_type for log in device_logs.created]
    assert events == [DeviceLogEvent.MARKED_LOST, DeviceLogEvent.SUPPORT_RESOLVED]
