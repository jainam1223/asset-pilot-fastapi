"""`AuthService` logic exercised against an in-memory fake repository (no
DB, no HTTP) — complements the real-Postgres coverage in
`tests/integration/test_auth_endpoints.py` by isolating branches that are
awkward to hit end-to-end (invalid-UUID token subjects, an account that
goes inactive between token issuance and use, etc).
"""

import uuid
from collections.abc import Iterable

import pytest

from app.core.exceptions import NotFoundException, UnauthorizedException
from app.core.security import TokenType, create_refresh_token, decode_token, hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

pytestmark = pytest.mark.unit

_PASSWORD = "S3cret-Pass!"


class FakeUserRepository(UserRepository):
    """In-memory stand-in for `UserRepository`, proving `AuthService` only
    depends on its narrow (`get_by_email`, `get_by_id`) interface — no real
    session is ever touched.
    """

    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users: dict[uuid.UUID, User] = {user.id: user for user in users}

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self._users.values() if user.email == email), None)

    async def get_by_id(self, id_: uuid.UUID) -> User | None:
        return self._users.get(id_)


def _make_user(*, is_active: bool = True, role: UserRole = UserRole.IT_ADMIN) -> User:
    return User(
        id=uuid.uuid4(),
        name="Test User",
        email="admin@techcorp.internal",
        password_hash=hash_password(_PASSWORD),
        role=role,
        manager_id=None,
        is_active=is_active,
    )


async def test_authenticate_unknown_email_raises_unauthorized() -> None:
    service = AuthService(FakeUserRepository())
    with pytest.raises(UnauthorizedException):
        await service.authenticate("nobody@techcorp.internal", _PASSWORD)


async def test_authenticate_wrong_password_raises_unauthorized() -> None:
    user = _make_user()
    service = AuthService(FakeUserRepository([user]))
    with pytest.raises(UnauthorizedException):
        await service.authenticate(user.email, "wrong-password")


async def test_authenticate_inactive_user_raises_unauthorized() -> None:
    user = _make_user(is_active=False)
    service = AuthService(FakeUserRepository([user]))
    with pytest.raises(UnauthorizedException):
        await service.authenticate(user.email, _PASSWORD)


async def test_authenticate_success_embeds_role_and_email_claims() -> None:
    user = _make_user(role=UserRole.IT_ADMIN)
    service = AuthService(FakeUserRepository([user]))

    result = await service.authenticate(user.email, _PASSWORD)

    payload = decode_token(result.access_token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == str(user.id)
    assert payload["role"] == UserRole.IT_ADMIN.value
    assert payload["email"] == user.email


async def test_refresh_invalid_uuid_subject_raises_unauthorized() -> None:
    service = AuthService(FakeUserRepository())
    token = create_refresh_token("not-a-uuid")
    with pytest.raises(UnauthorizedException):
        await service.refresh(token)


async def test_refresh_unknown_user_raises_not_found() -> None:
    service = AuthService(FakeUserRepository())
    token = create_refresh_token(str(uuid.uuid4()))
    with pytest.raises(NotFoundException):
        await service.refresh(token)


async def test_refresh_inactive_user_raises_unauthorized() -> None:
    user = _make_user(is_active=False)
    service = AuthService(FakeUserRepository([user]))
    token = create_refresh_token(str(user.id))
    with pytest.raises(UnauthorizedException):
        await service.refresh(token)


async def test_refresh_success_reissues_tokens_for_active_user() -> None:
    user = _make_user()
    service = AuthService(FakeUserRepository([user]))
    token = create_refresh_token(str(user.id))

    result = await service.refresh(token)

    payload = decode_token(result.access_token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == str(user.id)


async def test_get_me_invalid_uuid_subject_raises_unauthorized() -> None:
    service = AuthService(FakeUserRepository())
    with pytest.raises(UnauthorizedException):
        await service.get_me("not-a-uuid")


async def test_get_me_unknown_user_raises_not_found() -> None:
    service = AuthService(FakeUserRepository())
    with pytest.raises(NotFoundException):
        await service.get_me(str(uuid.uuid4()))


async def test_get_me_inactive_user_raises_unauthorized() -> None:
    user = _make_user(is_active=False)
    service = AuthService(FakeUserRepository([user]))
    with pytest.raises(UnauthorizedException):
        await service.get_me(str(user.id))


async def test_get_me_returns_profile_for_active_user() -> None:
    user = _make_user(role=UserRole.IT_ADMIN)
    service = AuthService(FakeUserRepository([user]))

    profile = await service.get_me(str(user.id))

    assert profile.id == user.id
    assert profile.email == user.email
    assert profile.role == UserRole.IT_ADMIN
    assert profile.is_active is True
