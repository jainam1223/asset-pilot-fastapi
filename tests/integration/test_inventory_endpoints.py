"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/items` and `/admin/dropdowns` HTTP routes. Requires Postgres to be
reachable (docker-compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import DeviceStatus, OwnerType, UserRole
from app.models.item_category import ItemCategory
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    """Not cleaned up: every item-mutating call in this file records this
    user as `device_log.actor_id`, which is a real (though nullable) FK —
    deleting the user afterward would violate it (same rationale as
    `active_category` below).
    """
    async with AsyncSessionLocal() as session:
        user = User(
            name="Inventory Admin",
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
    """Not cleaned up: items created against it in a test become permanent
    (see M4's `device_log` append-only note — the item can never be
    deleted once it has log rows, so neither can its category via the FK).
    """
    async with AsyncSessionLocal() as session:
        category = ItemCategory(name=f"Category-{uuid.uuid4().hex[:8]}", is_active=True)
        session.add(category)
        await session.commit()
        await session.refresh(category)
    yield category


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_item_returns_201_and_writes_device_created_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    serial_no = uuid.uuid4().hex
    response = await async_client.post(
        "/api/v1/admin/items",
        json={
            "name": "Test Laptop",
            "serial_no": serial_no,
            "category_id": str(active_category.id),
            "owner_type": OwnerType.COMPANY.value,
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"]["status"] == DeviceStatus.AVAILABLE.value
    item_id = body["data"]["id"]

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item_id}/timeline",
        params={"milestones_only": "false"},
        headers=_auth_headers(admin_token),
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["device_created"]


async def test_create_item_duplicate_serial_no_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    serial_no = uuid.uuid4().hex
    payload = {
        "name": "Test Laptop",
        "serial_no": serial_no,
        "category_id": str(active_category.id),
        "owner_type": OwnerType.COMPANY.value,
    }
    first = await async_client.post("/api/v1/admin/items", json=payload, headers=_auth_headers(admin_token))
    assert first.status_code == 201

    second = await async_client.post("/api/v1/admin/items", json=payload, headers=_auth_headers(admin_token))
    body = second.json()

    assert second.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_change_status_to_lost_does_not_auto_retire(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    create_response = await async_client.post(
        "/api/v1/admin/items",
        json={
            "name": "Test Laptop",
            "serial_no": uuid.uuid4().hex,
            "category_id": str(active_category.id),
            "owner_type": OwnerType.COMPANY.value,
        },
        headers=_auth_headers(admin_token),
    )
    item_id = create_response.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/admin/items/{item_id}/status",
        json={"status": "lost", "it_note": "Reported missing"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == "lost"

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item_id}/timeline", headers=_auth_headers(admin_token)
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["marked_lost"]


async def test_get_item_detail_returns_composite(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    create_response = await async_client.post(
        "/api/v1/admin/items",
        json={
            "name": "Test Laptop",
            "serial_no": uuid.uuid4().hex,
            "category_id": str(active_category.id),
            "owner_type": OwnerType.COMPANY.value,
        },
        headers=_auth_headers(admin_token),
    )
    item_id = create_response.json()["data"]["id"]

    response = await async_client.get(f"/api/v1/admin/items/{item_id}", headers=_auth_headers(admin_token))
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["item"]["id"] == item_id
    assert body["data"]["category"]["id"] == str(active_category.id)
    assert body["data"]["current_owner"] is None
    assert body["data"]["current_request"] is None
    assert body["data"]["open_support"] == []
    assert body["data"]["active_handover"] is None


async def test_list_items_filters_by_search(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    serial_no = uuid.uuid4().hex
    await async_client.post(
        "/api/v1/admin/items",
        json={
            "name": "Searchable Laptop",
            "serial_no": serial_no,
            "category_id": str(active_category.id),
            "owner_type": OwnerType.COMPANY.value,
        },
        headers=_auth_headers(admin_token),
    )

    response = await async_client.get(
        "/api/v1/admin/items", params={"search": serial_no}, headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body["data"]) == 1
    assert body["data"][0]["serial_no"] == serial_no
    assert body["meta"]["pagination"]["total_items"] == 1


async def test_item_category_dropdown_returns_only_active(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    async with AsyncSessionLocal() as session:
        inactive = ItemCategory(name=f"Inactive-{uuid.uuid4().hex[:8]}", is_active=False)
        session.add(inactive)
        await session.commit()

    response = await async_client.get(
        "/api/v1/admin/dropdowns/item-categories", headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = {c["id"] for c in body["data"]}

    assert response.status_code == 200
    assert str(active_category.id) in ids
    assert all(c["is_active"] for c in body["data"])


async def test_items_endpoints_require_it_admin_role(
    async_client: httpx.AsyncClient, active_category: ItemCategory
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get("/api/v1/admin/items", headers=_auth_headers(token))
    assert response.status_code == 403
