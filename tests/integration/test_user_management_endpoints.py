"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/users` HTTP routes. Requires Postgres to be reachable (docker-
compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import DeviceStatus, OwnerType, UserRole
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"
_SHARED_DEV_PASSWORD = "Password123!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name="User Admin",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.IT_ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    yield create_access_token(str(user.id), {"role": UserRole.IT_ADMIN.value, "email": user.email})


@pytest.fixture
async def active_category() -> AsyncGenerator[ItemCategory, None]:
    async with AsyncSessionLocal() as session:
        category = ItemCategory(name=f"Category-{uuid.uuid4().hex[:8]}", is_active=True)
        session.add(category)
        await session.commit()
        await session.refresh(category)
    yield category


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_user_returns_201_and_can_log_in(
    async_client: httpx.AsyncClient, admin_token: str
) -> None:
    email = f"{uuid.uuid4().hex}@techcorp.internal"
    response = await async_client.post(
        "/api/v1/admin/users",
        json={"name": "New Employee", "email": email, "role": UserRole.EMPLOYEE.value},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"]["email"] == email
    assert body["data"]["is_active"] is True

    login_response = await async_client.post(
        "/api/v1/auth/login", json={"email": email, "password": _SHARED_DEV_PASSWORD}
    )
    assert login_response.status_code == 200
    assert login_response.json()["data"]["access_token"]


async def test_create_user_duplicate_email_returns_409(
    async_client: httpx.AsyncClient, admin_token: str
) -> None:
    email = f"{uuid.uuid4().hex}@techcorp.internal"
    payload = {"name": "Duplicate", "email": email, "role": UserRole.EMPLOYEE.value}

    first = await async_client.post("/api/v1/admin/users", json=payload, headers=_auth_headers(admin_token))
    assert first.status_code == 201

    second = await async_client.post("/api/v1/admin/users", json=payload, headers=_auth_headers(admin_token))
    body = second.json()

    assert second.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_change_role_updates_user_role(async_client: httpx.AsyncClient, admin_token: str) -> None:
    create_response = await async_client.post(
        "/api/v1/admin/users",
        json={
            "name": "Role Change",
            "email": f"{uuid.uuid4().hex}@techcorp.internal",
            "role": UserRole.EMPLOYEE.value,
        },
        headers=_auth_headers(admin_token),
    )
    user_id = create_response.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/admin/users/{user_id}/role",
        json={"role": UserRole.MANAGER.value},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["role"] == UserRole.MANAGER.value


async def test_deactivate_blocked_when_user_holds_a_device(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    async with AsyncSessionLocal() as session:
        owner = User(
            name="Device Owner",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        session.add(owner)
        await session.flush()

        item = Item(
            name="Owned Laptop",
            serial_no=uuid.uuid4().hex,
            category_id=active_category.id,
            owner_type=OwnerType.COMPANY,
            status=DeviceStatus.ASSIGNED,
            current_owner_id=owner.id,
        )
        session.add(item)
        await session.commit()
        await session.refresh(owner)

    response = await async_client.patch(
        f"/api/v1/admin/users/{owner.id}/deactivate", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_deactivate_succeeds_when_user_has_no_devices_or_requests(
    async_client: httpx.AsyncClient, admin_token: str
) -> None:
    create_response = await async_client.post(
        "/api/v1/admin/users",
        json={
            "name": "Deactivatable",
            "email": f"{uuid.uuid4().hex}@techcorp.internal",
            "role": UserRole.EMPLOYEE.value,
        },
        headers=_auth_headers(admin_token),
    )
    user_id = create_response.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/admin/users/{user_id}/deactivate", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["is_active"] is False

    activate_response = await async_client.patch(
        f"/api/v1/admin/users/{user_id}/activate", headers=_auth_headers(admin_token)
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["data"]["is_active"] is True


async def test_list_users_filters_by_role_with_manager_name_populated(
    async_client: httpx.AsyncClient, admin_token: str
) -> None:
    async with AsyncSessionLocal() as session:
        manager = User(
            name=f"Manager-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.MANAGER,
            is_active=True,
        )
        session.add(manager)
        await session.flush()

        employee_name = f"Employee-{uuid.uuid4().hex[:8]}"
        employee = User(
            name=employee_name,
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            manager_id=manager.id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(manager)

    manager_response = await async_client.get(
        "/api/v1/admin/users", params={"role": UserRole.MANAGER.value}, headers=_auth_headers(admin_token)
    )
    manager_body = manager_response.json()
    assert manager_response.status_code == 200
    assert str(manager.id) in {row["id"] for row in manager_body["data"]}
    assert all(row["role"] == UserRole.MANAGER.value for row in manager_body["data"])

    employee_response = await async_client.get(
        "/api/v1/admin/users", params={"search": employee_name}, headers=_auth_headers(admin_token)
    )
    employee_body = employee_response.json()

    assert employee_response.status_code == 200
    assert len(employee_body["data"]) == 1
    assert employee_body["data"][0]["manager_name"] == manager.name


async def test_users_endpoints_require_it_admin_role(async_client: httpx.AsyncClient) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get("/api/v1/admin/users", headers=_auth_headers(token))
    assert response.status_code == 403
