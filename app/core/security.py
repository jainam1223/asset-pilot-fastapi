"""JWT + password hashing plumbing.

No login/register endpoints and no User model live here on purpose — this
commit only ships the reusable primitives (token issue/verify, password
hashing, and a `get_current_user` dependency) so a future auth feature
commit can wire real endpoints on top without restructuring anything.

Swapping the JWT library later (e.g. PyJWT -> python-jose) means editing
only this file: nothing outside it imports `jwt` or `bcrypt` directly.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import UnauthorizedException

_bearer_scheme = HTTPBearer(auto_error=False)


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(minutes=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and verify a JWT. Raises UnauthorizedException (never a raw
    jwt/PyJWT exception) on any failure so callers funnel into the
    standard error envelope automatically.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedException(message="Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedException(message="Token is invalid.") from exc

    if expected_type is not None and payload.get("type") != expected_type.value:
        raise UnauthorizedException(message="Token type is not valid for this operation.")

    return payload


class TokenPayload:
    """Minimal typed view over a verified token's claims, handed to
    downstream dependencies instead of a raw dict.
    """

    def __init__(self, subject: str, claims: dict[str, Any]) -> None:
        self.subject = subject
        self.claims = claims


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TokenPayload:
    """Reusable dependency for protected routes. Extracts and verifies the
    `Authorization: Bearer <token>` header. No user-domain lookup happens
    here yet (there's no User model in this commit) — it just proves the
    token is valid and exposes its claims.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException(message="Missing bearer token.")

    payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedException(message="Token is missing a subject claim.")

    return TokenPayload(subject=subject, claims=payload)
