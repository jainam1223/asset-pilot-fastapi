"""Extension-request review (API §9): IT approves or rejects an
assignment end-date extension. Approve moves the parent request's
`assigned_to` to the extension's `extended_to`; both actions write a
non-milestone `device_log` entry against the parent's item, per the
device-log discipline in `specs/00_CONTEXT.md`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    ExtensionStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    UserRole,
)
from app.models.extension_request import ExtensionRequest
from app.models.item import Item
from app.models.request import Request
from app.models.user import User
from app.repositories.extension_request_repository import (
    ExtensionDetailRow,
    ExtensionListRow,
    ExtensionRequestRepository,
)
from app.repositories.request_repository import RequestRepository
from app.services.device_log_service import DeviceLogService

_MGR_APPROVAL_STATUSES_ALLOWING_IT_APPROVAL = (MgrApprovalStatus.NOT_REQUIRED, MgrApprovalStatus.APPROVED)


@dataclass
class ExtensionResult:
    id: uuid.UUID
    original_request_id: uuid.UUID
    requester_id: uuid.UUID
    current_assigned_to: datetime
    extended_to: datetime
    status: ExtensionStatus
    requires_mgr_approval: bool
    manager_id: uuid.UUID | None
    mgr_approval_status: MgrApprovalStatus
    manager_note: str | None
    manager_decided_at: datetime | None
    it_decided_by: uuid.UUID | None
    it_note: str | None
    it_decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ExtensionListResult(ExtensionResult):
    item_name: str
    requester_name: str


@dataclass
class ExtensionParentRequestSummary:
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
class ExtensionItemSummary:
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
class ExtensionRequesterSummary:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class ExtensionDetailResult(ExtensionResult):
    request: ExtensionParentRequestSummary
    item: ExtensionItemSummary
    requester: ExtensionRequesterSummary


def _result_from(extension_request: ExtensionRequest) -> ExtensionResult:
    return ExtensionResult(
        id=extension_request.id,
        original_request_id=extension_request.original_request_id,
        requester_id=extension_request.requester_id,
        current_assigned_to=extension_request.current_assigned_to,
        extended_to=extension_request.extended_to,
        status=extension_request.status,
        requires_mgr_approval=extension_request.requires_mgr_approval,
        manager_id=extension_request.manager_id,
        mgr_approval_status=extension_request.mgr_approval_status,
        manager_note=extension_request.manager_note,
        manager_decided_at=extension_request.manager_decided_at,
        it_decided_by=extension_request.it_decided_by,
        it_note=extension_request.it_note,
        it_decided_at=extension_request.it_decided_at,
        created_at=extension_request.created_at,
        updated_at=extension_request.updated_at,
    )


def _list_result_from(row: ExtensionListRow) -> ExtensionListResult:
    extension_request = row.extension_request
    return ExtensionListResult(
        id=extension_request.id,
        original_request_id=extension_request.original_request_id,
        requester_id=extension_request.requester_id,
        current_assigned_to=extension_request.current_assigned_to,
        extended_to=extension_request.extended_to,
        status=extension_request.status,
        requires_mgr_approval=extension_request.requires_mgr_approval,
        manager_id=extension_request.manager_id,
        mgr_approval_status=extension_request.mgr_approval_status,
        manager_note=extension_request.manager_note,
        manager_decided_at=extension_request.manager_decided_at,
        it_decided_by=extension_request.it_decided_by,
        it_note=extension_request.it_note,
        it_decided_at=extension_request.it_decided_at,
        created_at=extension_request.created_at,
        updated_at=extension_request.updated_at,
        item_name=row.item_name,
        requester_name=row.requester_name,
    )


def _request_summary_from(request: Request) -> ExtensionParentRequestSummary:
    return ExtensionParentRequestSummary(
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


def _item_summary_from(item: Item) -> ExtensionItemSummary:
    return ExtensionItemSummary(
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


def _requester_summary_from(user: User) -> ExtensionRequesterSummary:
    return ExtensionRequesterSummary(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _detail_result_from(row: ExtensionDetailRow) -> ExtensionDetailResult:
    extension_request = row.extension_request
    return ExtensionDetailResult(
        id=extension_request.id,
        original_request_id=extension_request.original_request_id,
        requester_id=extension_request.requester_id,
        current_assigned_to=extension_request.current_assigned_to,
        extended_to=extension_request.extended_to,
        status=extension_request.status,
        requires_mgr_approval=extension_request.requires_mgr_approval,
        manager_id=extension_request.manager_id,
        mgr_approval_status=extension_request.mgr_approval_status,
        manager_note=extension_request.manager_note,
        manager_decided_at=extension_request.manager_decided_at,
        it_decided_by=extension_request.it_decided_by,
        it_note=extension_request.it_note,
        it_decided_at=extension_request.it_decided_at,
        created_at=extension_request.created_at,
        updated_at=extension_request.updated_at,
        request=_request_summary_from(row.request),
        item=_item_summary_from(row.item),
        requester=_requester_summary_from(row.requester),
    )


class ExtensionService:
    def __init__(
        self,
        extension_request_repository: ExtensionRequestRepository,
        request_repository: RequestRepository,
        device_log_service: DeviceLogService,
    ) -> None:
        self.extension_request_repository = extension_request_repository
        self.request_repository = request_repository
        self.device_log_service = device_log_service

    async def list_extension_requests(self, *, status: ExtensionStatus | None) -> list[ExtensionListResult]:
        rows = await self.extension_request_repository.list_filtered(status=status)
        return [_list_result_from(row) for row in rows]

    async def get_detail(self, extension_request_id: uuid.UUID) -> ExtensionDetailResult:
        row = await self.extension_request_repository.get_detail(extension_request_id)
        if row is None:
            raise NotFoundException(message="Extension request not found.")
        return _detail_result_from(row)

    async def approve(
        self, extension_request_id: uuid.UUID, *, it_note: str | None, actor_id: uuid.UUID
    ) -> ExtensionResult:
        extension_request = await self._get_extension_or_404(extension_request_id)
        if extension_request.status != ExtensionStatus.PENDING:
            raise ConflictException(message="Only pending extension requests can be approved.")
        if extension_request.mgr_approval_status not in _MGR_APPROVAL_STATUSES_ALLOWING_IT_APPROVAL:
            raise ConflictException(
                message="This extension is awaiting manager approval and cannot be approved yet."
            )

        parent_request = await self._get_parent_request_or_404(extension_request.original_request_id)
        parent_request.assigned_to = extension_request.extended_to
        await self.request_repository.update(parent_request)

        extension_request.status = ExtensionStatus.APPROVED
        extension_request.it_decided_by = actor_id
        extension_request.it_note = it_note
        extension_request.it_decided_at = datetime.now(UTC)
        updated = await self.extension_request_repository.update(extension_request)

        assert parent_request.assigned_item_id is not None
        await self.device_log_service.append(
            item_id=parent_request.assigned_item_id,
            event_type=DeviceLogEvent.EXTENSION_APPROVED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=parent_request.id,
            extension_request_id=updated.id,
            is_milestone=False,
        )
        return _result_from(updated)

    async def reject(
        self, extension_request_id: uuid.UUID, *, it_note: str | None, actor_id: uuid.UUID
    ) -> ExtensionResult:
        extension_request = await self._get_extension_or_404(extension_request_id)
        if extension_request.status != ExtensionStatus.PENDING:
            raise ConflictException(message="Only pending extension requests can be rejected.")

        parent_request = await self._get_parent_request_or_404(extension_request.original_request_id)

        extension_request.status = ExtensionStatus.REJECTED
        extension_request.it_decided_by = actor_id
        extension_request.it_note = it_note
        extension_request.it_decided_at = datetime.now(UTC)
        updated = await self.extension_request_repository.update(extension_request)

        assert parent_request.assigned_item_id is not None
        await self.device_log_service.append(
            item_id=parent_request.assigned_item_id,
            event_type=DeviceLogEvent.EXTENSION_REJECTED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=parent_request.id,
            extension_request_id=updated.id,
            is_milestone=False,
        )
        return _result_from(updated)

    async def _get_extension_or_404(self, extension_request_id: uuid.UUID) -> ExtensionRequest:
        extension_request = await self.extension_request_repository.get_by_id(extension_request_id)
        if extension_request is None:
            raise NotFoundException(message="Extension request not found.")
        return extension_request

    async def _get_parent_request_or_404(self, request_id: uuid.UUID) -> Request:
        request = await self.request_repository.get_by_id(request_id)
        if request is None:
            raise NotFoundException(message="The parent request was not found.")
        return request
