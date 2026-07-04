"""`support_request` table repository.

`list_open_for_item` backs M5's device-detail composite view. M10 (Support
Requests) adds the write-side queue queries (`list_filtered`, `get_detail`)
for its own endpoints.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select

from app.models.enums import SupportStatus, SupportType
from app.models.item import Item
from app.models.support_request import SupportRequest
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository

_OPEN_STATUSES = (SupportStatus.OPEN, SupportStatus.IN_PROGRESS)


@dataclass
class SupportListRow:
    support_request: SupportRequest
    item_name: str
    requester_name: str


@dataclass
class SupportDetailRow:
    support_request: SupportRequest
    item: Item
    requester: User


class SupportRequestRepository(SQLAlchemyRepository[SupportRequest]):
    model = SupportRequest

    async def list_open_for_item(self, item_id: uuid.UUID) -> list[SupportRequest]:
        stmt = (
            select(SupportRequest)
            .where(
                SupportRequest.item_id == item_id,
                SupportRequest.status.in_(_OPEN_STATUSES),
            )
            .order_by(SupportRequest.filed_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self) -> int:
        stmt = (
            select(func.count()).select_from(SupportRequest).where(SupportRequest.status.in_(_OPEN_STATUSES))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_open(self, *, limit: int) -> list[SupportListRow]:
        stmt = (
            select(SupportRequest, Item.name, User.name)
            .join(Item, SupportRequest.item_id == Item.id)
            .join(User, SupportRequest.requester_id == User.id)
            .where(SupportRequest.status.in_(_OPEN_STATUSES))
            .order_by(SupportRequest.filed_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            SupportListRow(
                support_request=support_request, item_name=item_name, requester_name=requester_name
            )
            for support_request, item_name, requester_name in result.all()
        ]

    async def list_filtered(
        self,
        *,
        status: SupportStatus | None,
        type_: SupportType | None,
        item_id: uuid.UUID | None,
    ) -> list[SupportListRow]:
        stmt = (
            select(SupportRequest, Item.name, User.name)
            .join(Item, SupportRequest.item_id == Item.id)
            .join(User, SupportRequest.requester_id == User.id)
        )
        if status is not None:
            stmt = stmt.where(SupportRequest.status == status)
        if type_ is not None:
            stmt = stmt.where(SupportRequest.type == type_)
        if item_id is not None:
            stmt = stmt.where(SupportRequest.item_id == item_id)
        stmt = stmt.order_by(SupportRequest.filed_at.asc())

        result = await self.session.execute(stmt)
        return [
            SupportListRow(
                support_request=support_request, item_name=item_name, requester_name=requester_name
            )
            for support_request, item_name, requester_name in result.all()
        ]

    async def get_detail(self, support_request_id: uuid.UUID) -> SupportDetailRow | None:
        stmt = (
            select(SupportRequest, Item, User)
            .join(Item, SupportRequest.item_id == Item.id)
            .join(User, SupportRequest.requester_id == User.id)
            .where(SupportRequest.id == support_request_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        support_request, item, requester = row
        return SupportDetailRow(support_request=support_request, item=item, requester=requester)
