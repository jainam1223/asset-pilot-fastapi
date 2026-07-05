"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/shipping/outbound|returns` and
`/admin/requests/{id}/ship|confirm-delivery|complete-return` HTTP routes.
Requires Postgres to be reachable (docker-compose stack / host Postgres
per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import (
    DeviceStatus,
    OwnerType,
    RequestStatus,
    SupportStatus,
    SupportType,
    UserRole,
)
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    """Not cleaned up: every shipping call in this file records this user
    as `device_log.actor_id` / `request.completed_by` — real FKs.
    """
    async with AsyncSessionLocal() as session:
        user = User(
            name="Shipping Admin",
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
            status=DeviceStatus.ASSIGNED,
        )
        defaults.update(overrides)
        item = Item(**defaults)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def _create_request(
    *, requester_id: uuid.UUID, category_id: uuid.UUID, assigned_item_id: uuid.UUID, **overrides: object
) -> Request:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        defaults: dict[str, object] = dict(
            requester_id=requester_id,
            category_id=category_id,
            assigned_item_id=assigned_item_id,
            requested_from=now,
            requested_to=now + timedelta(days=7),
            assigned_from=now,
            assigned_to=now + timedelta(days=7),
            status=RequestStatus.ASSIGNED,
            is_wfh=True,
        )
        defaults.update(overrides)
        request = Request(**defaults)
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request


async def _create_support_request(*, item_id: uuid.UUID, requester_id: uuid.UUID) -> SupportRequest:
    async with AsyncSessionLocal() as session:
        ticket = SupportRequest(
            item_id=item_id,
            requester_id=requester_id,
            type=SupportType.DAMAGE,
            description="Screen cracked",
            status=SupportStatus.OPEN,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def test_ship_moves_item_to_shipping_pending_and_writes_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id, is_wfh=True
    )

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/ship",
        json={"ship_tracking_url": "https://track.example/123"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["ship_tracking_url"] == "https://track.example/123"
    assert body["data"]["ship_initiated_at"] is not None

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    assert item_response.json()["data"]["item"]["status"] == DeviceStatus.SHIPPING_PENDING.value

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["ship_outbound_initiated"]


async def test_ship_non_wfh_request_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id, is_wfh=False
    )

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/ship",
        json={"ship_tracking_url": "https://track.example/123"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_confirm_delivery_requires_shipping_pending(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id, is_wfh=True
    )

    conflict_response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/confirm-delivery", headers=_auth_headers(admin_token)
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "CONFLICT"

    async with AsyncSessionLocal() as session:
        db_item = await session.get(Item, item.id)
        assert db_item is not None
        db_item.status = DeviceStatus.SHIPPING_PENDING
        await session.commit()

    success_response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/confirm-delivery", headers=_auth_headers(admin_token)
    )
    body = success_response.json()

    assert success_response.status_code == 200
    assert body["data"]["ship_completed_at"] is not None

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    assert item_response.json()["data"]["item"]["status"] == DeviceStatus.ASSIGNED.value


async def test_outbound_queue_lists_eligible_requests_only(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    eligible_item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    eligible_request = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        assigned_item_id=eligible_item.id,
        is_wfh=True,
    )
    already_shipped_item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    already_shipped_request = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        assigned_item_id=already_shipped_item.id,
        is_wfh=True,
        ship_initiated_at=datetime.now(UTC),
    )
    non_wfh_item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    non_wfh_request = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        assigned_item_id=non_wfh_item.id,
        is_wfh=False,
    )

    response = await async_client.get(
        "/api/v1/admin/shipping/outbound", headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(eligible_request.id) in ids
    assert str(already_shipped_request.id) not in ids
    assert str(non_wfh_request.id) not in ids


async def test_returns_queue_lists_return_shipping_pending_items(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    returning_item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.RETURN_SHIPPING_PENDING
    )
    returning_request = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        assigned_item_id=returning_item.id,
        return_initiated_at=datetime.now(UTC),
    )
    still_assigned_item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    still_assigned_request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=still_assigned_item.id
    )

    response = await async_client.get(
        "/api/v1/admin/shipping/returns", headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(returning_request.id) in ids
    assert str(still_assigned_request.id) not in ids


async def test_complete_return_completes_request_clears_owner_and_auto_closes_support(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(
        category_id=active_category.id,
        status=DeviceStatus.RETURN_SHIPPING_PENDING,
        current_owner_id=requester.id,
    )
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    open_ticket = await _create_support_request(item_id=item.id, requester_id=requester.id)

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/complete-return",
        json={"next_status": "available"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == RequestStatus.COMPLETED.value
    assert body["data"]["completed_next_status"] == DeviceStatus.AVAILABLE.value

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    item_body = item_response.json()["data"]["item"]
    assert item_body["status"] == DeviceStatus.AVAILABLE.value
    assert item_body["current_owner_id"] is None

    async with AsyncSessionLocal() as session:
        refreshed_ticket = await session.get(SupportRequest, open_ticket.id)
        assert refreshed_ticket is not None
        assert refreshed_ticket.status == SupportStatus.RESOLVED
        assert refreshed_ticket.auto_closed is True

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["return_received", "assignment_completed", "support_auto_closed"]

    milestone_only = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline", headers=_auth_headers(admin_token)
    )
    milestone_events = [entry["event_type"] for entry in milestone_only.json()["data"]]
    assert milestone_events == ["return_received", "assignment_completed"]


async def test_complete_return_invalid_next_status_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/complete-return",
        json={"next_status": "lost"},
        headers=_auth_headers(admin_token),
    )

    assert response.status_code == 422


async def test_complete_return_wrong_item_status_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.SHIPPING_PENDING)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )

    response = await async_client.post(
        f"/api/v1/admin/requests/{request.id}/complete-return",
        json={"next_status": "available"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_shipping_endpoints_require_it_admin_role(
    async_client: httpx.AsyncClient, active_category: ItemCategory
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get(
        "/api/v1/admin/shipping/outbound", headers=_auth_headers(token)
    )
    assert response.status_code == 403
