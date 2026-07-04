"""WFH outbound shipping and returns (API §10/§11): outbound/returns
queues, ship, confirm-delivery, complete-return with the support
auto-close cascade.

`complete_return` writes `item` + `request` in the same session and pairs
the write with `DeviceLogService.append(...)` milestones, per the
device-log discipline in `specs/00_CONTEXT.md`. The auto-close cascade
queries `support_request` rows directly via `SupportRequestRepository`
rather than importing M10's service, per the M9 spec's no-hard-dependency
note.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    MgrApprovalStatus,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    SupportStatus,
)
from app.models.item import Item
from app.models.request import Request
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository, ShippingQueueRow
from app.repositories.support_request_repository import SupportRequestRepository
from app.services.device_log_service import DeviceLogService

_RETURN_ELIGIBLE_STATUSES = (DeviceStatus.ASSIGNED, DeviceStatus.RETURN_SHIPPING_PENDING)


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
class ShippingQueueResult(RequestResult):
    item_name: str
    requester_name: str


def _request_result_from(request: Request) -> RequestResult:
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


def _queue_result_from(row: ShippingQueueRow) -> ShippingQueueResult:
    request = row.request
    return ShippingQueueResult(
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
        item_name=row.item_name,
        requester_name=row.requester_name,
    )


class ShippingService:
    def __init__(
        self,
        request_repository: RequestRepository,
        item_repository: ItemRepository,
        support_request_repository: SupportRequestRepository,
        device_log_service: DeviceLogService,
    ) -> None:
        self.request_repository = request_repository
        self.item_repository = item_repository
        self.support_request_repository = support_request_repository
        self.device_log_service = device_log_service

    async def list_outbound(self) -> list[ShippingQueueResult]:
        rows = await self.request_repository.list_outbound_shipping_queue()
        return [_queue_result_from(row) for row in rows]

    async def list_returns(self) -> list[ShippingQueueResult]:
        rows = await self.request_repository.list_return_shipping_queue()
        return [_queue_result_from(row) for row in rows]

    async def ship(
        self, request_id: uuid.UUID, *, ship_tracking_url: str, actor_id: uuid.UUID
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if not request.is_wfh:
            raise ValidationException(message="Only WFH requests can be shipped.")

        item = await self._get_assigned_item_or_404(request)
        if item.status != DeviceStatus.ASSIGNED:
            raise ConflictException(message="Only assigned devices can be marked shipped.")

        request.ship_tracking_url = ship_tracking_url
        request.ship_initiated_at = datetime.now(UTC)
        item.status = DeviceStatus.SHIPPING_PENDING

        updated_request = await self.request_repository.update(request)
        await self.item_repository.update(item)

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.SHIP_OUTBOUND_INITIATED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=updated_request.id,
            from_value=DeviceStatus.ASSIGNED.value,
            to_value=DeviceStatus.SHIPPING_PENDING.value,
            metadata={"ship_tracking_url": ship_tracking_url},
        )
        return _request_result_from(updated_request)

    async def confirm_delivery(self, request_id: uuid.UUID, *, actor_id: uuid.UUID) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        item = await self._get_assigned_item_or_404(request)
        if item.status != DeviceStatus.SHIPPING_PENDING:
            raise ConflictException(
                message="Only devices currently shipping_pending can have delivery confirmed."
            )

        request.ship_completed_at = datetime.now(UTC)
        item.status = DeviceStatus.ASSIGNED

        updated_request = await self.request_repository.update(request)
        await self.item_repository.update(item)

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.SHIP_OUTBOUND_COMPLETED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=updated_request.id,
            from_value=DeviceStatus.SHIPPING_PENDING.value,
            to_value=DeviceStatus.ASSIGNED.value,
        )
        return _request_result_from(updated_request)

    async def complete_return(
        self, request_id: uuid.UUID, *, next_status: DeviceStatus, actor_id: uuid.UUID
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        item = await self._get_assigned_item_or_404(request)
        if item.status not in _RETURN_ELIGIBLE_STATUSES:
            raise ConflictException(
                message="Device must be assigned (on-site) or return_shipping_pending (WFH) to "
                "complete a return."
            )

        from_status = item.status.value
        request.status = RequestStatus.COMPLETED
        request.completed_at = datetime.now(UTC)
        request.completed_by = actor_id
        request.completed_next_status = next_status
        item.status = next_status
        item.current_owner_id = None

        updated_request = await self.request_repository.update(request)
        updated_item = await self.item_repository.update(item)

        await self.device_log_service.append(
            item_id=updated_item.id,
            event_type=DeviceLogEvent.RETURN_RECEIVED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=updated_request.id,
            from_value=from_status,
            to_value=next_status.value,
        )
        await self.device_log_service.append(
            item_id=updated_item.id,
            event_type=DeviceLogEvent.ASSIGNMENT_COMPLETED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=updated_request.id,
        )
        await self._auto_close_open_support(updated_item.id)

        return _request_result_from(updated_request)

    async def _auto_close_open_support(self, item_id: uuid.UUID) -> None:
        open_tickets = await self.support_request_repository.list_open_for_item(item_id)
        for ticket in open_tickets:
            ticket.status = SupportStatus.RESOLVED
            ticket.auto_closed = True
            ticket.resolved_at = datetime.now(UTC)
            await self.support_request_repository.update(ticket)
            await self.device_log_service.append(
                item_id=item_id,
                event_type=DeviceLogEvent.SUPPORT_AUTO_CLOSED,
                actor_id=None,
                actor_role=ActorRole.SYSTEM,
                support_request_id=ticket.id,
            )

    async def _get_request_or_404(self, request_id: uuid.UUID) -> Request:
        request = await self.request_repository.get_by_id(request_id)
        if request is None:
            raise NotFoundException(message="Request not found.")
        return request

    async def _get_assigned_item_or_404(self, request: Request) -> Item:
        if request.assigned_item_id is None:
            raise ConflictException(message="This request has no assigned device.")
        item = await self.item_repository.get_by_id(request.assigned_item_id)
        if item is None:
            raise NotFoundException(message="Item not found.")
        return item
