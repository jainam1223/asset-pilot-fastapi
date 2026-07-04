"""Request ID generation/propagation and structlog context binding.

Used by the request-context middleware in `app/main.py` and by anything
that needs to read the current request's ID (e.g. to embed it in a
response envelope's `meta`).
"""

import uuid
from contextvars import ContextVar

import structlog

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def generate_request_id() -> str:
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def clear_request_context() -> None:
    _request_id_ctx.set(None)
    structlog.contextvars.clear_contextvars()
