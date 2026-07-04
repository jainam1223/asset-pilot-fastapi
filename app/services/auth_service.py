"""Login/refresh/me business logic for IT-Admin JWT auth."""

import uuid
from dataclasses import dataclass

from app.core.exceptions import ConflictException, NotFoundException, UnauthorizedException
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository


@dataclass
class TokenResult:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass
class UserProfile:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool


def _claims_for(user: User) -> dict[str, str]:
    return {"role": user.role.value, "email": user.email}


def _profile_from(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
    )


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def authenticate(self, email: str, password: str) -> TokenResult:
        user = await self.user_repository.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedException(message="Invalid email or password.")
        if not user.is_active:
            raise UnauthorizedException(message="This account is inactive.")

        subject = str(user.id)
        extra_claims = _claims_for(user)
        return TokenResult(
            access_token=create_access_token(subject, extra_claims),
            refresh_token=create_refresh_token(subject, extra_claims),
        )

    async def register(self, *, name: str, email: str, role: UserRole, password: str) -> TokenResult:
        if await self.user_repository.get_by_email(email) is not None:
            raise ConflictException(message=f"A user with email '{email}' already exists.")

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        created = await self.user_repository.create(user)

        subject = str(created.id)
        extra_claims = _claims_for(created)
        return TokenResult(
            access_token=create_access_token(subject, extra_claims),
            refresh_token=create_refresh_token(subject, extra_claims),
        )

    async def refresh(self, refresh_token: str) -> TokenResult:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        subject = payload.get("sub")
        user = await self._get_active_user(subject)

        new_subject = str(user.id)
        extra_claims = _claims_for(user)
        return TokenResult(
            access_token=create_access_token(new_subject, extra_claims),
            refresh_token=create_refresh_token(new_subject, extra_claims),
        )

    async def get_me(self, user_id: str) -> UserProfile:
        user = await self._get_active_user(user_id)
        return _profile_from(user)

    async def _get_active_user(self, user_id: str | None) -> User:
        if user_id is None:
            raise UnauthorizedException(message="Token is missing a subject claim.")
        try:
            user = await self.user_repository.get_by_id(uuid.UUID(user_id))
        except ValueError as exc:
            raise UnauthorizedException(message="Token subject is not a valid user id.") from exc
        if user is None:
            raise NotFoundException(message="User not found.")
        if not user.is_active:
            raise UnauthorizedException(message="This account is inactive.")
        return user
