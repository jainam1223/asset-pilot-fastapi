"""IT-Admin user administration (API §13): list, create, change role,
activate/deactivate — with the F4 hard-block on deactivating a user who
still holds a device or has a non-terminal request.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserListRow, UserRepository
from app.utils.pagination import Page, PaginationParams

# Shared dev password for users created via this endpoint, matching
# `scripts/seed.py`'s `DEV_PASSWORD` so newly created users can log in
# through the same M2 auth flow as seeded ones.
_DEFAULT_PASSWORD = "Password123!"


@dataclass
class UserResult:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class UserListEntry(UserResult):
    manager_name: str | None


def _user_result_from(user: User) -> UserResult:
    return UserResult(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _user_list_entry_from(row: UserListRow) -> UserListEntry:
    user = row.user
    return UserListEntry(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        manager_name=row.manager_name,
    )


class UserService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def list_users(
        self,
        *,
        role: UserRole | None,
        is_active: bool | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[UserListEntry]:
        page = await self.user_repository.list_users(
            role=role, is_active=is_active, search=search, pagination=pagination
        )
        return Page(
            items=[_user_list_entry_from(row) for row in page.items],
            total_items=page.total_items,
            page=page.page,
            page_size=page.page_size,
        )

    async def create_user(self, *, name: str, email: str, role: UserRole) -> UserResult:
        if await self.user_repository.get_by_email(email) is not None:
            raise ConflictException(message=f"A user with email '{email}' already exists.")

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(_DEFAULT_PASSWORD),
            role=role,
            is_active=True,
        )
        created = await self.user_repository.create(user)
        return _user_result_from(created)

    async def change_role(self, user_id: uuid.UUID, *, role: UserRole) -> UserResult:
        user = await self._get_user_or_404(user_id)
        user.role = role
        updated = await self.user_repository.update(user)
        return _user_result_from(updated)

    async def deactivate(self, user_id: uuid.UUID) -> UserResult:
        user = await self._get_user_or_404(user_id)
        if await self.user_repository.has_active_devices_or_requests(user.id):
            raise ConflictException(
                message="Cannot deactivate a user who currently holds a device or has an open request."
            )
        user.is_active = False
        updated = await self.user_repository.update(user)
        return _user_result_from(updated)

    async def activate(self, user_id: uuid.UUID) -> UserResult:
        user = await self._get_user_or_404(user_id)
        user.is_active = True
        updated = await self.user_repository.update(user)
        return _user_result_from(updated)

    async def _get_user_or_404(self, user_id: uuid.UUID) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundException(message="User not found.")
        return user
