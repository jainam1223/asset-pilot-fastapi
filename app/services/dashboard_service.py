"""Aggregate KPI endpoints for the admin dashboard landing screen (API §1).

The five summary aggregates are independent COUNT/GROUP BY queries across
five tables, but all repositories here share one request-scoped
`AsyncSession` (`get_db_session`) — a single `AsyncSession` cannot run
concurrent queries, so they are awaited sequentially rather than via
`asyncio.gather`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.models.enums import (
    DeviceStatus,
    MgrApprovalStatus,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
)
from app.repositories.extension_request_repository import ExtensionRequestRepository
from app.repositories.handover_request_repository import HandoverRequestRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestListRow, RequestRepository
from app.repositories.support_request_repository import SupportListRow, SupportRequestRepository

_STATUS_BREAKDOWN_STATUSES = (
    DeviceStatus.AVAILABLE,
    DeviceStatus.ASSIGNED,
    DeviceStatus.UNDER_REPAIR,
    DeviceStatus.MAINTENANCE,
    DeviceStatus.SHIPPING_PENDING,
    DeviceStatus.RETURN_SHIPPING_PENDING,
    DeviceStatus.LOST,
    DeviceStatus.RETIRED,
)


@dataclass
class DashboardSummary:
    status_breakdown: dict[str, int]
    pending_requests_count: int
    open_support_count: int
    active_handovers_count: int
    pending_extensions_count: int


@dataclass
class RecentRequestEntry:
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
    category_name: str
    requester_name: str


@dataclass
class OpenSupportEntry:
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
    item_name: str
    requester_name: str


def _recent_request_from(row: RequestListRow) -> RecentRequestEntry:
    request = row.request
    return RecentRequestEntry(
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


def _open_support_from(row: SupportListRow) -> OpenSupportEntry:
    support_request = row.support_request
    return OpenSupportEntry(
        id=support_request.id,
        item_id=support_request.item_id,
        requester_id=support_request.requester_id,
        request_id=support_request.request_id,
        type=support_request.type,
        description=support_request.description,
        status=support_request.status,
        resolution=support_request.resolution,
        it_note=support_request.it_note,
        swapped_to_item_id=support_request.swapped_to_item_id,
        filed_at=support_request.filed_at,
        resolved_by=support_request.resolved_by,
        resolved_at=support_request.resolved_at,
        auto_closed=support_request.auto_closed,
        created_at=support_request.created_at,
        updated_at=support_request.updated_at,
        item_name=row.item_name,
        requester_name=row.requester_name,
    )


class DashboardService:
    def __init__(
        self,
        item_repository: ItemRepository,
        request_repository: RequestRepository,
        support_request_repository: SupportRequestRepository,
        handover_request_repository: HandoverRequestRepository,
        extension_request_repository: ExtensionRequestRepository,
    ) -> None:
        self.item_repository = item_repository
        self.request_repository = request_repository
        self.support_request_repository = support_request_repository
        self.handover_request_repository = handover_request_repository
        self.extension_request_repository = extension_request_repository

    async def get_summary(self) -> DashboardSummary:
        status_counts = await self.item_repository.count_by_status()
        pending_requests_count = await self.request_repository.count_pending()
        open_support_count = await self.support_request_repository.count_open()
        active_handovers_count = await self.handover_request_repository.count_active()
        pending_extensions_count = await self.extension_request_repository.count_pending()

        status_breakdown = {
            status.value: status_counts.get(status, 0) for status in _STATUS_BREAKDOWN_STATUSES
        }
        return DashboardSummary(
            status_breakdown=status_breakdown,
            pending_requests_count=pending_requests_count,
            open_support_count=open_support_count,
            active_handovers_count=active_handovers_count,
            pending_extensions_count=pending_extensions_count,
        )

    async def get_recent_requests(self, *, limit: int) -> list[RecentRequestEntry]:
        rows = await self.request_repository.list_recent(limit=limit)
        return [_recent_request_from(row) for row in rows]

    async def get_open_support(self, *, limit: int) -> list[OpenSupportEntry]:
        rows = await self.support_request_repository.list_open(limit=limit)
        return [_open_support_from(row) for row in rows]
