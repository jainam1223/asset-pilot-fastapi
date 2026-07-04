"""`handover_request` table repository.

M5's device-detail composite view uses `get_accepted_for_item`; M12's
read-only IT audit list uses `list_filtered`.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.models.enums import HandoverStatus
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository


@dataclass
class HandoverListRow:
    handover_request: HandoverRequest
    item_name: str
    owner_name: str
    borrower_name: str


class HandoverRequestRepository(SQLAlchemyRepository[HandoverRequest]):
    model = HandoverRequest

    async def get_accepted_for_item(self, item_id: uuid.UUID) -> HandoverRequest | None:
        stmt = select(HandoverRequest).where(
            HandoverRequest.item_id == item_id, HandoverRequest.status == HandoverStatus.ACCEPTED
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active(self) -> int:
        stmt = (
            select(func.count())
            .select_from(HandoverRequest)
            .where(HandoverRequest.status == HandoverStatus.ACCEPTED)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_filtered(
        self, *, status: HandoverStatus | None, item_id: uuid.UUID | None
    ) -> list[HandoverListRow]:
        owner = aliased(User)
        borrower = aliased(User)
        stmt = (
            select(HandoverRequest, Item.name, owner.name, borrower.name)
            .join(Item, HandoverRequest.item_id == Item.id)
            .join(owner, HandoverRequest.owner_id == owner.id)
            .join(borrower, HandoverRequest.borrower_id == borrower.id)
        )
        if status is not None:
            stmt = stmt.where(HandoverRequest.status == status)
        if item_id is not None:
            stmt = stmt.where(HandoverRequest.item_id == item_id)
        stmt = stmt.order_by(HandoverRequest.requested_at.asc())

        result = await self.session.execute(stmt)
        return [
            HandoverListRow(
                handover_request=handover_request,
                item_name=item_name,
                owner_name=owner_name,
                borrower_name=borrower_name,
            )
            for handover_request, item_name, owner_name, borrower_name in result.all()
        ]
