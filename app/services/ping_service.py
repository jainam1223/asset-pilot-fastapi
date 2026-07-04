"""Trivial vertical-slice service — proves API -> Service -> Repository ->
Redis wiring end-to-end. Not a real domain feature; delete once Assets or
Tickets ships its first real slice.
"""

from dataclasses import dataclass

from app.repositories.cache_repository import AbstractCacheRepository

_PING_COUNTER_KEY = "ping:counter"


@dataclass
class PingResult:
    message: str
    count: int


class PingService:
    def __init__(self, cache_repository: AbstractCacheRepository) -> None:
        self.cache_repository = cache_repository

    async def ping(self) -> PingResult:
        count = await self.cache_repository.incr(_PING_COUNTER_KEY)
        return PingResult(message="pong", count=count)
