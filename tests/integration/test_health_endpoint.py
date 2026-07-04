"""Requires the docker-compose stack (Postgres + Redis) to be reachable —
run via `make test-integration` / `make test`, which execs into the
running `api` container so `postgres`/`redis` hostnames resolve.
"""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_liveness_always_ok(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_database_and_redis(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["database"]["latency_ms"] is not None
    assert body["checks"]["redis"]["latency_ms"] is not None
