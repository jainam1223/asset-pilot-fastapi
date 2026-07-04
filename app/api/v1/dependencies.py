"""Single place where dependency injection is wired together.

Every provider a router needs — DB session, Redis client, repositories,
services — is resolved here and exposed as an `Annotated` alias. Routers
only ever import from this module (never construct a session/repository/
service themselves), so swapping an implementation is a one-file change.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.redis import get_redis
from app.db.session import get_db_session
from app.repositories.cache_repository import AbstractCacheRepository, RedisCacheRepository
from app.repositories.health_repository import AbstractHealthRepository, HealthRepository
from app.services.health_service import HealthService
from app.services.ping_service import PingService

# --- Infra-level providers ---

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


# --- Repository providers ---


def get_cache_repository(redis_client: RedisClient) -> AbstractCacheRepository:
    return RedisCacheRepository(redis_client)


CacheRepositoryDep = Annotated[AbstractCacheRepository, Depends(get_cache_repository)]


def get_health_repository(session: DbSession, cache: CacheRepositoryDep) -> AbstractHealthRepository:
    return HealthRepository(session, cache)


HealthRepositoryDep = Annotated[AbstractHealthRepository, Depends(get_health_repository)]


# --- Service providers ---


def get_health_service(health_repository: HealthRepositoryDep) -> HealthService:
    return HealthService(health_repository)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def get_ping_service(cache_repository: CacheRepositoryDep) -> PingService:
    return PingService(cache_repository)


PingServiceDep = Annotated[PingService, Depends(get_ping_service)]
