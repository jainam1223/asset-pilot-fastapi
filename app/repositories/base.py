"""Repository interface + generic SQLAlchemy implementation.

Services depend on `AbstractRepository`, never on `SQLAlchemyRepository`
directly. If the persistence technology ever changes, only a new
implementation of this Protocol needs to be written and swapped in at the
DI wiring point (`app/api/v1/dependencies.py`) — Services and the API
layer stay untouched.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.utils.pagination import Page, PaginationParams


class AbstractRepository[ModelType: Base](ABC):
    """Contract every concrete repository must satisfy. Kept minimal and
    generic on purpose — domain-specific query methods belong on the
    concrete repository subclass, not here.
    """

    @abstractmethod
    async def get_by_id(self, id_: Any) -> ModelType | None: ...

    @abstractmethod
    async def list(self, pagination: PaginationParams) -> Page[ModelType]: ...

    @abstractmethod
    async def create(self, entity: ModelType) -> ModelType: ...

    @abstractmethod
    async def update(self, entity: ModelType) -> ModelType: ...

    @abstractmethod
    async def delete(self, id_: Any) -> bool: ...


class SQLAlchemyRepository[ModelType: Base](AbstractRepository[ModelType]):
    """Generic async SQLAlchemy 2.0 implementation. Concrete per-domain
    repositories (e.g. `AssetRepository`) subclass this with their model
    and add domain-specific query methods.
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: UUID) -> ModelType | None:
        return await self.session.get(self.model, id_)

    async def list(self, pagination: PaginationParams) -> Page[ModelType]:
        count_stmt = select(func.count()).select_from(self.model)
        total_items = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(self.model).offset(pagination.offset).limit(pagination.limit)
        if pagination.sort_by and hasattr(self.model, pagination.sort_by):
            column = getattr(self.model, pagination.sort_by)
            stmt = stmt.order_by(column.desc() if pagination.sort_order == "desc" else column.asc())

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return Page(
            items=items,
            total_items=total_items,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def create(self, entity: ModelType) -> ModelType:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id_: UUID) -> bool:
        entity = await self.get_by_id(id_)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True
