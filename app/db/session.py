"""Async SQLAlchemy engine/session factory.

This is the ONE place that knows how to connect to Postgres. Switching
from your local Postgres install to a distributed/managed Postgres (e.g.
Azure Database for PostgreSQL Flexible Server) is a pure `DATABASE_URL`
change — including SSL, which is encoded directly in the URL's query
string (e.g. `?ssl=require`) and passed through to asyncpg by SQLAlchemy.
Nothing here needs to change, and nothing outside this module should
construct an engine/session itself.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.sqlalchemy_database_uri,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session. Commits on
    clean exit, rolls back on exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
