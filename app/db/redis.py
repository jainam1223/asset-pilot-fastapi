"""Redis connection pool.

This is the ONE place that knows how to connect to Redis. Local Docker
Redis -> Azure Cache for Redis is a pure env-var change (`REDIS_URL` or
the `REDIS_*` fields, plus `REDIS_SSL=true` for `rediss://`) — nothing
here needs to change. Nothing outside `app/repositories` should import
`redis.asyncio` directly; go through `CacheRepository` instead.
"""

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from app.core.config import settings

redis_pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
    settings.redis_uri,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
    decode_responses=True,
)


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=redis_pool)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency yielding a pooled Redis client."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()
