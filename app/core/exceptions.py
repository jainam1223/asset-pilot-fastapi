"""Domain exception taxonomy.

Services raise these (never the Repository or API layer) and the global
exception handlers in `app/main.py` translate them into the standard
response envelope via `app/utils/response.py`. This keeps the mapping of
"business failure" -> "HTTP status + machine-readable code" in one place.
"""

from typing import Any


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class AppException(Exception):
    """Base class for all domain exceptions.

    Carries everything the global handler needs to build the error
    envelope, so `status_code` in the HTTP response and `status_code` in
    the JSON body can never drift apart — both are read from here.
    """

    status_code: int = 500
    code: str = ErrorCode.INTERNAL_SERVER_ERROR
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class ValidationException(AppException):
    status_code = 422
    code = ErrorCode.VALIDATION_ERROR
    message = "Validation failed."


class UnauthorizedException(AppException):
    status_code = 401
    code = ErrorCode.UNAUTHORIZED
    message = "Authentication is required or has failed."


class ForbiddenException(AppException):
    status_code = 403
    code = ErrorCode.FORBIDDEN
    message = "You do not have permission to perform this action."


class NotFoundException(AppException):
    status_code = 404
    code = ErrorCode.RESOURCE_NOT_FOUND
    message = "The requested resource was not found."


class ConflictException(AppException):
    status_code = 409
    code = ErrorCode.CONFLICT
    message = "The request conflicts with the current state of the resource."


class RateLimitedException(AppException):
    status_code = 429
    code = ErrorCode.RATE_LIMITED
    message = "Too many requests."


class ServiceUnavailableException(AppException):
    status_code = 503
    code = ErrorCode.SERVICE_UNAVAILABLE
    message = "A required dependency is currently unavailable."
