"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/requests/{id}/suggested-devices|booking-range|assign` and
`/admin/items/{itemId}/bookings|direct-assign`, `/admin/items/client-available`
HTTP routes. Requires Postgres to be reachable (docker-compose stack / host
Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import DeviceStatus, OwnerType, RequestStatus, UserRole
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    """Not cleaned up: every assignment call in this file records this user
    as `device_log.actor_id` / `request.it_decided_by` — real FKs.
    """
    async with AsyncSessionLocal() as session:
        user = User(
            name="Assignment Admin",
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


@pytest.fixture
async def requester() -> AsyncGenerator[User, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name=f"Requester-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    yield user


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_item(*, category_id: uuid.UUID, **overrides: object) -> Item:
    async with AsyncSessionLocal() as session:
        defaults: dict[str, object] = dict(
            name="Laptop",
            serial_no=uuid.uuid4().hex,
            category_id=category_id,
            owner_type=OwnerType.COMPANY,
            status=DeviceStatus.AVAILABLE,
        )
        defaults.update(overrides)
        item = Item(**defaults)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def _create_request(
    *, requester_id: uuid.UUID, category_id: uuid.UUID, status: RequestStatus, **overrides: object
) -> Request:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        defaults: dict[str, object] = dict(
            requester_id=requester_id,
            category_id=category_id,
            requested_from=now,
            requested_to=now + timedelta(days=7),
            status=status,
        )
        defaults.update(overrides)
        request = Request(**defaults)
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request


async def test_suggested_devices_excludes_wrong_category_and_unavailable_items(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    other_category = ItemCategory(name=f"Other-{uuid.uuid4().hex[:8]}", is_active=True)
    async with AsyncSessionLocal() as session:
        session.add(other_category)
        await session.commit()
        await session.refresh(other_category)

    matching_item = await _create_item(category_id=active_category.id)
    await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    await _create_item(category_id=other_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )

    response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}/suggested-devices", headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(matching_item.id) in ids
    assert all(row["category_id"] == str(active_category.id) for row in body["data"])
    assert all(row["active_bookings_count"] == 0 for row in body["data"])


async def test_assign_success_updates_request_item_and_writes_milestone_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )
    now = datetime.now(UTC)

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/assign",
        json={
            "item_id": str(item.id),
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=7)).isoformat(),
            "is_wfh": False,
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == RequestStatus.ASSIGNED.value
    assert body["data"]["assigned_item_id"] == str(item.id)

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    item_body = item_response.json()
    assert item_body["data"]["item"]["status"] == DeviceStatus.ASSIGNED.value
    assert item_body["data"]["item"]["current_owner_id"] == str(requester.id)

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline", headers=_auth_headers(admin_token)
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["assigned"]


async def test_assign_unavailable_item_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )
    now = datetime.now(UTC)

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/assign",
        json={
            "item_id": str(item.id),
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=7)).isoformat(),
            "is_wfh": False,
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_assign_category_mismatch_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    other_category = ItemCategory(name=f"Other-{uuid.uuid4().hex[:8]}", is_active=True)
    async with AsyncSessionLocal() as session:
        session.add(other_category)
        await session.commit()
        await session.refresh(other_category)

    item = await _create_item(category_id=other_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )
    now = datetime.now(UTC)

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/assign",
        json={
            "item_id": str(item.id),
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=7)).isoformat(),
            "is_wfh": False,
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_assign_overlapping_range_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    now = datetime.now(UTC)
    await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.ASSIGNED,
        assigned_item_id=item.id,
        assigned_from=now,
        assigned_to=now + timedelta(days=10),
    )
    # Re-open the item for a second concurrent assignment attempt, bypassing the
    # `item.status == available` guard, to exercise the overlap check itself.
    async with AsyncSessionLocal() as session:
        db_item = await session.get(Item, item.id)
        assert db_item is not None
        db_item.status = DeviceStatus.AVAILABLE
        await session.commit()

    second_request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )

    response = await async_client.post(
        f"/api/v1/admin/requests/{second_request.id}/assign",
        json={
            "item_id": str(item.id),
            "assigned_from": (now + timedelta(days=3)).isoformat(),
            "assigned_to": (now + timedelta(days=5)).isoformat(),
            "is_wfh": False,
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_booking_range_update_success(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    now = datetime.now(UTC)
    request = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.ASSIGNED,
        assigned_item_id=item.id,
        assigned_from=now,
        assigned_to=now + timedelta(days=5),
    )
    new_from = now + timedelta(days=1)
    new_to = now + timedelta(days=8)

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/booking-range",
        json={"assigned_from": new_from.isoformat(), "assigned_to": new_to.isoformat()},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["assigned_from"] == new_from.isoformat().replace("+00:00", "Z")
    assert body["data"]["assigned_to"] == new_to.isoformat().replace("+00:00", "Z")


async def test_booking_range_wrong_status_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )
    now = datetime.now(UTC)

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/booking-range",
        json={
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=1)).isoformat(),
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_get_item_bookings_returns_only_assigned_requests(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    now = datetime.now(UTC)
    booking = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.ASSIGNED,
        assigned_item_id=item.id,
        assigned_from=now,
        assigned_to=now + timedelta(days=5),
    )
    await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.get(
        f"/api/v1/admin/items/{item.id}/bookings", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == str(booking.id)
    assert body["data"][0]["requester_name"] == requester.name


async def test_list_client_available_returns_only_client_owned_available_items(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    client_item = await _create_item(
        category_id=active_category.id, owner_type=OwnerType.CLIENT, client_name="Acme Corp"
    )
    await _create_item(category_id=active_category.id, owner_type=OwnerType.COMPANY)
    await _create_item(
        category_id=active_category.id,
        owner_type=OwnerType.CLIENT,
        client_name="Acme Corp",
        status=DeviceStatus.ASSIGNED,
    )

    response = await async_client.get(
        "/api/v1/admin/items/client-available", headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(client_item.id) in ids
    assert all(row["owner_type"] == OwnerType.CLIENT.value for row in body["data"])
    assert all(row["status"] == DeviceStatus.AVAILABLE.value for row in body["data"])


async def test_direct_assign_creates_client_direct_request_and_writes_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, owner_type=OwnerType.CLIENT, client_name="Acme")
    now = datetime.now(UTC)

    response = await async_client.post(
        f"/api/v1/admin/items/{item.id}/direct-assign",
        json={
            "employee_id": str(requester.id),
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=14)).isoformat(),
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 201
    assert body["data"]["is_client_direct"] is True
    assert body["data"]["status"] == RequestStatus.ASSIGNED.value
    assert body["data"]["requester_id"] == str(requester.id)
    assert body["data"]["assigned_item_id"] == str(item.id)

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline", headers=_auth_headers(admin_token)
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["client_assigned"]


async def test_direct_assign_non_client_item_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, owner_type=OwnerType.COMPANY)
    now = datetime.now(UTC)

    response = await async_client.post(
        f"/api/v1/admin/items/{item.id}/direct-assign",
        json={
            "employee_id": str(requester.id),
            "assigned_from": now.isoformat(),
            "assigned_to": (now + timedelta(days=14)).isoformat(),
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_assignment_endpoints_require_it_admin_role(
    async_client: httpx.AsyncClient, active_category: ItemCategory
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get(
        "/api/v1/admin/items/client-available", headers=_auth_headers(token)
    )
    assert response.status_code == 403
