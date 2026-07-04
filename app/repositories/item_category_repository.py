"""`item_category` table repository."""

from sqlalchemy import select

from app.models.item_category import ItemCategory
from app.repositories.base import SQLAlchemyRepository


class ItemCategoryRepository(SQLAlchemyRepository[ItemCategory]):
    model = ItemCategory

    async def list_active(self) -> list[ItemCategory]:
        stmt = select(ItemCategory).where(ItemCategory.is_active.is_(True)).order_by(ItemCategory.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
