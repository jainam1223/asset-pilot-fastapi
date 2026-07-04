"""Readiness/liveness orchestration. Knows nothing about HTTP — returns
plain dataclasses that the API layer translates into the response
envelope.
"""

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.repositories.health_repository import AbstractHealthRepository


@dataclass
class DependencyCheck:
    status: str  # "ok" | "error"
    latency_ms: float | None
    error: str | None


@dataclass
class ReadinessResult:
    status: str  # "ok" | "degraded"
    database: DependencyCheck
    redis: DependencyCheck

    @property
    def is_healthy(self) -> bool:
        return self.status == "ok"


class HealthService:
    def __init__(self, health_repository: AbstractHealthRepository) -> None:
        self.health_repository = health_repository

    async def _timed_check(self, coro: Coroutine[Any, Any, None]) -> DependencyCheck:
        start = time.perf_counter()
        try:
            await asyncio.wait_for(coro, timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS)
        except TimeoutError:
            return DependencyCheck(status="error", latency_ms=None, error="Timed out.")
        except Exception:
            return DependencyCheck(status="error", latency_ms=None, error="Dependency check failed.")
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return DependencyCheck(status="ok", latency_ms=latency_ms, error=None)

    async def check_readiness(self) -> ReadinessResult:
        database, redis_check = await asyncio.gather(
            self._timed_check(self.health_repository.check_database()),
            self._timed_check(self.health_repository.check_cache()),
        )
        overall = "ok" if database.status == "ok" and redis_check.status == "ok" else "degraded"
        return ReadinessResult(status=overall, database=database, redis=redis_check)
