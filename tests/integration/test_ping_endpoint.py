"""API -> Service -> Repository -> Redis, exercised through the real HTTP
route. Requires Redis to be reachable (docker-compose stack up).
"""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_ping_increments_and_uses_standard_envelope(async_client: httpx.AsyncClient) -> None:
    first = await async_client.get("/api/v1/ping")
    second = await async_client.get("/api/v1/ping")

    assert first.status_code == 200
    body = second.json()
    assert body["success"] is True
    assert body["data"]["message"] == "pong"
    assert body["data"]["count"] == first.json()["data"]["count"] + 1
