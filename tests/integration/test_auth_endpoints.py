"""API -> Service -> Repository -> Postgres, exercised through the real
`/auth/*` HTTP routes. Requires Postgres to be reachable (docker-compose
stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


async def _create_user(*, role: UserRole, is_active: bool = True) -> User:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Test User",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=role,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _delete_user(user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


async def _deactivate_user(user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.is_active = False
        await session.commit()


@pytest.fixture
async def admin_user() -> AsyncGenerator[User, None]:
    user = await _create_user(role=UserRole.IT_ADMIN)
    try:
        yield user
    finally:
        await _delete_user(user.id)


async def test_login_success_returns_tokens(async_client: httpx.AsyncClient, admin_user: User) -> None:
    response = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": _PASSWORD}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]
    assert body["data"]["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(async_client: httpx.AsyncClient, admin_user: User) -> None:
    response = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": "wrong-password"}
    )
    body = response.json()

    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"


async def test_login_unknown_email_returns_401(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login", json={"email": "nobody@techcorp.internal", "password": _PASSWORD}
    )
    assert response.status_code == 401


async def test_login_inactive_user_returns_401(async_client: httpx.AsyncClient) -> None:
    user = await _create_user(role=UserRole.IT_ADMIN, is_active=False)
    try:
        response = await async_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": _PASSWORD}
        )
        body = response.json()

        assert response.status_code == 401
        assert body["error"]["code"] == "UNAUTHORIZED"
    finally:
        await _delete_user(user.id)


async def test_login_invalid_email_format_returns_422(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": _PASSWORD}
    )
    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_refresh_issues_new_tokens(async_client: httpx.AsyncClient, admin_user: User) -> None:
    login = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": _PASSWORD}
    )
    refresh_token = login.json()["data"]["refresh_token"]

    response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]


async def test_refresh_rejects_access_token(async_client: httpx.AsyncClient, admin_user: User) -> None:
    login = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": _PASSWORD}
    )
    access_token = login.json()["data"]["access_token"]

    response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


async def test_refresh_rejects_garbage_token(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "this-is-not-a-jwt-at-all"}
    )
    body = response.json()

    assert response.status_code == 401
    assert body["error"]["code"] == "UNAUTHORIZED"


async def test_refresh_with_deactivated_user_returns_401(
    async_client: httpx.AsyncClient, admin_user: User
) -> None:
    login = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": _PASSWORD}
    )
    refresh_token = login.json()["data"]["refresh_token"]

    await _deactivate_user(admin_user.id)

    response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    body = response.json()

    assert response.status_code == 401
    assert body["error"]["code"] == "UNAUTHORIZED"


async def test_me_returns_current_admin_profile(async_client: httpx.AsyncClient, admin_user: User) -> None:
    login = await async_client.post(
        "/api/v1/auth/login", json={"email": admin_user.email, "password": _PASSWORD}
    )
    access_token = login.json()["data"]["access_token"]

    response = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["id"] == str(admin_user.id)
    assert body["data"]["email"] == admin_user.email
    assert body["data"]["role"] == "it_admin"


async def test_me_without_token_returns_401(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401
