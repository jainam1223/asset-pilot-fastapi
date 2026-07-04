"""Application factory.

Kept intentionally plain: middleware + global exception handlers + router
registration. Nothing here assumes every route is a simple JSON
request/response — adding a WebSocket route or a `StreamingResponse`
endpoint later (for the future AI chatbot module) is a normal addition.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.health import router as health_router
from app.api.v1.routers import api_v1_router
from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.core.logging import configure_logging, get_logger
from app.db.session import engine
from app.utils.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    clear_request_context,
    generate_request_id,
)
from app.utils.response import error_response

configure_logging()
logger = get_logger(__name__)

_HTTP_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.RESOURCE_NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generates/propagates a request ID and binds it to structlog's
    contextvars so every log line emitted while handling this request
    carries it automatically. Also logs a start/finish line per request.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # Deliberately NOT a try/finally around call_next(): ServerErrorMiddleware
        # (which invokes the unhandled-exception handler) sits OUTSIDE this
        # middleware, so clearing the context here on the exception path would
        # wipe the request_id before that handler ever runs. Leaving it bound on
        # the exception path is safe — the next request overwrites it via
        # bind_request_id() at the top of this method regardless.
        request_id = request.headers.get(REQUEST_ID_HEADER) or generate_request_id()
        bind_request_id(request_id)
        logger.info("request_started", method=request.method, path=request.url.path)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info("request_finished", status_code=response.status_code)
        clear_request_context()
        return response


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("app_startup", environment=settings.ENVIRONMENT.value)
    yield
    logger.info("app_shutdown")
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
    app.add_middleware(GZipMiddleware, minimum_size=settings.GZIP_MIN_SIZE)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> Any:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> Any:
        details = [
            {"field": ".".join(str(loc) for loc in error["loc"]), "issue": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> Any:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_SERVER_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "An error occurred."
        return error_response(status_code=exc.status_code, code=code, message=message)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> Any:
        logger.exception("unhandled_exception", error=str(exc))
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred. Please try again later.",
        )


app = create_app()
