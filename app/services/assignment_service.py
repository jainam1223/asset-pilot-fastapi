"""Assignment engine (API §4/§5): suggested devices, device booking
calendar, booking-range adjustment, request assignment, and client-owned
device direct-assign.

Both `assign` and `direct_assign` write `item` + `request` in the same
session and pair the write with a `DeviceLogService.append(...)` milestone,
per the device-log discipline in `specs/00_CONTEXT.md`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
)
from app.models.item import Item
from app.models.request import Request
from app.repositories.item_repository import ClientAvailableRow, ItemRepository, SuggestedDeviceRow
from app.repositories.request_repository import BookingRow, RequestRepository
from app.repositories.user_repository import UserRepository
from app.services.device_log_service import DeviceLogService


@dataclass
class SuggestedDeviceResult:
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
    category_name: str
    active_bookings_count: int


@dataclass
class ClientAvailableResult:
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
    category_name: str


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
class BookingResult(RequestResult):
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


def _booking_result_from(row: BookingRow) -> BookingResult:
    request = row.request
    return BookingResult(
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
        requester_name=row.requester_name,
    )


def _suggested_device_result_from(row: SuggestedDeviceRow) -> SuggestedDeviceResult:
    item = row.item
    return SuggestedDeviceResult(
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
        active_bookings_count=row.active_bookings_count,
    )


def _client_available_result_from(row: ClientAvailableRow) -> ClientAvailableResult:
    item = row.item
    return ClientAvailableResult(
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
    )


class AssignmentService:
    def __init__(
        self,
        item_repository: ItemRepository,
        request_repository: RequestRepository,
        user_repository: UserRepository,
        device_log_service: DeviceLogService,
    ) -> None:
        self.item_repository = item_repository
        self.request_repository = request_repository
        self.user_repository = user_repository
        self.device_log_service = device_log_service

    async def suggested_devices(self, request_id: uuid.UUID) -> list[SuggestedDeviceResult]:
        request = await self._get_request_or_404(request_id)
        rows = await self.item_repository.list_suggested_devices(
            category_id=request.category_id,
            requested_from=request.requested_from,
            requested_to=request.requested_to,
        )
        return [_suggested_device_result_from(row) for row in rows]

    async def item_bookings(self, item_id: uuid.UUID) -> list[BookingResult]:
        await self._get_item_or_404(item_id)
        rows = await self.request_repository.list_bookings_for_item(item_id)
        return [_booking_result_from(row) for row in rows]

    async def update_booking_range(
        self, request_id: uuid.UUID, *, assigned_from: datetime, assigned_to: datetime
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if request.status != RequestStatus.ASSIGNED:
            raise ConflictException(message="Only assigned requests have a booking range to adjust.")

        assert request.assigned_item_id is not None
        if await self.request_repository.has_overlapping_assigned_booking(
            request.assigned_item_id, assigned_from, assigned_to, exclude_request_id=request.id
        ):
            raise ConflictException(message="The new range overlaps another active booking for this device.")

        request.assigned_from = assigned_from
        request.assigned_to = assigned_to
        updated = await self.request_repository.update(request)
        # Notifying the affected requester is a no-op stub — no mailer is built (see CLAUDE.md §7).
        return _request_result_from(updated)

    async def assign(
        self,
        request_id: uuid.UUID,
        *,
        item_id: uuid.UUID,
        assigned_from: datetime,
        assigned_to: datetime,
        is_wfh: bool,
        actor_id: uuid.UUID,
    ) -> RequestResult:
        request = await self._get_request_or_404(request_id)
        if request.status != RequestStatus.PENDING_IT_APPROVAL:
            raise ConflictException(message="Only requests pending IT approval can be assigned.")

        item = await self._get_item_or_404(item_id)
        if item.status != DeviceStatus.AVAILABLE:
            raise ConflictException(message="Only available devices can be assigned.")
        if item.category_id != request.category_id:
            raise ValidationException(message="The device category does not match the request's category.")
        if await self.request_repository.has_overlapping_assigned_booking(
            item_id, assigned_from, assigned_to, exclude_request_id=request.id
        ):
            raise ConflictException(
                message="The chosen dates overlap another active booking for this device."
            )

        request.assigned_item_id = item_id
        request.assigned_from = assigned_from
        request.assigned_to = assigned_to
        request.is_wfh = is_wfh
        request.it_decided_by = actor_id
        request.it_decided_at = datetime.now(UTC)
        request.status = RequestStatus.ASSIGNED

        item.status = DeviceStatus.ASSIGNED
        item.current_owner_id = request.requester_id

        try:
            updated_request = await self.request_repository.update(request)
            await self.item_repository.update(item)
        except IntegrityError as exc:
            raise ConflictException(
                message="This device was just assigned to another active request."
            ) from exc

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.ASSIGNED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=updated_request.id,
            from_value=DeviceStatus.AVAILABLE.value,
            to_value=DeviceStatus.ASSIGNED.value,
        )
        return _request_result_from(updated_request)

    async def client_available(
        self, *, category_id: uuid.UUID | None, search: str | None
    ) -> list[ClientAvailableResult]:
        rows = await self.item_repository.list_client_available(category_id=category_id, search=search)
        return [_client_available_result_from(row) for row in rows]

    async def direct_assign(
        self,
        item_id: uuid.UUID,
        *,
        employee_id: uuid.UUID,
        assigned_from: datetime,
        assigned_to: datetime,
        actor_id: uuid.UUID,
    ) -> RequestResult:
        item = await self._get_item_or_404(item_id)
        if item.owner_type != OwnerType.CLIENT:
            raise ValidationException(message="Direct-assign is only valid for client-owned devices.")
        if item.status != DeviceStatus.AVAILABLE:
            raise ConflictException(message="Only available devices can be directly assigned.")

        employee = await self.user_repository.get_by_id(employee_id)
        if employee is None:
            raise NotFoundException(message="Employee not found.")

        request = Request(
            requester_id=employee_id,
            category_id=item.category_id,
            assigned_item_id=item_id,
            requested_from=assigned_from,
            requested_to=assigned_to,
            assigned_from=assigned_from,
            assigned_to=assigned_to,
            status=RequestStatus.ASSIGNED,
            is_client_direct=True,
            it_decided_by=actor_id,
            it_decided_at=datetime.now(UTC),
        )
        item.status = DeviceStatus.ASSIGNED
        item.current_owner_id = employee_id

        try:
            created_request = await self.request_repository.create(request)
            await self.item_repository.update(item)
        except IntegrityError as exc:
            raise ConflictException(
                message="This device was just assigned to another active request."
            ) from exc

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.CLIENT_ASSIGNED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=created_request.id,
            from_value=DeviceStatus.AVAILABLE.value,
            to_value=DeviceStatus.ASSIGNED.value,
        )
        return _request_result_from(created_request)

    async def _get_request_or_404(self, request_id: uuid.UUID) -> Request:
        request = await self.request_repository.get_by_id(request_id)
        if request is None:
            raise NotFoundException(message="Request not found.")
        return request

    async def _get_item_or_404(self, item_id: uuid.UUID) -> Item:
        item = await self.item_repository.get_by_id(item_id)
        if item is None:
            raise NotFoundException(message="Item not found.")
        return item
