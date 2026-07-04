"""`UserService` logic exercised against in-memory fake repositories (no
DB, no HTTP) — mirrors `tests/unit/test_inventory_service.py`'s pattern.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserListRow, UserRepository
from app.services.user_service import UserService
from app.utils.pagination import Page, PaginationParams

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


def _make_user(*, role: UserRole = UserRole.EMPLOYEE, is_active: bool = True, **kwargs: object) -> User:
    return User(
        id=kwargs.get("id", uuid.uuid4()),
        name=kwargs.get("name", "User"),
        email=kwargs.get("email", f"{uuid.uuid4().hex}@techcorp.internal"),
        password_hash="hash",
        role=role,
        manager_id=kwargs.get("manager_id"),
        is_active=is_active,
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )


class FakeUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = (), *, has_active: bool = False) -> None:
        self._users: dict[uuid.UUID, User] = {user.id: user for user in users}
        self._has_active = has_active

    async def get_by_id(self, id_: uuid.UUID) -> User | None:
        return self._users.get(id_)

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self._users.values() if user.email == email), None)

    async def create(self, entity: User) -> User:
        if entity.id is None:
            entity.id = uuid.uuid4()
        entity.created_at = entity.created_at or _next_ts()
        entity.updated_at = entity.updated_at or _next_ts()
        self._users[entity.id] = entity
        return entity

    async def update(self, entity: User) -> User:
        entity.updated_at = _next_ts()
        self._users[entity.id] = entity
        return entity

    async def list_users(
        self,
        *,
        role: UserRole | None,
        is_active: bool | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[UserListRow]:
        users = list(self._users.values())
        if role is not None:
            users = [u for u in users if u.role == role]
        if is_active is not None:
            users = [u for u in users if u.is_active == is_active]
        if search:
            users = [
                u for u in users if search.lower() in u.name.lower() or search.lower() in u.email.lower()
            ]
        rows = [UserListRow(user=u, manager_name=None) for u in users]
        return Page(items=rows, total_items=len(rows), page=pagination.page, page_size=pagination.page_size)

    async def has_active_devices_or_requests(self, user_id: uuid.UUID) -> bool:
        return self._has_active


async def test_create_user_hashes_shared_dev_password() -> None:
    service = UserService(FakeUserRepository())

    result = await service.create_user(
        name="Jane Doe", email="jane@techcorp.internal", role=UserRole.EMPLOYEE
    )

    assert result.is_active is True
    stored = await service.user_repository.get_by_id(result.id)
    assert stored is not None
    assert verify_password("Password123!", stored.password_hash)


async def test_create_user_duplicate_email_raises_conflict() -> None:
    existing = _make_user(email="jane@techcorp.internal")
    service = UserService(FakeUserRepository([existing]))

    with pytest.raises(ConflictException):
        await service.create_user(name="Jane Doe", email="jane@techcorp.internal", role=UserRole.EMPLOYEE)


async def test_change_role_updates_user() -> None:
    user = _make_user(role=UserRole.EMPLOYEE)
    service = UserService(FakeUserRepository([user]))

    result = await service.change_role(user.id, role=UserRole.MANAGER)

    assert result.role == UserRole.MANAGER


async def test_change_role_missing_user_raises_not_found() -> None:
    service = UserService(FakeUserRepository())

    with pytest.raises(NotFoundException):
        await service.change_role(uuid.uuid4(), role=UserRole.MANAGER)


async def test_deactivate_blocked_when_user_has_active_devices_or_requests() -> None:
    user = _make_user(is_active=True)
    service = UserService(FakeUserRepository([user], has_active=True))

    with pytest.raises(ConflictException):
        await service.deactivate(user.id)


async def test_deactivate_succeeds_when_no_active_devices_or_requests() -> None:
    user = _make_user(is_active=True)
    service = UserService(FakeUserRepository([user], has_active=False))

    result = await service.deactivate(user.id)

    assert result.is_active is False


async def test_activate_sets_is_active_true() -> None:
    user = _make_user(is_active=False)
    service = UserService(FakeUserRepository([user]))

    result = await service.activate(user.id)

    assert result.is_active is True
