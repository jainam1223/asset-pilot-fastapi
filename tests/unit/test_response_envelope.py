"""Asserts the standard envelope shape for a success case, a 404 case, and
a validation-error case. Uses a throwaway FastAPI app wired with the same
`register_exception_handlers` the real app uses, so these tests exercise
the actual handler code without needing Postgres to be reachable.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorCode
from app.main import RequestContextMiddleware, register_exception_handlers
from app.utils.response import success_response

pytestmark = pytest.mark.unit


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/envelope/success")
    async def _success() -> JSONResponse:
        return success_response(data={"foo": "bar"}, message="ok")

    @app.get("/envelope/validate")
    async def _validate(count: int) -> dict[str, int]:
        return {"count": count}

    @app.get("/envelope/crash")
    async def _crash() -> None:
        raise RuntimeError("boom")

    return app


@pytest.fixture
async def envelope_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    app = _build_test_app()
    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware sends the
    # 500 response THEN re-raises the original exception (so it's still
    # visible to server-side logging/ASGI servers). The default transport
    # would propagate that re-raise to the test instead of handing back the
    # response — matching a real client, which only ever sees the response.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_success_envelope_shape(envelope_client: httpx.AsyncClient) -> None:
    response = await envelope_client.get("/envelope/success")

    assert response.status_code == 200
    body = response.json()
    assert body["status_code"] == 200
    assert body["success"] is True
    assert body["data"] == {"foo": "bar"}
    assert body["message"] == "ok"
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]


async def test_not_found_envelope_shape(envelope_client: httpx.AsyncClient) -> None:
    response = await envelope_client.get("/envelope/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["status_code"] == 404
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.RESOURCE_NOT_FOUND
    assert "request_id" in body["meta"]


async def test_validation_error_envelope_shape(envelope_client: httpx.AsyncClient) -> None:
    response = await envelope_client.get("/envelope/validate", params={"count": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["status_code"] == 422
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert body["error"]["details"]
    assert body["error"]["details"][0]["field"]
    assert body["error"]["details"][0]["issue"]


async def test_unhandled_exception_still_carries_request_id(envelope_client: httpx.AsyncClient) -> None:
    """Regression test: RequestContextMiddleware used to clear the request-id
    context in a `finally` around call_next(), which ran *before*
    ServerErrorMiddleware's catch-all handler executed — so every 500 lost
    its request_id in both the response body and the X-Request-ID header.
    """
    response = await envelope_client.get("/envelope/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.INTERNAL_SERVER_ERROR
    assert body["meta"]["request_id"]
    assert response.headers.get("X-Request-ID") == body["meta"]["request_id"]
