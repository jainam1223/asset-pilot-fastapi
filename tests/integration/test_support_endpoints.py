"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/support-requests` HTTP routes. Requires Postgres to be reachable
(docker-compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import DeviceStatus, OwnerType, RequestStatus, SupportStatus, SupportType, UserRole
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    """Not cleaned up: every support call in this file records this user
    as `device_log.actor_id` / `support_request.resolved_by` — real FKs.
    """
    async with AsyncSessionLocal() as session:
        user = User(
            name="Support Admin",
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
        )
        defaults.update(overrides)
        request = Request(**defaults)
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request


async def _create_support_request(
    *, item_id: uuid.UUID, requester_id: uuid.UUID, **overrides: object
) -> SupportRequest:
    async with AsyncSessionLocal() as session:
        defaults: dict[str, object] = dict(
            item_id=item_id,
            requester_id=requester_id,
            type=SupportType.DAMAGE,
            description="Screen cracked",
            status=SupportStatus.OPEN,
        )
        defaults.update(overrides)
        ticket = SupportRequest(**defaults)
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def test_start_damage_ticket_moves_item_under_repair_and_writes_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.ASSIGNED, current_owner_id=requester.id
    )
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    ticket = await _create_support_request(
        item_id=item.id, requester_id=requester.id, request_id=request.id
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/start", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == SupportStatus.IN_PROGRESS.value

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    assert item_response.json()["data"]["item"]["status"] == DeviceStatus.UNDER_REPAIR.value

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["status_changed"]


async def test_start_already_started_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    ticket = await _create_support_request(
        item_id=item.id, requester_id=requester.id, status=SupportStatus.IN_PROGRESS
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/start", headers=_auth_headers(admin_token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_resolve_repaired_in_place_returns_item_to_assigned(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR, current_owner_id=requester.id
    )
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    ticket = await _create_support_request(
        item_id=item.id,
        requester_id=requester.id,
        request_id=request.id,
        status=SupportStatus.IN_PROGRESS,
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={"resolution": "repaired_in_place", "it_note": "Fixed on-site"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == SupportStatus.RESOLVED.value
    assert body["data"]["resolution"] == "repaired_in_place"

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    assert item_response.json()["data"]["item"]["status"] == DeviceStatus.ASSIGNED.value

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["status_changed", "support_resolved"]


async def test_resolve_swap_repoints_request_and_transitions_both_items(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    old_item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR, current_owner_id=requester.id
    )
    new_item = await _create_item(category_id=active_category.id, status=DeviceStatus.AVAILABLE)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=old_item.id
    )
    ticket = await _create_support_request(
        item_id=old_item.id,
        requester_id=requester.id,
        request_id=request.id,
        status=SupportStatus.IN_PROGRESS,
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={
            "resolution": "swapped",
            "it_note": "Faulty unit swapped for a spare",
            "swapped_to_item_id": str(new_item.id),
            "old_item_next_status": "retired",
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == SupportStatus.RESOLVED.value
    assert body["data"]["swapped_to_item_id"] == str(new_item.id)

    request_response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}", headers=_auth_headers(admin_token)
    )
    assert request_response.json()["data"]["assigned_item_id"] == str(new_item.id)

    old_item_response = await async_client.get(
        f"/api/v1/admin/items/{old_item.id}", headers=_auth_headers(admin_token)
    )
    old_item_body = old_item_response.json()["data"]["item"]
    assert old_item_body["status"] == DeviceStatus.RETIRED.value
    assert old_item_body["current_owner_id"] is None

    new_item_response = await async_client.get(
        f"/api/v1/admin/items/{new_item.id}", headers=_auth_headers(admin_token)
    )
    new_item_body = new_item_response.json()["data"]["item"]
    assert new_item_body["status"] == DeviceStatus.ASSIGNED.value
    assert new_item_body["current_owner_id"] == str(requester.id)

    old_timeline = await async_client.get(
        f"/api/v1/admin/items/{old_item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    assert [entry["event_type"] for entry in old_timeline.json()["data"]] == [
        "swapped_out",
        "support_resolved",
    ]

    new_timeline = await async_client.get(
        f"/api/v1/admin/items/{new_item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    assert [entry["event_type"] for entry in new_timeline.json()["data"]] == ["swapped_in"]


async def test_resolve_swap_wrong_category_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    other_category_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        other_category = ItemCategory(name=f"Category-{uuid.uuid4().hex[:8]}", is_active=True)
        session.add(other_category)
        await session.commit()
        await session.refresh(other_category)
        other_category_id = other_category.id

    old_item = await _create_item(category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR)
    new_item = await _create_item(category_id=other_category_id, status=DeviceStatus.AVAILABLE)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=old_item.id
    )
    ticket = await _create_support_request(
        item_id=old_item.id,
        requester_id=requester.id,
        request_id=request.id,
        status=SupportStatus.IN_PROGRESS,
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={
            "resolution": "swapped",
            "swapped_to_item_id": str(new_item.id),
            "old_item_next_status": "retired",
        },
        headers=_auth_headers(admin_token),
    )

    assert response.status_code == 422


async def test_resolve_swap_target_not_available_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    old_item = await _create_item(category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR)
    new_item = await _create_item(category_id=active_category.id, status=DeviceStatus.ASSIGNED)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=old_item.id
    )
    ticket = await _create_support_request(
        item_id=old_item.id,
        requester_id=requester.id,
        request_id=request.id,
        status=SupportStatus.IN_PROGRESS,
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={
            "resolution": "swapped",
            "swapped_to_item_id": str(new_item.id),
            "old_item_next_status": "retired",
        },
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_resolve_marked_lost_sets_item_lost_and_completes_request(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.ASSIGNED, current_owner_id=requester.id
    )
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    ticket = await _create_support_request(
        item_id=item.id,
        requester_id=requester.id,
        request_id=request.id,
        type=SupportType.LOST,
        status=SupportStatus.IN_PROGRESS,
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={"resolution": "marked_lost", "it_note": "Never returned"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["resolution"] == "marked_lost"

    item_response = await async_client.get(
        f"/api/v1/admin/items/{item.id}", headers=_auth_headers(admin_token)
    )
    assert item_response.json()["data"]["item"]["status"] == DeviceStatus.LOST.value

    request_response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}", headers=_auth_headers(admin_token)
    )
    request_body = request_response.json()["data"]
    assert request_body["status"] == RequestStatus.COMPLETED.value
    assert request_body["completed_next_status"] is None


async def test_resolve_missing_swap_fields_returns_422(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id, status=DeviceStatus.UNDER_REPAIR)
    ticket = await _create_support_request(
        item_id=item.id, requester_id=requester.id, status=SupportStatus.IN_PROGRESS
    )

    response = await async_client.patch(
        f"/api/v1/admin/support-requests/{ticket.id}/resolve",
        json={"resolution": "swapped"},
        headers=_auth_headers(admin_token),
    )

    assert response.status_code == 422


async def test_list_support_requests_filters_by_status_and_type(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    open_item = await _create_item(category_id=active_category.id)
    open_ticket = await _create_support_request(
        item_id=open_item.id, requester_id=requester.id, status=SupportStatus.OPEN, type=SupportType.DAMAGE
    )
    resolved_item = await _create_item(category_id=active_category.id)
    resolved_ticket = await _create_support_request(
        item_id=resolved_item.id,
        requester_id=requester.id,
        status=SupportStatus.RESOLVED,
        type=SupportType.UPDATE,
    )

    # This is a shared dev database with pre-existing tickets from seed data
    # and other test runs, so filtering is verified by membership rather
    # than an exact total count.
    response = await async_client.get(
        "/api/v1/admin/support-requests",
        headers=_auth_headers(admin_token),
        params={"status": "open", "type": "damage"},
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(open_ticket.id) in ids
    assert str(resolved_ticket.id) not in ids

    item_scoped_response = await async_client.get(
        "/api/v1/admin/support-requests",
        headers=_auth_headers(admin_token),
        params={"item_id": str(open_item.id)},
    )
    item_scoped_ids = {row["id"] for row in item_scoped_response.json()["data"]}
    assert item_scoped_ids == {str(open_ticket.id)}


async def test_get_support_request_detail_includes_item_and_requester(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    ticket = await _create_support_request(item_id=item.id, requester_id=requester.id)

    response = await async_client.get(
        f"/api/v1/admin/support-requests/{ticket.id}", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["item"]["id"] == str(item.id)
    assert body["data"]["requester"]["id"] == str(requester.id)


async def test_support_endpoints_require_it_admin_role(
    async_client: httpx.AsyncClient, active_category: ItemCategory
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get(
        "/api/v1/admin/support-requests", headers=_auth_headers(token)
    )
    assert response.status_code == 403
