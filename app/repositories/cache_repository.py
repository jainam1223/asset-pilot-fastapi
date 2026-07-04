"""Thin wrapper around the Redis client.

Services never call `redis.asyncio` directly — they depend on
`AbstractCacheRepository`. If Redis is ever swapped for a different cache
backend, only `RedisCacheRepository` (and the provider in
`app/api/v1/dependencies.py`) need to change.
"""

from abc import ABC, abstractmethod
from typing import cast

import redis.asyncio as redis


class AbstractCacheRepository(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abstractmethod
    async def set(self, key: str, value: str, *, expire_seconds: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int: ...

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...


class RedisCacheRepository(AbstractCacheRepository):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def get(self, key: str) -> str | None:
        # The connection pool is configured with decode_responses=True, so
        # this is always a str (or None) at runtime despite the client's
        # broader bytes|str stub signature.
        return cast(str | None, await self.client.get(key))

    async def set(self, key: str, value: str, *, expire_seconds: int | None = None) -> None:
        await self.client.set(key, value, ex=expire_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    async def incr(self, key: str, amount: int = 1) -> int:
        value: int = await self.client.incrby(key, amount)
        return value

    async def expire(self, key: str, seconds: int) -> None:
        await self.client.expire(key, seconds)

    async def ping(self) -> bool:
        return bool(await self.client.ping())
