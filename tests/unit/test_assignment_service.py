"""`AssignmentService` guard logic exercised against in-memory fake
repositories (no DB, no HTTP) — mirrors `tests/unit/test_inventory_service.py`'s
pattern. Suggested-devices sorting/filtering and the booking-calendar join
live in `ItemRepository`/`RequestRepository` and are covered by the
integration tests.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.device_log import DeviceLog
from app.models.enums import DeviceLogEvent, DeviceStatus, OwnerType, RequestStatus, UserRole
from app.models.item import Item
from app.models.request import Request
from app.models.user import User
from app.repositories.device_log_repository import DeviceLogRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.user_repository import UserRepository
from app.services.assignment_service import AssignmentService
from app.services.device_log_service import DeviceLogService

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


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
    def __init__(self, requests: Iterable[Request] = (), *, has_overlap: bool = False) -> None:
        self._requests: dict[uuid.UUID, Request] = {r.id: r for r in requests}
        self._has_overlap = has_overlap

    async def get_by_id(self, id_: uuid.UUID) -> Request | None:
        return self._requests.get(id_)

    async def update(self, entity: Request) -> Request:
        entity.updated_at = _next_ts()
        self._requests[entity.id] = entity
        return entity

    async def create(self, entity: Request) -> Request:
        if entity.id is None:
            entity.id = uuid.uuid4()
        entity.created_at = entity.created_at or _next_ts()
        entity.updated_at = entity.updated_at or _next_ts()
        self._requests[entity.id] = entity
        return entity

    async def has_overlapping_assigned_booking(
        self,
        item_id: uuid.UUID,
        assigned_from: datetime,
        assigned_to: datetime,
        *,
        exclude_request_id: uuid.UUID | None = None,
    ) -> bool:
        return self._has_overlap


class FakeUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users: dict[uuid.UUID, User] = {u.id: u for u in users}

    async def get_by_id(self, id_: uuid.UUID) -> User | None:
        return self._users.get(id_)


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
        status=DeviceStatus.AVAILABLE,
        current_owner_id=None,
        purchase_date=None,
        qr_code_token=uuid.uuid4(),
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Item(**defaults)


def _make_request(*, category_id: uuid.UUID, status: RequestStatus, **overrides: object) -> Request:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        requester_id=uuid.uuid4(),
        category_id=category_id,
        requested_from=_next_ts(),
        requested_to=_next_ts(),
        status=status,
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )
    defaults.update(overrides)
    return Request(**defaults)


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        name="Employee",
        email=f"{uuid.uuid4().hex}@techcorp.internal",
        password_hash="hash",
        role=UserRole.EMPLOYEE,
        is_active=True,
    )


def _build_service(
    *,
    items: Iterable[Item] = (),
    requests: Iterable[Request] = (),
    users: Iterable[User] = (),
    has_overlap: bool = False,
) -> tuple[AssignmentService, FakeDeviceLogRepository]:
    device_log_repository = FakeDeviceLogRepository()
    service = AssignmentService(
        FakeItemRepository(items),
        FakeRequestRepository(requests, has_overlap=has_overlap),
        FakeUserRepository(users),
        DeviceLogService(device_log_repository),
    )
    return service, device_log_repository


async def test_assign_wrong_request_status_raises_conflict() -> None:
    category_id = uuid.uuid4()
    request = _make_request(category_id=category_id, status=RequestStatus.REQUESTED)
    item = _make_item(category_id=category_id)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ConflictException):
        await service.assign(
            request.id,
            item_id=item.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_unavailable_item_raises_conflict() -> None:
    category_id = uuid.uuid4()
    request = _make_request(category_id=category_id, status=RequestStatus.PENDING_IT_APPROVAL)
    item = _make_item(category_id=category_id, status=DeviceStatus.ASSIGNED)
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ConflictException):
        await service.assign(
            request.id,
            item_id=item.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_category_mismatch_raises_validation_error() -> None:
    request = _make_request(category_id=uuid.uuid4(), status=RequestStatus.PENDING_IT_APPROVAL)
    item = _make_item(category_id=uuid.uuid4())
    service, _ = _build_service(items=[item], requests=[request])

    with pytest.raises(ValidationException):
        await service.assign(
            request.id,
            item_id=item.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_overlapping_range_raises_conflict() -> None:
    category_id = uuid.uuid4()
    request = _make_request(category_id=category_id, status=RequestStatus.PENDING_IT_APPROVAL)
    item = _make_item(category_id=category_id)
    service, _ = _build_service(items=[item], requests=[request], has_overlap=True)

    with pytest.raises(ConflictException):
        await service.assign(
            request.id,
            item_id=item.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_missing_request_raises_not_found() -> None:
    service, _ = _build_service()

    with pytest.raises(NotFoundException):
        await service.assign(
            uuid.uuid4(),
            item_id=uuid.uuid4(),
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_missing_item_raises_not_found() -> None:
    request = _make_request(category_id=uuid.uuid4(), status=RequestStatus.PENDING_IT_APPROVAL)
    service, _ = _build_service(requests=[request])

    with pytest.raises(NotFoundException):
        await service.assign(
            request.id,
            item_id=uuid.uuid4(),
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            is_wfh=False,
            actor_id=uuid.uuid4(),
        )


async def test_assign_success_updates_request_and_item_and_writes_milestone_log() -> None:
    category_id = uuid.uuid4()
    request = _make_request(category_id=category_id, status=RequestStatus.PENDING_IT_APPROVAL)
    item = _make_item(category_id=category_id)
    actor_id = uuid.uuid4()
    from_dt = _next_ts()
    to_dt = from_dt + timedelta(days=7)
    service, device_logs = _build_service(items=[item], requests=[request])

    result = await service.assign(
        request.id, item_id=item.id, assigned_from=from_dt, assigned_to=to_dt, is_wfh=True, actor_id=actor_id
    )

    assert result.status == RequestStatus.ASSIGNED
    assert result.assigned_item_id == item.id
    assert result.is_wfh is True
    assert result.it_decided_by == actor_id
    assert item.status == DeviceStatus.ASSIGNED
    assert item.current_owner_id == request.requester_id
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.ASSIGNED
    assert log.is_milestone is True
    assert log.request_id == request.id


async def test_update_booking_range_wrong_status_raises_conflict() -> None:
    request = _make_request(category_id=uuid.uuid4(), status=RequestStatus.PENDING_IT_APPROVAL)
    service, _ = _build_service(requests=[request])

    with pytest.raises(ConflictException):
        await service.update_booking_range(
            request.id, assigned_from=_next_ts(), assigned_to=_next_ts() + timedelta(days=1)
        )


async def test_update_booking_range_overlap_raises_conflict() -> None:
    request = _make_request(
        category_id=uuid.uuid4(),
        status=RequestStatus.ASSIGNED,
        assigned_item_id=uuid.uuid4(),
        assigned_from=_next_ts(),
        assigned_to=_next_ts() + timedelta(days=1),
    )
    service, _ = _build_service(requests=[request], has_overlap=True)

    with pytest.raises(ConflictException):
        await service.update_booking_range(
            request.id, assigned_from=_next_ts(), assigned_to=_next_ts() + timedelta(days=1)
        )


async def test_update_booking_range_success_updates_dates() -> None:
    request = _make_request(
        category_id=uuid.uuid4(),
        status=RequestStatus.ASSIGNED,
        assigned_item_id=uuid.uuid4(),
        assigned_from=_next_ts(),
        assigned_to=_next_ts() + timedelta(days=1),
    )
    service, _ = _build_service(requests=[request])
    new_from = _next_ts()
    new_to = new_from + timedelta(days=3)

    result = await service.update_booking_range(request.id, assigned_from=new_from, assigned_to=new_to)

    assert result.assigned_from == new_from
    assert result.assigned_to == new_to


async def test_direct_assign_non_client_item_raises_validation_error() -> None:
    item = _make_item(category_id=uuid.uuid4(), owner_type=OwnerType.COMPANY)
    employee = _make_user()
    service, _ = _build_service(items=[item], users=[employee])

    with pytest.raises(ValidationException):
        await service.direct_assign(
            item.id,
            employee_id=employee.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            actor_id=uuid.uuid4(),
        )


async def test_direct_assign_unavailable_item_raises_conflict() -> None:
    item = _make_item(
        category_id=uuid.uuid4(), owner_type=OwnerType.CLIENT, status=DeviceStatus.UNDER_REPAIR
    )
    employee = _make_user()
    service, _ = _build_service(items=[item], users=[employee])

    with pytest.raises(ConflictException):
        await service.direct_assign(
            item.id,
            employee_id=employee.id,
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            actor_id=uuid.uuid4(),
        )


async def test_direct_assign_missing_employee_raises_not_found() -> None:
    item = _make_item(category_id=uuid.uuid4(), owner_type=OwnerType.CLIENT)
    service, _ = _build_service(items=[item])

    with pytest.raises(NotFoundException):
        await service.direct_assign(
            item.id,
            employee_id=uuid.uuid4(),
            assigned_from=_next_ts(),
            assigned_to=_next_ts() + timedelta(days=1),
            actor_id=uuid.uuid4(),
        )


async def test_direct_assign_creates_client_direct_request_and_writes_client_assigned_log() -> None:
    item = _make_item(category_id=uuid.uuid4(), owner_type=OwnerType.CLIENT)
    employee = _make_user()
    actor_id = uuid.uuid4()
    from_dt = _next_ts()
    to_dt = from_dt + timedelta(days=5)
    service, device_logs = _build_service(items=[item], users=[employee])

    result = await service.direct_assign(
        item.id, employee_id=employee.id, assigned_from=from_dt, assigned_to=to_dt, actor_id=actor_id
    )

    assert result.is_client_direct is True
    assert result.status == RequestStatus.ASSIGNED
    assert result.assigned_item_id == item.id
    assert result.requester_id == employee.id
    assert item.status == DeviceStatus.ASSIGNED
    assert item.current_owner_id == employee.id
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.CLIENT_ASSIGNED
    assert log.is_milestone is True
    assert log.request_id == result.id


async def test_direct_assign_overlapping_dates_raises_conflict() -> None:
    category_id = uuid.uuid4()
    item = _make_item(category_id=category_id, owner_type=OwnerType.CLIENT)
    employee1 = _make_user()
    employee2 = _make_user()
    actor_id = uuid.uuid4()
    from_dt = _next_ts()
    to_dt = from_dt + timedelta(days=5)
    overlapping_from = from_dt + timedelta(days=2)
    overlapping_to = to_dt + timedelta(days=2)
    existing_request = _make_request(
        category_id=category_id,
        status=RequestStatus.ASSIGNED,
        requester_id=employee1.id,
        assigned_item_id=item.id,
        assigned_from=from_dt,
        assigned_to=to_dt,
    )
    service, _ = _build_service(
        items=[item],
        users=[employee1, employee2],
        requests=[existing_request],
        has_overlap=True,
    )

    with pytest.raises(ConflictException, match="overlap"):
        await service.direct_assign(
            item.id,
            employee_id=employee2.id,
            assigned_from=overlapping_from,
            assigned_to=overlapping_to,
            actor_id=actor_id,
        )


async def test_direct_assign_inactive_employee_raises_conflict() -> None:
    item = _make_item(category_id=uuid.uuid4(), owner_type=OwnerType.CLIENT)
    inactive_employee = User(
        id=uuid.uuid4(),
        name="Inactive Employee",
        email=f"{uuid.uuid4().hex}@techcorp.internal",
        password_hash="hash",
        is_active=False,
    )
    actor_id = uuid.uuid4()
    from_dt = _next_ts()
    to_dt = from_dt + timedelta(days=5)
    service, _ = _build_service(items=[item], users=[inactive_employee])

    with pytest.raises(ConflictException, match="Only active employees"):
        await service.direct_assign(
            item.id, employee_id=inactive_employee.id, assigned_from=from_dt, assigned_to=to_dt, actor_id=actor_id
        )


async def test_direct_assign_non_employee_role_raises_validation_error() -> None:
    item = _make_item(category_id=uuid.uuid4(), owner_type=OwnerType.CLIENT)
    manager = User(
        id=uuid.uuid4(),
        name="Manager",
        email=f"{uuid.uuid4().hex}@techcorp.internal",
        password_hash="hash",
        role=UserRole.MANAGER,
        is_active=True,
    )
    actor_id = uuid.uuid4()
    from_dt = _next_ts()
    to_dt = from_dt + timedelta(days=5)
    service, _ = _build_service(items=[item], users=[manager])

    with pytest.raises(ValidationException, match="Only employees"):
        await service.direct_assign(
            item.id, employee_id=manager.id, assigned_from=from_dt, assigned_to=to_dt, actor_id=actor_id
        )
