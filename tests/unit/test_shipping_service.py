"""`ShippingService` guard logic + support auto-close cascade exercised
against in-memory fake repositories (no DB, no HTTP) — mirrors
`tests/unit/test_assignment_service.py`'s pattern. Queue listing lives in
`RequestRepository` and is covered by the integration tests.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.device_log import DeviceLog
from app.models.enums import DeviceLogEvent, DeviceStatus, RequestStatus, SupportStatus, SupportType
from app.models.item import Item
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.repositories.device_log_repository import DeviceLogRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import SupportRequestRepository
from app.services.device_log_service import DeviceLogService
from app.services.shipping_service import ShippingService

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


class FakeRequestRepository(RequestRepository):
    def __init__(self, requests: Iterable[Request] = ()) -> None:
        self._requests: dict[uuid.UUID, Request] = {r.id: r for r in requests}

    async def get_by_id(self, id_: uuid.UUID) -> Request | None:
        return self._requests.get(id_)

    async def update(self, entity: Request) -> Request:
        entity.updated_at = _next_ts()
        self._requests[entity.id] = entity
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


class FakeSupportRequestRepository(SupportRequestRepository):
    def __init__(self, tickets: Iterable[SupportRequest] = ()) -> None:
        self._tickets: dict[uuid.UUID, SupportRequest] = {t.id: t for t in tickets}

    async def list_open_for_item(self, item_id: uuid.UUID) -> list[SupportRequest]:
        return [
            t
            for t in self._tickets.values()
            if t.item_id == item_id and t.status in (SupportStatus.OPEN, SupportStatus.IN_PROGRESS)
        ]

    async def update(self, entity: SupportRequest) -> SupportRequest:
        self._tickets[entity.id] = entity
        return entity


class FakeDeviceLogRepository(DeviceLogRepository):
    def __init__(self) -> None:
        self.created: list[DeviceLog] = []

    async def create(self, entity: DeviceLog) -> DeviceLog:
        self.created.append(entity)
        return entity


def _make_item(**overrides: object) -> Item:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        name="Laptop",
        serial_no=f"SN-{uuid.uuid4().hex[:8]}",
        category_id=uuid.uuid4(),
        status=DeviceStatus.ASSIGNED,
        current_owner_id=uuid.uuid4(),
        qr_code_token=uuid.uuid4(),
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Item(**defaults)


def _make_request(*, assigned_item_id: uuid.UUID | None, **overrides: object) -> Request:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        requester_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        assigned_item_id=assigned_item_id,
        requested_from=_next_ts(),
        requested_to=_next_ts(),
        status=RequestStatus.ASSIGNED,
        is_wfh=False,
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Request(**defaults)


def _make_support_request(*, item_id: uuid.UUID, status: SupportStatus) -> SupportRequest:
    return SupportRequest(
        id=uuid.uuid4(),
        item_id=item_id,
        requester_id=uuid.uuid4(),
        type=SupportType.DAMAGE,
        description="Broken",
        status=status,
        filed_at=_next_ts(),
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )


def _build_service(
    *,
    items: Iterable[Item] = (),
    requests: Iterable[Request] = (),
    tickets: Iterable[SupportRequest] = (),
) -> tuple[ShippingService, FakeDeviceLogRepository]:
    device_log_repository = FakeDeviceLogRepository()
    service = ShippingService(
        FakeRequestRepository(requests),
        FakeItemRepository(items),
        FakeSupportRequestRepository(tickets),
        DeviceLogService(device_log_repository),
    )
    return service, device_log_repository


async def test_ship_non_wfh_request_raises_validation_error() -> None:
    item = _make_item()
    request = _make_request(assigned_item_id=item.id, is_wfh=False)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ValidationException):
        await service.ship(request.id, ship_tracking_url="https://track.example/1", actor_id=uuid.uuid4())


async def test_ship_item_not_assigned_raises_conflict() -> None:
    item = _make_item(status=DeviceStatus.UNDER_REPAIR)
    request = _make_request(assigned_item_id=item.id, is_wfh=True)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ConflictException):
        await service.ship(request.id, ship_tracking_url="https://track.example/1", actor_id=uuid.uuid4())


async def test_ship_missing_request_raises_not_found() -> None:
    service, _ = _build_service()

    with pytest.raises(NotFoundException):
        await service.ship(uuid.uuid4(), ship_tracking_url="https://track.example/1", actor_id=uuid.uuid4())


async def test_ship_success_moves_item_to_shipping_pending_and_writes_log() -> None:
    item = _make_item(status=DeviceStatus.ASSIGNED)
    request = _make_request(assigned_item_id=item.id, is_wfh=True)
    service, device_logs = _build_service(items=[item], requests=[request])

    result = await service.ship(
        request.id, ship_tracking_url="https://track.example/1", actor_id=uuid.uuid4()
    )

    assert result.ship_tracking_url == "https://track.example/1"
    assert result.ship_initiated_at is not None
    assert item.status == DeviceStatus.SHIPPING_PENDING
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.SHIP_OUTBOUND_INITIATED
    assert log.is_milestone is False
    assert log.log_metadata == {"ship_tracking_url": "https://track.example/1"}


async def test_confirm_delivery_wrong_item_status_raises_conflict() -> None:
    item = _make_item(status=DeviceStatus.ASSIGNED)
    request = _make_request(assigned_item_id=item.id, is_wfh=True)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ConflictException):
        await service.confirm_delivery(request.id, actor_id=uuid.uuid4())


async def test_confirm_delivery_success_returns_item_to_assigned() -> None:
    item = _make_item(status=DeviceStatus.SHIPPING_PENDING)
    request = _make_request(assigned_item_id=item.id, is_wfh=True)
    service, device_logs = _build_service(items=[item], requests=[request])

    result = await service.confirm_delivery(request.id, actor_id=uuid.uuid4())

    assert result.ship_completed_at is not None
    assert item.status == DeviceStatus.ASSIGNED
    assert len(device_logs.created) == 1
    assert device_logs.created[0].event_type == DeviceLogEvent.SHIP_OUTBOUND_COMPLETED


async def test_complete_return_wrong_item_status_raises_conflict() -> None:
    item = _make_item(status=DeviceStatus.SHIPPING_PENDING)
    request = _make_request(assigned_item_id=item.id)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ConflictException):
        await service.complete_return(
            request.id, next_status=DeviceStatus.AVAILABLE, actor_id=uuid.uuid4()
        )


async def test_complete_return_no_assigned_item_raises_conflict() -> None:
    request = _make_request(assigned_item_id=None)
    service, _ = _build_service(requests=[request])

    with pytest.raises(ConflictException):
        await service.complete_return(
            request.id, next_status=DeviceStatus.AVAILABLE, actor_id=uuid.uuid4()
        )


async def test_complete_return_success_completes_request_and_clears_owner() -> None:
    item = _make_item(status=DeviceStatus.RETURN_SHIPPING_PENDING)
    request = _make_request(assigned_item_id=item.id, is_wfh=True)
    actor_id = uuid.uuid4()
    service, device_logs = _build_service(items=[item], requests=[request])

    result = await service.complete_return(
        request.id, next_status=DeviceStatus.AVAILABLE, actor_id=actor_id
    )

    assert result.status == RequestStatus.COMPLETED
    assert result.completed_by == actor_id
    assert result.completed_next_status == DeviceStatus.AVAILABLE
    assert item.status == DeviceStatus.AVAILABLE
    assert item.current_owner_id is None
    events = [log.event_type for log in device_logs.created]
    assert events == [DeviceLogEvent.RETURN_RECEIVED, DeviceLogEvent.ASSIGNMENT_COMPLETED]
    assert device_logs.created[0].is_milestone is True
    assert device_logs.created[0].to_value == DeviceStatus.AVAILABLE.value


async def test_complete_return_auto_closes_open_support_tickets_with_system_actor() -> None:
    item = _make_item(status=DeviceStatus.ASSIGNED)
    request = _make_request(assigned_item_id=item.id)
    open_ticket = _make_support_request(item_id=item.id, status=SupportStatus.OPEN)
    in_progress_ticket = _make_support_request(item_id=item.id, status=SupportStatus.IN_PROGRESS)
    already_resolved = _make_support_request(item_id=item.id, status=SupportStatus.RESOLVED)
    service, device_logs = _build_service(
        items=[item], requests=[request], tickets=[open_ticket, in_progress_ticket, already_resolved]
    )

    await service.complete_return(request.id, next_status=DeviceStatus.AVAILABLE, actor_id=uuid.uuid4())

    assert open_ticket.status == SupportStatus.RESOLVED
    assert open_ticket.auto_closed is True
    assert open_ticket.resolved_at is not None
    assert in_progress_ticket.status == SupportStatus.RESOLVED
    assert in_progress_ticket.auto_closed is True

    auto_close_logs = [
        log for log in device_logs.created if log.event_type == DeviceLogEvent.SUPPORT_AUTO_CLOSED
    ]
    assert len(auto_close_logs) == 2
    for log in auto_close_logs:
        assert log.actor_id is None
        assert log.actor_role.value == "system"
        assert log.is_milestone is False
