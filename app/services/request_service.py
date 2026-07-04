"""Request listing/detail and the IT approval queue actions (API §2/§3):
reject, cancel, escalate-to-manager. Assignment itself is M8's concern.

Reject/cancel/escalate never touch an `item` row (a `pending_it_approval`
or otherwise non-terminal request has no `assigned_item_id` yet), so none
of these call `DeviceLogService` — logs are only for device-touching
writes.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import (
    DeviceStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
)
from app.models.item import Item
from app.models.request import Request
from app.repositories.request_repository import RequestDetailRow, RequestListRow, RequestRepository
from app.repositories.user_repository import UserRepository
from app.utils.pagination import Page, PaginationParams

_TERMINAL_STATUSES = (RequestStatus.COMPLETED, RequestStatus.REJECTED, RequestStatus.CANCELLED)


@dataclass
class RequestResult:
    id: uuid.UUID
    requester_id: uuid.UUID
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
class RequestListEntry(RequestResult):
    category_name: str
    requester_name: str


@dataclass
class AssignedItemSummary:
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


@dataclass
class RequestDetail(RequestResult):
    category_name: str
    requester_name: str
    manager_name: str | None
    it_decided_by_name: str | None
    cancelled_by_name: str | None
    completed_by_name: str | None
    item: AssignedItemSummary | None


def _result_from(request: Request) -> RequestResult:
    return RequestResult(
        id=request.id,
        requester_id=request.requester_id,
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


def _list_entry_from(row: RequestListRow) -> RequestListEntry:
    request = row.request
    return RequestListEntry(
        id=request.id,
        requester_id=request.requester_id,
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
        category_name=row.category_name,
        requester_name=row.requester_name,
    )


def _item_summary_from(item: Item) -> AssignedItemSummary:
    return AssignedItemSummary(
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
    )


def _detail_from(row: RequestDetailRow) -> RequestDetail:
    request = row.request
    return RequestDetail(
        id=request.id,
        requester_id=request.requester_id,
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
        category_name=row.category_name,
        requester_name=row.requester_name,
        manager_name=row.manager_name,
        it_decided_by_name=row.it_decided_by_name,
        cancelled_by_name=row.cancelled_by_name,
        completed_by_name=row.completed_by_name,
        item=_item_summary_from(row.item) if row.item is not None else None,
    )


class RequestService:
    def __init__(self, request_repository: RequestRepository, user_repository: UserRepository) -> None:
        self.request_repository = request_repository
        self.user_repository = user_repository

    async def list_requests(
        self,
        *,
        status: RequestStatus | None,
        category_id: uuid.UUID | None,
        priority: RequestPriority | None,
        requested_from: datetime | None,
        requested_to: datetime | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[RequestListEntry]:
        page = await self.request_repository.list_requests(
            status=status,
            category_id=category_id,
            priority=priority,
            requested_from=requested_from,
            requested_to=requested_to,
            search=search,
            pagination=pagination,
        )
        return Page(
            items=[_list_entry_from(row) for row in page.items],
            total_items=page.total_items,
            page=page.page,
            page_size=page.page_size,
        )

    async def list_it_approvals(self, *, pagination: PaginationParams) -> Page[RequestListEntry]:
        page = await self.request_repository.list_it_approvals(pagination=pagination)
        return Page(
            items=[_list_entry_from(row) for row in page.items],
            total_items=page.total_items,
            page=page.page,
            page_size=page.page_size,
        )

    async def get_detail(self, request_id: uuid.UUID) -> RequestDetail:
        row = await self.request_repository.get_detail(request_id)
        if row is None:
            raise NotFoundException(message="Request not found.")
        return _detail_from(row)

    async def reject(
        self,
        request_id: uuid.UUID,
        *,
        rejected_reason: str,
        it_decision_note: str | None,
        actor_id: uuid.UUID,
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if request.status != RequestStatus.PENDING_IT_APPROVAL:
            raise ConflictException(message="Only requests pending IT approval can be rejected.")

        request.status = RequestStatus.REJECTED
        request.rejected_by = RejectedByEnum.IT_ADMIN
        request.rejected_reason = rejected_reason
        request.it_decision_note = it_decision_note
        request.it_decided_by = actor_id
        request.it_decided_at = datetime.now(UTC)
        updated = await self.request_repository.update(request)
        return _result_from(updated)

    async def cancel(
        self, request_id: uuid.UUID, *, rejected_reason: str, actor_id: uuid.UUID
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if request.status in _TERMINAL_STATUSES:
            raise ConflictException(
                message="Cannot cancel a request that has already reached a terminal state."
            )

        request.status = RequestStatus.CANCELLED
        request.cancelled_by = actor_id
        request.cancelled_at = datetime.now(UTC)
        request.rejected_by = RejectedByEnum.IT_ADMIN_CANCEL
        request.rejected_reason = rejected_reason
        updated = await self.request_repository.update(request)
        return _result_from(updated)

    async def escalate_to_manager(
        self, request_id: uuid.UUID, *, manager_id: uuid.UUID | None
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if request.status != RequestStatus.PENDING_IT_APPROVAL or request.requires_mgr_approval:
            raise ConflictException(
                message="Only requests pending IT approval that have not yet required manager "
                "approval can be escalated."
            )

        resolved_manager_id = manager_id
        if resolved_manager_id is None:
            requester = await self.user_repository.get_by_id(request.requester_id)
            resolved_manager_id = requester.manager_id if requester is not None else None

        request.requires_mgr_approval = True
        request.mgr_approval_status = MgrApprovalStatus.PENDING
        request.manager_id = resolved_manager_id
        request.status = RequestStatus.PENDING_MGR_APPROVAL
        updated = await self.request_repository.update(request)
        return _result_from(updated)

    async def _get_request_or_404(self, request_id: uuid.UUID) -> Request:
        request = await self.request_repository.get_by_id(request_id)
        if request is None:
            raise NotFoundException(message="Request not found.")
        return request
