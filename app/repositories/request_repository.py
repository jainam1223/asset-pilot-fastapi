"""`request` table repository.

`get_active_for_item` backs M5's device-detail composite view. The rest
(`list_requests`, `list_it_approvals`, `get_detail`) are M7's
listing/detail/approval-queue queries.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.models.enums import DeviceStatus, RequestPriority, RequestStatus
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository
from app.utils.pagination import Page, PaginationParams


@dataclass
class RequestListRow:
    request: Request
    category_name: str
    requester_name: str


@dataclass
class BookingRow:
    request: Request
    requester_name: str


@dataclass
class ShippingQueueRow:
    request: Request
    item_name: str
    requester_name: str


@dataclass
class RequestDetailRow:
    request: Request
    category_name: str
    requester_name: str
    manager_name: str | None
    it_decided_by_name: str | None
    cancelled_by_name: str | None
    completed_by_name: str | None
    item: Item | None


class RequestRepository(SQLAlchemyRepository[Request]):
    model = Request

    async def get_active_for_item(self, item_id: uuid.UUID) -> Request | None:
        stmt = (
            select(Request)
            .where(Request.assigned_item_id == item_id, Request.status == RequestStatus.ASSIGNED)
            .order_by(Request.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_pending(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Request)
            .where(
                Request.status.in_([RequestStatus.PENDING_MGR_APPROVAL, RequestStatus.PENDING_IT_APPROVAL])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_recent(self, *, limit: int) -> list[RequestListRow]:
        requester = aliased(User)
        stmt = (
            select(Request, ItemCategory.name, requester.name)
            .join(ItemCategory, Request.category_id == ItemCategory.id)
            .join(requester, Request.requester_id == requester.id)
            .order_by(Request.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            RequestListRow(request=request, category_name=category_name, requester_name=requester_name)
            for request, category_name, requester_name in result.all()
        ]

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
    ) -> Page[RequestListRow]:
        requester = aliased(User)
        base_stmt = (
            select(Request, ItemCategory.name, requester.name)
            .join(ItemCategory, Request.category_id == ItemCategory.id)
            .join(requester, Request.requester_id == requester.id)
        )
        if status is not None:
            base_stmt = base_stmt.where(Request.status == status)
        if category_id is not None:
            base_stmt = base_stmt.where(Request.category_id == category_id)
        if priority is not None:
            base_stmt = base_stmt.where(Request.priority == priority)
        if requested_from is not None:
            base_stmt = base_stmt.where(Request.requested_from >= requested_from)
        if requested_to is not None:
            base_stmt = base_stmt.where(Request.requested_to <= requested_to)
        if search:
            pattern = f"%{search}%"
            base_stmt = base_stmt.where(or_(requester.name.ilike(pattern), requester.email.ilike(pattern)))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one()

        stmt = base_stmt.order_by(Request.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        rows = [
            RequestListRow(request=request, category_name=category_name, requester_name=requester_name)
            for request, category_name, requester_name in result.all()
        ]
        return Page(items=rows, total_items=total_items, page=pagination.page, page_size=pagination.page_size)

    async def list_it_approvals(self, *, pagination: PaginationParams) -> Page[RequestListRow]:
        requester = aliased(User)
        base_stmt = (
            select(Request, ItemCategory.name, requester.name)
            .join(ItemCategory, Request.category_id == ItemCategory.id)
            .join(requester, Request.requester_id == requester.id)
            .where(Request.status == RequestStatus.PENDING_IT_APPROVAL)
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base_stmt.order_by(Request.priority.desc(), Request.created_at.asc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        result = await self.session.execute(stmt)
        rows = [
            RequestListRow(request=request, category_name=category_name, requester_name=requester_name)
            for request, category_name, requester_name in result.all()
        ]
        return Page(items=rows, total_items=total_items, page=pagination.page, page_size=pagination.page_size)

    async def list_bookings_for_item(self, item_id: uuid.UUID) -> list[BookingRow]:
        stmt = (
            select(Request, User.name)
            .join(User, Request.requester_id == User.id)
            .where(Request.assigned_item_id == item_id, Request.status == RequestStatus.ASSIGNED)
            .order_by(Request.assigned_from)
        )
        result = await self.session.execute(stmt)
        return [BookingRow(request=request, requester_name=name) for request, name in result.all()]

    async def has_overlapping_assigned_booking(
        self,
        item_id: uuid.UUID,
        assigned_from: datetime,
        assigned_to: datetime,
        *,
        exclude_request_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(Request.id).where(
            Request.assigned_item_id == item_id,
            Request.status == RequestStatus.ASSIGNED,
            Request.assigned_from < assigned_to,
            Request.assigned_to > assigned_from,
        )
        if exclude_request_id is not None:
            stmt = stmt.where(Request.id != exclude_request_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def list_outbound_shipping_queue(self) -> list[ShippingQueueRow]:
        stmt = (
            select(Request, Item.name, User.name)
            .join(Item, Request.assigned_item_id == Item.id)
            .join(User, Request.requester_id == User.id)
            .where(
                Request.is_wfh.is_(True),
                Request.status == RequestStatus.ASSIGNED,
                Request.ship_initiated_at.is_(None),
            )
            .order_by(Request.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [
            ShippingQueueRow(request=request, item_name=item_name, requester_name=requester_name)
            for request, item_name, requester_name in result.all()
        ]

    async def list_return_shipping_queue(self) -> list[ShippingQueueRow]:
        stmt = (
            select(Request, Item.name, User.name)
            .join(Item, Request.assigned_item_id == Item.id)
            .join(User, Request.requester_id == User.id)
            .where(Item.status == DeviceStatus.RETURN_SHIPPING_PENDING)
            .order_by(Request.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [
            ShippingQueueRow(request=request, item_name=item_name, requester_name=requester_name)
            for request, item_name, requester_name in result.all()
        ]

    async def get_detail(self, request_id: uuid.UUID) -> RequestDetailRow | None:
        requester = aliased(User)
        manager = aliased(User)
        it_decider = aliased(User)
        canceller = aliased(User)
        completer = aliased(User)
        stmt = (
            select(
                Request,
                ItemCategory.name,
                requester.name,
                manager.name,
                it_decider.name,
                canceller.name,
                completer.name,
                Item,
            )
            .join(ItemCategory, Request.category_id == ItemCategory.id)
            .join(requester, Request.requester_id == requester.id)
            .outerjoin(manager, Request.manager_id == manager.id)
            .outerjoin(it_decider, Request.it_decided_by == it_decider.id)
            .outerjoin(canceller, Request.cancelled_by == canceller.id)
            .outerjoin(completer, Request.completed_by == completer.id)
            .outerjoin(Item, Request.assigned_item_id == Item.id)
            .where(Request.id == request_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        (
            request,
            category_name,
            requester_name,
            manager_name,
            it_decided_by_name,
            cancelled_by_name,
            completed_by_name,
            item,
        ) = row
        return RequestDetailRow(
            request=request,
            category_name=category_name,
            requester_name=requester_name,
            manager_name=manager_name,
            it_decided_by_name=it_decided_by_name,
            cancelled_by_name=cancelled_by_name,
            completed_by_name=completed_by_name,
            item=item,
        )
