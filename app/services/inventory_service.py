"""Inventory CRUD, status changes, and the composite device-detail view.

Every write pairs with a `DeviceLogService.append(...)` call in the same
request/session (API §6): `device_created` on create, `device_edited` on
edit, and the status→event map on status change.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    HandoverStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
    UserRole,
)
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User
from app.repositories.handover_request_repository import HandoverRequestRepository
from app.repositories.item_category_repository import ItemCategoryRepository
from app.repositories.item_repository import ItemListRow, ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import SupportRequestRepository
from app.repositories.user_repository import UserRepository
from app.services.device_log_service import DeviceLogService
from app.utils.pagination import Page, PaginationParams

_STATUS_EVENT_MAP: dict[DeviceStatus, DeviceLogEvent] = {
    DeviceStatus.LOST: DeviceLogEvent.MARKED_LOST,
    DeviceStatus.RETIRED: DeviceLogEvent.RETIRED,
    DeviceStatus.RETURNED_TO_CLIENT: DeviceLogEvent.RETURNED_TO_CLIENT,
}

_EDITABLE_FIELDS = ("name", "category_id", "client_name", "purchase_date")


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID | date):
        return str(value)
    return value


@dataclass
class ItemResult:
    id: uuid.UUID
    name: str
    serial_no: str
    category_id: uuid.UUID
    owner_type: OwnerType
    client_name: str | None
    status: DeviceStatus
    current_owner_id: uuid.UUID | None
    purchase_date: date | None
    qr_code_token: uuid.UUID
    created_at: datetime
    updated_at: datetime


@dataclass
class ItemListEntry(ItemResult):
    category_name: str
    current_owner_name: str | None


@dataclass
class CategoryResult:
    id: uuid.UUID
    name: str
    description: str | None
    requires_mgr_approval: bool
    is_active: bool


@dataclass
class UserSummary:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool


@dataclass
class RequestSummary:
    id: uuid.UUID
    requester_id: uuid.UUID
    requester_name: str | None
    category_id: uuid.UUID
    assigned_item_id: uuid.UUID | None
    requested_from: datetime
    requested_to: datetime
    assigned_from: datetime | None
    assigned_to: datetime | None
    status: RequestStatus
    priority: RequestPriority
    note: str | None
    requires_mgr_approval: bool
    mgr_approval_status: MgrApprovalStatus
    manager_id: uuid.UUID | None
    manager_decision_note: str | None
    manager_decided_at: datetime | None
    it_decided_by: uuid.UUID | None
    it_decision_note: str | None
    it_decided_at: datetime | None
    rejected_by: RejectedByEnum | None
    rejected_reason: str | None
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None
    is_wfh: bool
    ship_tracking_url: str | None
    ship_initiated_at: datetime | None
    ship_completed_at: datetime | None
    return_tracking_url: str | None
    return_initiated_at: datetime | None
    completed_at: datetime | None
    completed_by: uuid.UUID | None
    completed_next_status: DeviceStatus | None
    is_client_direct: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class SupportRequestSummary:
    id: uuid.UUID
    item_id: uuid.UUID
    requester_id: uuid.UUID
    request_id: uuid.UUID | None
    type: SupportType
    description: str
    status: SupportStatus
    resolution: SupportResolution | None
    it_note: str | None
    swapped_to_item_id: uuid.UUID | None
    filed_at: datetime
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    auto_closed: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class HandoverSummary:
    id: uuid.UUID
    item_id: uuid.UUID
    owner_id: uuid.UUID
    owner_name: str | None
    borrower_id: uuid.UUID
    borrower_name: str | None
    requested_duration_hours: int | None
    status: HandoverStatus
    requested_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ItemDetail:
    item: ItemResult
    category: CategoryResult
    current_owner: UserSummary | None
    current_request: RequestSummary | None
    open_support: list[SupportRequestSummary]
    active_handover: HandoverSummary | None


def _item_result_from(item: Item) -> ItemResult:
    return ItemResult(
        id=item.id,
        name=item.name,
        serial_no=item.serial_no,
        category_id=item.category_id,
        owner_type=item.owner_type,
        client_name=item.client_name,
        status=item.status,
        current_owner_id=item.current_owner_id,
        purchase_date=item.purchase_date,
        qr_code_token=item.qr_code_token,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _item_list_entry_from(row: ItemListRow) -> ItemListEntry:
    item = row.item
    return ItemListEntry(
        id=item.id,
        name=item.name,
        serial_no=item.serial_no,
        category_id=item.category_id,
        owner_type=item.owner_type,
        client_name=item.client_name,
        status=item.status,
        current_owner_id=item.current_owner_id,
        purchase_date=item.purchase_date,
        qr_code_token=item.qr_code_token,
        created_at=item.created_at,
        updated_at=item.updated_at,
        category_name=row.category_name,
        current_owner_name=row.current_owner_name,
    )


def _category_result_from(category: ItemCategory) -> CategoryResult:
    return CategoryResult(
        id=category.id,
        name=category.name,
        description=category.description,
        requires_mgr_approval=category.requires_mgr_approval,
        is_active=category.is_active,
    )


def _user_summary_from(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
    )


def _request_summary_from(request: Request, *, requester_name: str | None) -> RequestSummary:
    return RequestSummary(
        id=request.id,
        requester_id=request.requester_id,
        requester_name=requester_name,
        category_id=request.category_id,
        assigned_item_id=request.assigned_item_id,
        requested_from=request.requested_from,
        requested_to=request.requested_to,
        assigned_from=request.assigned_from,
        assigned_to=request.assigned_to,
        status=request.status,
        priority=request.priority,
        note=request.note,
        requires_mgr_approval=request.requires_mgr_approval,
        mgr_approval_status=request.mgr_approval_status,
        manager_id=request.manager_id,
        manager_decision_note=request.manager_decision_note,
        manager_decided_at=request.manager_decided_at,
        it_decided_by=request.it_decided_by,
        it_decision_note=request.it_decision_note,
        it_decided_at=request.it_decided_at,
        rejected_by=request.rejected_by,
        rejected_reason=request.rejected_reason,
        cancelled_by=request.cancelled_by,
        cancelled_at=request.cancelled_at,
        is_wfh=request.is_wfh,
        ship_tracking_url=request.ship_tracking_url,
        ship_initiated_at=request.ship_initiated_at,
        ship_completed_at=request.ship_completed_at,
        return_tracking_url=request.return_tracking_url,
        return_initiated_at=request.return_initiated_at,
        completed_at=request.completed_at,
        completed_by=request.completed_by,
        completed_next_status=request.completed_next_status,
        is_client_direct=request.is_client_direct,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _support_summary_from(support: SupportRequest) -> SupportRequestSummary:
    return SupportRequestSummary(
        id=support.id,
        item_id=support.item_id,
        requester_id=support.requester_id,
        request_id=support.request_id,
        type=support.type,
        description=support.description,
        status=support.status,
        resolution=support.resolution,
        it_note=support.it_note,
        swapped_to_item_id=support.swapped_to_item_id,
        filed_at=support.filed_at,
        resolved_by=support.resolved_by,
        resolved_at=support.resolved_at,
        auto_closed=support.auto_closed,
        created_at=support.created_at,
        updated_at=support.updated_at,
    )


def _handover_summary_from(
    handover: HandoverRequest, *, owner_name: str | None, borrower_name: str | None
) -> HandoverSummary:
    return HandoverSummary(
        id=handover.id,
        item_id=handover.item_id,
        owner_id=handover.owner_id,
        owner_name=owner_name,
        borrower_id=handover.borrower_id,
        borrower_name=borrower_name,
        requested_duration_hours=handover.requested_duration_hours,
        status=handover.status,
        requested_at=handover.requested_at,
        decided_at=handover.decided_at,
        completed_at=handover.completed_at,
        note=handover.note,
        created_at=handover.created_at,
        updated_at=handover.updated_at,
    )


class InventoryService:
    def __init__(
        self,
        item_repository: ItemRepository,
        item_category_repository: ItemCategoryRepository,
        user_repository: UserRepository,
        request_repository: RequestRepository,
        support_request_repository: SupportRequestRepository,
        handover_request_repository: HandoverRequestRepository,
        device_log_service: DeviceLogService,
    ) -> None:
        self.item_repository = item_repository
        self.item_category_repository = item_category_repository
        self.user_repository = user_repository
        self.request_repository = request_repository
        self.support_request_repository = support_request_repository
        self.handover_request_repository = handover_request_repository
        self.device_log_service = device_log_service

    async def list_items(
        self,
        *,
        category_id: uuid.UUID | None,
        status: DeviceStatus | None,
        owner_type: OwnerType | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[ItemListEntry]:
        page = await self.item_repository.list_items(
            category_id=category_id,
            status=status,
            owner_type=owner_type,
            search=search,
            pagination=pagination,
        )
        return Page(
            items=[_item_list_entry_from(row) for row in page.items],
            total_items=page.total_items,
            page=page.page,
            page_size=page.page_size,
        )

    async def create_item(
        self,
        *,
        name: str,
        serial_no: str,
        category_id: uuid.UUID,
        owner_type: OwnerType,
        client_name: str | None,
        purchase_date: date | None,
        actor_id: uuid.UUID,
    ) -> ItemResult:
        if await self.item_category_repository.get_by_id(category_id) is None:
            raise NotFoundException(message="Item category not found.")
        if await self.item_repository.get_by_serial_no(serial_no) is not None:
            raise ConflictException(message=f"An item with serial number '{serial_no}' already exists.")

        item = Item(
            name=name,
            serial_no=serial_no,
            category_id=category_id,
            owner_type=owner_type,
            client_name=client_name if owner_type == OwnerType.CLIENT else None,
            status=DeviceStatus.AVAILABLE,
            purchase_date=purchase_date,
        )
        created = await self.item_repository.create(item)

        await self.device_log_service.append(
            item_id=created.id,
            event_type=DeviceLogEvent.DEVICE_CREATED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            to_value=DeviceStatus.AVAILABLE.value,
        )
        return _item_result_from(created)

    async def edit_item(
        self, item_id: uuid.UUID, *, updates: dict[str, Any], actor_id: uuid.UUID
    ) -> ItemResult:
        item = await self._get_item_or_404(item_id)

        new_category_id = updates.get("category_id")
        if (
            new_category_id is not None
            and await self.item_category_repository.get_by_id(new_category_id) is None
        ):
            raise NotFoundException(message="Item category not found.")

        changes: dict[str, dict[str, Any]] = {}
        for field in _EDITABLE_FIELDS:
            if field not in updates:
                continue
            new_value = updates[field]
            old_value = getattr(item, field)
            if new_value == old_value:
                continue
            changes[field] = {"old": _jsonable(old_value), "new": _jsonable(new_value)}
            setattr(item, field, new_value)

        updated = await self.item_repository.update(item)

        if changes:
            await self.device_log_service.append(
                item_id=updated.id,
                event_type=DeviceLogEvent.DEVICE_EDITED,
                actor_id=actor_id,
                actor_role=ActorRole.IT_ADMIN,
                metadata={"changes": changes},
            )
        return _item_result_from(updated)

    async def change_status(
        self, item_id: uuid.UUID, *, status: DeviceStatus, it_note: str | None, actor_id: uuid.UUID
    ) -> ItemResult:
        item = await self._get_item_or_404(item_id)
        from_status = item.status
        item.status = status
        updated = await self.item_repository.update(item)

        await self.device_log_service.append(
            item_id=updated.id,
            event_type=_STATUS_EVENT_MAP.get(status, DeviceLogEvent.STATUS_CHANGED),
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            from_value=from_status.value,
            to_value=status.value,
            note=it_note,
        )
        return _item_result_from(updated)

    async def get_detail(self, item_id: uuid.UUID) -> ItemDetail:
        item = await self._get_item_or_404(item_id)

        category = await self.item_category_repository.get_by_id(item.category_id)
        if category is None:
            raise NotFoundException(message="Item category not found.")

        owner = None
        if item.current_owner_id is not None:
            owner = await self.user_repository.get_by_id(item.current_owner_id)

        current_request = await self.request_repository.get_active_for_item(item.id)
        open_support = await self.support_request_repository.list_open_for_item(item.id)
        active_handover = await self.handover_request_repository.get_accepted_for_item(item.id)

        request_summary = None
        if current_request is not None:
            requester = (
                owner
                if owner is not None and owner.id == current_request.requester_id
                else await self.user_repository.get_by_id(current_request.requester_id)
            )
            request_summary = _request_summary_from(
                current_request, requester_name=requester.name if requester is not None else None
            )

        handover_summary = None
        if active_handover is not None:
            handover_owner = await self.user_repository.get_by_id(active_handover.owner_id)
            handover_borrower = await self.user_repository.get_by_id(active_handover.borrower_id)
            handover_summary = _handover_summary_from(
                active_handover,
                owner_name=handover_owner.name if handover_owner is not None else None,
                borrower_name=handover_borrower.name if handover_borrower is not None else None,
            )

        return ItemDetail(
            item=_item_result_from(item),
            category=_category_result_from(category),
            current_owner=_user_summary_from(owner) if owner is not None else None,
            current_request=request_summary,
            open_support=[_support_summary_from(support) for support in open_support],
            active_handover=handover_summary,
        )

    async def _get_item_or_404(self, item_id: uuid.UUID) -> Item:
        item = await self.item_repository.get_by_id(item_id)
        if item is None:
            raise NotFoundException(message="Item not found.")
        return item
