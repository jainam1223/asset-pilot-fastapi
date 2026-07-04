"""Lightweight connectivity checks used by the readiness probe.

Kept in the repository layer since it's the only layer allowed to touch
the DB session / Redis client directly.
"""

from abc import ABC, abstractmethod

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cache_repository import AbstractCacheRepository


class AbstractHealthRepository(ABC):
    @abstractmethod
    async def check_database(self) -> None: ...

    @abstractmethod
    async def check_cache(self) -> None: ...


class HealthRepository(AbstractHealthRepository):
    def __init__(self, session: AsyncSession, cache: AbstractCacheRepository) -> None:
        self.session = session
        self.cache = cache

    async def check_database(self) -> None:
        await self.session.execute(text("SELECT 1"))

    async def check_cache(self) -> None:
        await self.cache.ping()
