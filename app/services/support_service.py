"""Support queue (API §8): list/detail, mark-in-progress, and resolve with
the 4 resolutions — including the swap flow (repoint the tied request,
transition both items, `swapped_out`/`swapped_in` logs) and marked_lost
(item→lost, complete the tied request with `completed_next_status = NULL`,
per F6 in `specs/00_CONTEXT.md`).

Every device-touching branch pairs its write with a
`DeviceLogService.append(...)` call in the same transaction, per the
device-log discipline in `specs/00_CONTEXT.md`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    OwnerType,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
    UserRole,
)
from app.models.item import Item
from app.models.support_request import SupportRequest
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import (
    SupportDetailRow,
    SupportListRow,
    SupportRequestRepository,
)
from app.services.device_log_service import DeviceLogService


@dataclass
class SupportRequestResult:
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
class SupportListResult(SupportRequestResult):
    item_name: str
    requester_name: str


@dataclass
class SupportItemSummary:
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
class SupportRequesterSummary:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class SupportDetailResult(SupportRequestResult):
    item: SupportItemSummary
    requester: SupportRequesterSummary


def _result_from(support_request: SupportRequest) -> SupportRequestResult:
    return SupportRequestResult(
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
    )


def _list_result_from(row: SupportListRow) -> SupportListResult:
    support_request = row.support_request
    return SupportListResult(
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


def _item_summary_from(item: Item) -> SupportItemSummary:
    return SupportItemSummary(
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


def _detail_result_from(row: SupportDetailRow) -> SupportDetailResult:
    support_request = row.support_request
    requester = row.requester
    return SupportDetailResult(
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
        item=_item_summary_from(row.item),
        requester=SupportRequesterSummary(
            id=requester.id,
            name=requester.name,
            email=requester.email,
            role=requester.role,
            manager_id=requester.manager_id,
            is_active=requester.is_active,
            created_at=requester.created_at,
            updated_at=requester.updated_at,
        ),
    )


class SupportService:
    def __init__(
        self,
        support_request_repository: SupportRequestRepository,
        item_repository: ItemRepository,
        request_repository: RequestRepository,
        device_log_service: DeviceLogService,
    ) -> None:
        self.support_request_repository = support_request_repository
        self.item_repository = item_repository
        self.request_repository = request_repository
        self.device_log_service = device_log_service

    async def list_support_requests(
        self, *, status: SupportStatus | None, type_: SupportType | None, item_id: uuid.UUID | None
    ) -> list[SupportListResult]:
        rows = await self.support_request_repository.list_filtered(
            status=status, type_=type_, item_id=item_id
        )
        return [_list_result_from(row) for row in rows]

    async def get_detail(self, support_request_id: uuid.UUID) -> SupportDetailResult:
        row = await self.support_request_repository.get_detail(support_request_id)
        if row is None:
            raise NotFoundException(message="Support request not found.")
        return _detail_result_from(row)

    async def start(self, support_request_id: uuid.UUID, *, actor_id: uuid.UUID) -> SupportRequestResult:
        ticket = await self._get_ticket_or_404(support_request_id)
        if ticket.status != SupportStatus.OPEN:
            raise ConflictException(message="Only open support requests can be started.")

        ticket.status = SupportStatus.IN_PROGRESS
        updated = await self.support_request_repository.update(ticket)

        if ticket.type == SupportType.DAMAGE:
            item = await self._get_item_or_404(ticket.item_id)
            from_status = item.status.value
            item.status = DeviceStatus.UNDER_REPAIR
            await self.item_repository.update(item)
            await self.device_log_service.append(
                item_id=item.id,
                event_type=DeviceLogEvent.STATUS_CHANGED,
                actor_id=actor_id,
                actor_role=ActorRole.IT_ADMIN,
                support_request_id=updated.id,
                from_value=from_status,
                to_value=DeviceStatus.UNDER_REPAIR.value,
            )

        return _result_from(updated)

    async def resolve(
        self,
        support_request_id: uuid.UUID,
        *,
        resolution: SupportResolution,
        it_note: str | None,
        swapped_to_item_id: uuid.UUID | None,
        old_item_next_status: DeviceStatus | None,
        actor_id: uuid.UUID,
    ) -> SupportRequestResult:
        ticket = await self._get_ticket_or_404(support_request_id)
        if ticket.status == SupportStatus.RESOLVED:
            raise ConflictException(message="This support request is already resolved.")

        item = await self._get_item_or_404(ticket.item_id)

        if resolution == SupportResolution.REPAIRED_IN_PLACE:
            await self._repair_in_place(ticket, item, actor_id)
        elif resolution == SupportResolution.SWAPPED:
            assert swapped_to_item_id is not None
            assert old_item_next_status is not None
            await self._swap(ticket, item, swapped_to_item_id, old_item_next_status, actor_id)
        elif resolution == SupportResolution.MARKED_LOST:
            await self._mark_lost(ticket, item, actor_id)

        ticket.status = SupportStatus.RESOLVED
        ticket.resolution = resolution
        ticket.it_note = it_note
        ticket.resolved_by = actor_id
        ticket.resolved_at = datetime.now(UTC)
        if resolution == SupportResolution.SWAPPED:
            ticket.swapped_to_item_id = swapped_to_item_id
        updated = await self.support_request_repository.update(ticket)

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.SUPPORT_RESOLVED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            support_request_id=updated.id,
        )
        return _result_from(updated)

    async def _repair_in_place(self, ticket: SupportRequest, item: Item, actor_id: uuid.UUID) -> None:
        if item.status != DeviceStatus.UNDER_REPAIR:
            raise ConflictException(
                message="Only a device currently under_repair can be resolved as repaired_in_place."
            )
        item.status = DeviceStatus.ASSIGNED
        await self.item_repository.update(item)
        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.STATUS_CHANGED,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            support_request_id=ticket.id,
            from_value=DeviceStatus.UNDER_REPAIR.value,
            to_value=DeviceStatus.ASSIGNED.value,
        )

    async def _swap(
        self,
        ticket: SupportRequest,
        old_item: Item,
        swapped_to_item_id: uuid.UUID,
        old_item_next_status: DeviceStatus,
        actor_id: uuid.UUID,
    ) -> None:
        if swapped_to_item_id == old_item.id:
            raise ValidationException(message="Cannot swap a device for itself.")
        if ticket.request_id is None:
            raise ConflictException(message="This support request has no tied request to repoint.")

        new_item = await self._get_item_or_404(swapped_to_item_id)
        if new_item.category_id != old_item.category_id:
            raise ValidationException(message="The swap target must be in the same category as the device.")
        if new_item.status != DeviceStatus.AVAILABLE:
            raise ConflictException(message="The swap target must be an available device.")

        request = await self.request_repository.get_by_id(ticket.request_id)
        if request is None:
            raise NotFoundException(message="The tied request was not found.")

        request.assigned_item_id = new_item.id
        old_item.status = old_item_next_status
        old_item.current_owner_id = None
        new_item.status = DeviceStatus.ASSIGNED
        new_item.current_owner_id = request.requester_id

        await self.request_repository.update(request)
        await self.item_repository.update(old_item)
        await self.item_repository.update(new_item)

        await self.device_log_service.append(
            item_id=old_item.id,
            event_type=DeviceLogEvent.SWAPPED_OUT,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=request.id,
            support_request_id=ticket.id,
            metadata={"swapped_to_item_id": str(new_item.id)},
            is_milestone=True,
        )
        await self.device_log_service.append(
            item_id=new_item.id,
            event_type=DeviceLogEvent.SWAPPED_IN,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=request.id,
            support_request_id=ticket.id,
            metadata={"swapped_from_item_id": str(old_item.id)},
            is_milestone=True,
        )

    async def _mark_lost(self, ticket: SupportRequest, item: Item, actor_id: uuid.UUID) -> None:
        if ticket.request_id is None:
            raise ConflictException(message="This support request has no tied request to complete.")
        request = await self.request_repository.get_by_id(ticket.request_id)
        if request is None:
            raise NotFoundException(message="The tied request was not found.")

        from_status = item.status.value
        item.status = DeviceStatus.LOST
        await self.item_repository.update(item)

        request.status = RequestStatus.COMPLETED
        request.completed_at = datetime.now(UTC)
        request.completed_by = actor_id
        request.completed_next_status = None
        await self.request_repository.update(request)

        await self.device_log_service.append(
            item_id=item.id,
            event_type=DeviceLogEvent.MARKED_LOST,
            actor_id=actor_id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=request.id,
            support_request_id=ticket.id,
            from_value=from_status,
            to_value=DeviceStatus.LOST.value,
        )

    async def _get_ticket_or_404(self, support_request_id: uuid.UUID) -> SupportRequest:
        ticket = await self.support_request_repository.get_by_id(support_request_id)
        if ticket is None:
            raise NotFoundException(message="Support request not found.")
        return ticket

    async def _get_item_or_404(self, item_id: uuid.UUID) -> Item:
        item = await self.item_repository.get_by_id(item_id)
        if item is None:
            raise NotFoundException(message="Item not found.")
        return item
