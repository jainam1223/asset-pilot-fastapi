"""Exercises `SQLAlchemyRepository`'s generic CRUD against a real Postgres
connection, using a throwaway model defined only in this test module (no
domain models exist yet in this commit). Requires Postgres to be
reachable (docker-compose stack up).
"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import AsyncSessionLocal, engine
from app.repositories.base import SQLAlchemyRepository
from app.utils.pagination import PaginationParams

pytestmark = pytest.mark.integration


class _Widget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "_test_widgets"

    name: Mapped[str] = mapped_column(nullable=False)


class WidgetRepository(SQLAlchemyRepository[_Widget]):
    model = _Widget


_widget_table = _Widget.metadata.tables[_Widget.__tablename__]


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with engine.begin() as conn:
        await conn.run_sync(_Widget.metadata.create_all, tables=[_widget_table])
    try:
        async with AsyncSessionLocal() as db_session:
            yield db_session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(_Widget.metadata.drop_all, tables=[_widget_table])


async def test_repository_crud_round_trip(session: AsyncSession) -> None:
    repo = WidgetRepository(session)

    created = await repo.create(_Widget(name="laptop"))
    await session.commit()
    assert created.id is not None

    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.name == "laptop"

    fetched.name = "renamed-laptop"
    updated = await repo.update(fetched)
    await session.commit()
    assert updated.name == "renamed-laptop"

    page = await repo.list(PaginationParams(page=1, page_size=10))
    assert page.total_items == 1
    assert page.items[0].name == "renamed-laptop"

    deleted = await repo.delete(created.id)
    await session.commit()
    assert deleted is True
    assert await repo.get_by_id(created.id) is None
