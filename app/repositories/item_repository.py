"""`item` table repository — inventory CRUD reads/writes plus the joined
list query backing `GET /admin/items` (item + category name + current
owner name).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.models.enums import DeviceStatus, OwnerType, RequestStatus
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository
from app.utils.pagination import Page, PaginationParams


@dataclass
class ItemListRow:
    item: Item
    category_name: str
    current_owner_name: str | None


@dataclass
class SuggestedDeviceRow:
    item: Item
    category_name: str
    active_bookings_count: int


@dataclass
class ClientAvailableRow:
    item: Item
    category_name: str


class ItemRepository(SQLAlchemyRepository[Item]):
    model = Item

    async def get_by_serial_no(self, serial_no: str) -> Item | None:
        stmt = select(Item).where(Item.serial_no == serial_no)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_status(self) -> dict[DeviceStatus, int]:
        stmt = select(Item.status, func.count()).group_by(Item.status)
        result = await self.session.execute(stmt)
        return {status: count for status, count in result.all()}

    async def list_items(
        self,
        *,
        category_id: uuid.UUID | None,
        status: DeviceStatus | None,
        owner_type: OwnerType | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[ItemListRow]:
        owner = aliased(User)
        base_stmt = (
            select(Item, ItemCategory.name, owner.name)
            .join(ItemCategory, Item.category_id == ItemCategory.id)
            .outerjoin(owner, Item.current_owner_id == owner.id)
        )
        if category_id is not None:
            base_stmt = base_stmt.where(Item.category_id == category_id)
        if status is not None:
            base_stmt = base_stmt.where(Item.status == status)
        if owner_type is not None:
            base_stmt = base_stmt.where(Item.owner_type == owner_type)
        if search:
            pattern = f"%{search}%"
            base_stmt = base_stmt.where(or_(Item.name.ilike(pattern), Item.serial_no.ilike(pattern)))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one()

        stmt = base_stmt.order_by(Item.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        rows = [
            ItemListRow(item=item, category_name=category_name, current_owner_name=owner_name)
            for item, category_name, owner_name in result.all()
        ]
        return Page(items=rows, total_items=total_items, page=pagination.page, page_size=pagination.page_size)

    async def list_suggested_devices(
        self, *, category_id: uuid.UUID, requested_from: datetime, requested_to: datetime
    ) -> list[SuggestedDeviceRow]:
        active_bookings_count = (
            select(func.count(Request.id))
            .where(Request.assigned_item_id == Item.id, Request.status == RequestStatus.ASSIGNED)
            .correlate(Item)
            .scalar_subquery()
        )
        overlap_exists = (
            select(Request.id)
            .where(
                Request.assigned_item_id == Item.id,
                Request.status == RequestStatus.ASSIGNED,
                Request.assigned_from < requested_to,
                Request.assigned_to > requested_from,
            )
            .correlate(Item)
            .exists()
        )
        stmt = (
            select(Item, ItemCategory.name, active_bookings_count)
            .join(ItemCategory, Item.category_id == ItemCategory.id)
            .where(
                Item.category_id == category_id,
                Item.status == DeviceStatus.AVAILABLE,
                ~overlap_exists,
            )
            .order_by(active_bookings_count.asc(), Item.updated_at.asc())
        )
        result = await self.session.execute(stmt)
        return [
            SuggestedDeviceRow(item=item, category_name=category_name, active_bookings_count=count)
            for item, category_name, count in result.all()
        ]

    async def list_client_available(
        self, *, category_id: uuid.UUID | None, search: str | None
    ) -> list[ClientAvailableRow]:
        stmt = (
            select(Item, ItemCategory.name)
            .join(ItemCategory, Item.category_id == ItemCategory.id)
            .where(Item.owner_type == OwnerType.CLIENT, Item.status == DeviceStatus.AVAILABLE)
        )
        if category_id is not None:
            stmt = stmt.where(Item.category_id == category_id)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(or_(Item.name.ilike(pattern), Item.serial_no.ilike(pattern)))
        stmt = stmt.order_by(Item.name)
        result = await self.session.execute(stmt)
        return [ClientAvailableRow(item=item, category_name=name) for item, name in result.all()]
