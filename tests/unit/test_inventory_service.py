"""`InventoryService` logic exercised against in-memory fake repositories
(no DB, no HTTP) — mirrors `tests/unit/test_auth_service.py`'s pattern.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.models.device_log import DeviceLog
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    HandoverStatus,
    OwnerType,
    RequestStatus,
    SupportStatus,
    SupportType,
)
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User
from app.repositories.device_log_repository import DeviceLogRepository
from app.repositories.handover_request_repository import HandoverRequestRepository
from app.repositories.item_category_repository import ItemCategoryRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import SupportRequestRepository
from app.repositories.user_repository import UserRepository
from app.services.device_log_service import DeviceLogService
from app.services.inventory_service import InventoryService

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


class FakeItemRepository(ItemRepository):
    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._items: dict[uuid.UUID, Item] = {item.id: item for item in items}

    async def get_by_id(self, id_: uuid.UUID) -> Item | None:
        return self._items.get(id_)

    async def get_by_serial_no(self, serial_no: str) -> Item | None:
        return next((item for item in self._items.values() if item.serial_no == serial_no), None)

    async def create(self, entity: Item) -> Item:
        if entity.id is None:
            entity.id = uuid.uuid4()
        if entity.qr_code_token is None:
            entity.qr_code_token = uuid.uuid4()
        entity.created_at = entity.created_at or _next_ts()
        entity.updated_at = entity.updated_at or _next_ts()
        self._items[entity.id] = entity
        return entity

    async def update(self, entity: Item) -> Item:
        entity.updated_at = _next_ts()
        self._items[entity.id] = entity
        return entity


class FakeItemCategoryRepository(ItemCategoryRepository):
    def __init__(self, categories: Iterable[ItemCategory] = ()) -> None:
        self._categories: dict[uuid.UUID, ItemCategory] = {c.id: c for c in categories}

    async def get_by_id(self, id_: uuid.UUID) -> ItemCategory | None:
        return self._categories.get(id_)

    async def list_active(self) -> list[ItemCategory]:
        return [c for c in self._categories.values() if c.is_active]


class FakeUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users: dict[uuid.UUID, User] = {user.id: user for user in users}

    async def get_by_id(self, id_: uuid.UUID) -> User | None:
        return self._users.get(id_)


class FakeRequestRepository(RequestRepository):
    def __init__(self, requests: Iterable[Request] = ()) -> None:
        self._requests: list[Request] = list(requests)

    async def get_active_for_item(self, item_id: uuid.UUID) -> Request | None:
        return next(
            (
                r
                for r in self._requests
                if r.assigned_item_id == item_id and r.status == RequestStatus.ASSIGNED
            ),
            None,
        )


class FakeSupportRequestRepository(SupportRequestRepository):
    def __init__(self, support_requests: Iterable[SupportRequest] = ()) -> None:
        self._support_requests: list[SupportRequest] = list(support_requests)

    async def list_open_for_item(self, item_id: uuid.UUID) -> list[SupportRequest]:
        return [
            s
            for s in self._support_requests
            if s.item_id == item_id and s.status in (SupportStatus.OPEN, SupportStatus.IN_PROGRESS)
        ]


class FakeHandoverRequestRepository(HandoverRequestRepository):
    def __init__(self, handovers: Iterable[HandoverRequest] = ()) -> None:
        self._handovers: list[HandoverRequest] = list(handovers)

    async def get_accepted_for_item(self, item_id: uuid.UUID) -> HandoverRequest | None:
        return next(
            (h for h in self._handovers if h.item_id == item_id and h.status == HandoverStatus.ACCEPTED),
            None,
        )


class FakeDeviceLogRepository(DeviceLogRepository):
    def __init__(self) -> None:
        self.created: list[DeviceLog] = []

    async def create(self, entity: DeviceLog) -> DeviceLog:
        self.created.append(entity)
        return entity


def _make_category(*, is_active: bool = True) -> ItemCategory:
    return ItemCategory(id=uuid.uuid4(), name=f"Category-{uuid.uuid4().hex[:6]}", is_active=is_active)


def _make_item(*, category_id: uuid.UUID, serial_no: str = "SN-1", **overrides: object) -> Item:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        name="Laptop",
        serial_no=serial_no,
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


def _build_service(
    *,
    items: Iterable[Item] = (),
    categories: Iterable[ItemCategory] = (),
    users: Iterable[User] = (),
    requests: Iterable[Request] = (),
    support_requests: Iterable[SupportRequest] = (),
    handovers: Iterable[HandoverRequest] = (),
) -> tuple[InventoryService, FakeDeviceLogRepository]:
    device_log_repository = FakeDeviceLogRepository()
    service = InventoryService(
        FakeItemRepository(items),
        FakeItemCategoryRepository(categories),
        FakeUserRepository(users),
        FakeRequestRepository(requests),
        FakeSupportRequestRepository(support_requests),
        FakeHandoverRequestRepository(handovers),
        DeviceLogService(device_log_repository),
    )
    return service, device_log_repository


async def test_create_item_writes_device_created_log() -> None:
    category = _make_category()
    service, device_logs = _build_service(categories=[category])

    result = await service.create_item(
        name="Laptop",
        serial_no="SN-1",
        category_id=category.id,
        owner_type=OwnerType.COMPANY,
        client_name=None,
        purchase_date=None,
        actor_id=uuid.uuid4(),
    )

    assert result.status == DeviceStatus.AVAILABLE
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.DEVICE_CREATED
    assert log.is_milestone is False
    assert log.to_value == DeviceStatus.AVAILABLE.value
    assert log.actor_role == ActorRole.IT_ADMIN


async def test_create_item_clears_client_name_for_non_client_owner() -> None:
    category = _make_category()
    service, _ = _build_service(categories=[category])

    result = await service.create_item(
        name="Laptop",
        serial_no="SN-1",
        category_id=category.id,
        owner_type=OwnerType.COMPANY,
        client_name="Should be dropped",
        purchase_date=None,
        actor_id=uuid.uuid4(),
    )

    assert result.client_name is None


async def test_create_item_raises_conflict_on_duplicate_serial_no() -> None:
    category = _make_category()
    existing = _make_item(category_id=category.id, serial_no="SN-DUP")
    service, _ = _build_service(items=[existing], categories=[category])

    with pytest.raises(ConflictException):
        await service.create_item(
            name="Laptop",
            serial_no="SN-DUP",
            category_id=category.id,
            owner_type=OwnerType.COMPANY,
            client_name=None,
            purchase_date=None,
            actor_id=uuid.uuid4(),
        )


async def test_create_item_raises_not_found_for_unknown_category() -> None:
    service, _ = _build_service()

    with pytest.raises(NotFoundException):
        await service.create_item(
            name="Laptop",
            serial_no="SN-1",
            category_id=uuid.uuid4(),
            owner_type=OwnerType.COMPANY,
            client_name=None,
            purchase_date=None,
            actor_id=uuid.uuid4(),
        )


async def test_edit_item_writes_device_edited_log_with_diff() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id)
    service, device_logs = _build_service(items=[item], categories=[category])

    result = await service.edit_item(item.id, updates={"name": "New Name"}, actor_id=uuid.uuid4())

    assert result.name == "New Name"
    assert len(device_logs.created) == 1
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.DEVICE_EDITED
    assert log.is_milestone is False
    assert log.log_metadata["changes"]["name"] == {"old": "Laptop", "new": "New Name"}


async def test_edit_item_no_op_update_writes_no_log() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id)
    service, device_logs = _build_service(items=[item], categories=[category])

    result = await service.edit_item(item.id, updates={"name": "Laptop"}, actor_id=uuid.uuid4())

    assert result.name == "Laptop"
    assert device_logs.created == []


async def test_edit_item_raises_not_found_for_unknown_item() -> None:
    service, _ = _build_service()

    with pytest.raises(NotFoundException):
        await service.edit_item(uuid.uuid4(), updates={"name": "New Name"}, actor_id=uuid.uuid4())


async def test_edit_item_raises_not_found_for_unknown_category() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id)
    service, _ = _build_service(items=[item], categories=[category])

    with pytest.raises(NotFoundException):
        await service.edit_item(item.id, updates={"category_id": uuid.uuid4()}, actor_id=uuid.uuid4())


async def test_change_status_to_lost_writes_marked_lost_milestone_without_auto_retire() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id, status=DeviceStatus.AVAILABLE)
    service, device_logs = _build_service(items=[item], categories=[category])

    result = await service.change_status(
        item.id, status=DeviceStatus.LOST, it_note="Reported lost", actor_id=uuid.uuid4()
    )

    assert result.status == DeviceStatus.LOST
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.MARKED_LOST
    assert log.is_milestone is True
    assert log.from_value == DeviceStatus.AVAILABLE.value
    assert log.to_value == DeviceStatus.LOST.value
    assert log.note == "Reported lost"


async def test_change_status_to_maintenance_writes_status_changed() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id, status=DeviceStatus.AVAILABLE)
    service, device_logs = _build_service(items=[item], categories=[category])

    result = await service.change_status(
        item.id, status=DeviceStatus.MAINTENANCE, it_note=None, actor_id=uuid.uuid4()
    )

    assert result.status == DeviceStatus.MAINTENANCE
    log = device_logs.created[0]
    assert log.event_type == DeviceLogEvent.STATUS_CHANGED
    assert log.is_milestone is True


async def test_get_detail_returns_none_relations_when_none_exist() -> None:
    category = _make_category()
    item = _make_item(category_id=category.id)
    service, _ = _build_service(items=[item], categories=[category])

    detail = await service.get_detail(item.id)

    assert detail.item.id == item.id
    assert detail.category.id == category.id
    assert detail.current_owner is None
    assert detail.current_request is None
    assert detail.open_support == []
    assert detail.active_handover is None


async def test_get_detail_assembles_composite_view() -> None:
    category = _make_category()
    owner = User(
        id=uuid.uuid4(),
        name="Owner",
        email="owner@techcorp.internal",
        password_hash="hash",
    )
    item = _make_item(category_id=category.id, current_owner_id=owner.id)
    request = Request(
        id=uuid.uuid4(),
        requester_id=owner.id,
        category_id=category.id,
        assigned_item_id=item.id,
        requested_from=_next_ts(),
        requested_to=_next_ts(),
        status=RequestStatus.ASSIGNED,
    )
    support = SupportRequest(
        id=uuid.uuid4(),
        item_id=item.id,
        requester_id=owner.id,
        type=SupportType.DAMAGE,
        description="Broken screen",
        status=SupportStatus.OPEN,
        filed_at=_next_ts(),
    )
    handover = HandoverRequest(
        id=uuid.uuid4(),
        item_id=item.id,
        owner_id=owner.id,
        borrower_id=uuid.uuid4(),
        status=HandoverStatus.ACCEPTED,
        requested_at=_next_ts(),
    )
    service, _ = _build_service(
        items=[item],
        categories=[category],
        users=[owner],
        requests=[request],
        support_requests=[support],
        handovers=[handover],
    )

    detail = await service.get_detail(item.id)

    assert detail.current_owner is not None
    assert detail.current_owner.id == owner.id
    assert detail.current_request is not None
    assert detail.current_request.id == request.id
    assert [s.id for s in detail.open_support] == [support.id]
    assert detail.active_handover is not None
    assert detail.active_handover.id == handover.id
