"""`extension_request` table repository — IT review queries for M11
(list with item/requester joins, single-row detail with parent request/
item/requester joins).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select

from app.models.enums import ExtensionStatus
from app.models.extension_request import ExtensionRequest
from app.models.item import Item
from app.models.request import Request
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository


@dataclass
class ExtensionListRow:
    extension_request: ExtensionRequest
    item_name: str
    requester_name: str


@dataclass
class ExtensionDetailRow:
    extension_request: ExtensionRequest
    request: Request
    item: Item
    requester: User


class ExtensionRequestRepository(SQLAlchemyRepository[ExtensionRequest]):
    model = ExtensionRequest

    async def count_pending(self) -> int:
        stmt = (
            select(func.count())
            .select_from(ExtensionRequest)
            .where(ExtensionRequest.status == ExtensionStatus.PENDING)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_filtered(self, *, status: ExtensionStatus | None) -> list[ExtensionListRow]:
        stmt = (
            select(ExtensionRequest, Item.name, User.name)
            .join(Request, ExtensionRequest.original_request_id == Request.id)
            .join(Item, Request.assigned_item_id == Item.id)
            .join(User, ExtensionRequest.requester_id == User.id)
        )
        if status is not None:
            stmt = stmt.where(ExtensionRequest.status == status)
        stmt = stmt.order_by(ExtensionRequest.created_at.asc())

        result = await self.session.execute(stmt)
        return [
            ExtensionListRow(
                extension_request=extension_request, item_name=item_name, requester_name=requester_name
            )
            for extension_request, item_name, requester_name in result.all()
        ]

    async def get_detail(self, extension_request_id: uuid.UUID) -> ExtensionDetailRow | None:
        stmt = (
            select(ExtensionRequest, Request, Item, User)
            .join(Request, ExtensionRequest.original_request_id == Request.id)
            .join(Item, Request.assigned_item_id == Item.id)
            .join(User, ExtensionRequest.requester_id == User.id)
            .where(ExtensionRequest.id == extension_request_id)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        extension_request, request, item, requester = row
        return ExtensionDetailRow(
            extension_request=extension_request, request=request, item=item, requester=requester
        )
