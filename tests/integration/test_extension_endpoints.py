"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/extension-requests` HTTP routes. Requires Postgres to be reachable
(docker-compose stack / host Postgres per README/CLAUDE.md).
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
    ExtensionStatus,
    MgrApprovalStatus,
    OwnerType,
    RequestStatus,
    UserRole,
)
from app.models.extension_request import ExtensionRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    """Not cleaned up: every extension call in this file records this user
    as `device_log.actor_id` / `extension_request.it_decided_by` — real FKs.
    """
    async with AsyncSessionLocal() as session:
        user = User(
            name="Extension Admin",
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


async def _create_extension_request(
    *, original_request_id: uuid.UUID, requester_id: uuid.UUID, **overrides: object
) -> ExtensionRequest:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        defaults: dict[str, object] = dict(
            original_request_id=original_request_id,
            requester_id=requester_id,
            current_assigned_to=now + timedelta(days=7),
            extended_to=now + timedelta(days=14),
            status=ExtensionStatus.PENDING,
        )
        defaults.update(overrides)
        extension_request = ExtensionRequest(**defaults)
        session.add(extension_request)
        await session.commit()
        await session.refresh(extension_request)
        return extension_request


async def test_approve_moves_parent_assigned_to_and_writes_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(
        category_id=active_category.id, status=DeviceStatus.ASSIGNED, current_owner_id=requester.id
    )
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    extension_request = await _create_extension_request(
        original_request_id=request.id, requester_id=requester.id
    )

    response = await async_client.patch(
        f"/api/v1/admin/extension-requests/{extension_request.id}/approve",
        json={"it_note": "Approved for one more week"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == ExtensionStatus.APPROVED.value

    request_response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}", headers=_auth_headers(admin_token)
    )
    request_body = request_response.json()["data"]
    assert request_body["assigned_to"] == body["data"]["extended_to"]

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["extension_approved"]


async def test_approve_pending_manager_extension_returns_conflict(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    extension_request = await _create_extension_request(
        original_request_id=request.id,
        requester_id=requester.id,
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.PENDING,
    )

    response = await async_client.patch(
        f"/api/v1/admin/extension-requests/{extension_request.id}/approve",
        json={"it_note": "trying anyway"},
        headers=_auth_headers(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_approve_already_decided_extension_returns_conflict(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    extension_request = await _create_extension_request(
        original_request_id=request.id, requester_id=requester.id, status=ExtensionStatus.APPROVED
    )

    response = await async_client.patch(
        f"/api/v1/admin/extension-requests/{extension_request.id}/approve",
        json={},
        headers=_auth_headers(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_reject_sets_status_and_writes_log(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    extension_request = await _create_extension_request(
        original_request_id=request.id, requester_id=requester.id
    )

    response = await async_client.patch(
        f"/api/v1/admin/extension-requests/{extension_request.id}/reject",
        json={"it_note": "Not enough justification"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == ExtensionStatus.REJECTED.value

    timeline = await async_client.get(
        f"/api/v1/admin/items/{item.id}/timeline",
        headers=_auth_headers(admin_token),
        params={"milestones_only": False},
    )
    events = [entry["event_type"] for entry in timeline.json()["data"]]
    assert events == ["extension_rejected"]

    request_response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}", headers=_auth_headers(admin_token)
    )
    # Reject must not move the parent request's assigned_to.
    returned_assigned_to = datetime.fromisoformat(request_response.json()["data"]["assigned_to"])
    assert request.assigned_to is not None
    assert returned_assigned_to == request.assigned_to


async def test_list_extension_requests_filters_by_status(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    pending_item = await _create_item(category_id=active_category.id)
    pending_request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=pending_item.id
    )
    pending_extension = await _create_extension_request(
        original_request_id=pending_request.id, requester_id=requester.id, status=ExtensionStatus.PENDING
    )

    approved_item = await _create_item(category_id=active_category.id)
    approved_request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=approved_item.id
    )
    approved_extension = await _create_extension_request(
        original_request_id=approved_request.id, requester_id=requester.id, status=ExtensionStatus.APPROVED
    )

    # This is a shared dev database with pre-existing extensions from seed
    # data and other test runs, so filtering is verified by membership
    # rather than an exact total count.
    response = await async_client.get(
        "/api/v1/admin/extension-requests",
        headers=_auth_headers(admin_token),
        params={"status": "pending"},
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}

    assert response.status_code == 200
    assert str(pending_extension.id) in ids
    assert str(approved_extension.id) not in ids


async def test_get_extension_request_detail_includes_request_item_and_requester(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    item = await _create_item(category_id=active_category.id)
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, assigned_item_id=item.id
    )
    extension_request = await _create_extension_request(
        original_request_id=request.id, requester_id=requester.id
    )

    response = await async_client.get(
        f"/api/v1/admin/extension-requests/{extension_request.id}", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["request"]["id"] == str(request.id)
    assert body["data"]["item"]["id"] == str(item.id)
    assert body["data"]["requester"]["id"] == str(requester.id)


async def test_extension_endpoints_require_it_admin_role(
    async_client: httpx.AsyncClient, active_category: ItemCategory
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get("/api/v1/admin/extension-requests", headers=_auth_headers(token))
    assert response.status_code == 403
