import pytest

from app.repositories.cache_repository import AbstractCacheRepository
from app.services.ping_service import PingService

pytestmark = pytest.mark.unit


class FakeCacheRepository(AbstractCacheRepository):
    """In-memory stand-in for Redis, proving the Service layer only
    depends on the `AbstractCacheRepository` interface — swapping the real
    Redis-backed implementation for this fake requires no Service changes.
    """

    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return str(self._store[key]) if key in self._store else None

    async def set(self, key: str, value: str, *, expire_seconds: int | None = None) -> None:
        self._store[key] = int(value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def incr(self, key: str, amount: int = 1) -> int:
        self._store[key] = self._store.get(key, 0) + amount
        return self._store[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def ping(self) -> bool:
        return True


async def test_ping_service_increments_counter() -> None:
    service = PingService(FakeCacheRepository())

    first = await service.ping()
    second = await service.ping()

    assert first.message == "pong"
    assert first.count == 1
    assert second.count == 2
