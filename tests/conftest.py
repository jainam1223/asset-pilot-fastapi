from collections.abc import AsyncGenerator

import httpx
import pytest


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-process client against the real app. Connections to Postgres/
    Redis are lazy, so this is safe to use even for routes with no live
    dependencies (e.g. 404s); routes that DO touch Postgres/Redis
    (`/health/ready`, `/api/v1/ping`) require the docker-compose stack to
    be up, which is why those live in `tests/integration/`.
    """
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
