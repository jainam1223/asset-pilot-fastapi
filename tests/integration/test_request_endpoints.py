"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/requests` and `/admin/it/approvals` HTTP routes. Requires Postgres
to be reachable (docker-compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import MgrApprovalStatus, RequestPriority, RequestStatus, UserRole
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Request Admin",
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
async def manager() -> AsyncGenerator[User, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name=f"Manager-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.MANAGER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    yield user


@pytest.fixture
async def requester(manager: User) -> AsyncGenerator[User, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name=f"Requester-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            manager_id=manager.id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    yield user


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_request(
    *,
    requester_id: uuid.UUID,
    category_id: uuid.UUID,
    status: RequestStatus,
    priority: RequestPriority = RequestPriority.MEDIUM,
    requires_mgr_approval: bool = False,
) -> Request:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        request = Request(
            requester_id=requester_id,
            category_id=category_id,
            requested_from=now,
            requested_to=now + timedelta(days=7),
            status=status,
            priority=priority,
            requires_mgr_approval=requires_mgr_approval,
        )
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request


async def test_list_it_approvals_returns_only_pending_sorted_by_priority_then_oldest(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    low = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.PENDING_IT_APPROVAL,
        priority=RequestPriority.LOW,
    )
    high = await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.PENDING_IT_APPROVAL,
        priority=RequestPriority.HIGH,
    )
    await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.get(
        "/api/v1/admin/it/approvals", params={"page_size": 100}, headers=_auth_headers(admin_token)
    )
    body = response.json()
    ids = [row["id"] for row in body["data"]]

    assert response.status_code == 200
    assert all(row["status"] == RequestStatus.PENDING_IT_APPROVAL.value for row in body["data"])
    assert str(high.id) in ids
    assert str(low.id) in ids
    assert ids.index(str(high.id)) < ids.index(str(low.id))


async def test_reject_flips_pending_it_approval_to_rejected(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/reject",
        json={"rejected_reason": "No budget", "it_decision_note": "Reapply next quarter"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == RequestStatus.REJECTED.value
    assert body["data"]["rejected_by"] == "it_admin"
    assert body["data"]["rejected_reason"] == "No budget"


async def test_reject_wrong_status_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/reject",
        json={"rejected_reason": "No budget"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_escalate_to_manager_defaults_manager_id_from_requester(
    async_client: httpx.AsyncClient,
    admin_token: str,
    active_category: ItemCategory,
    requester: User,
    manager: User,
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.PENDING_IT_APPROVAL
    )

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/escalate-to-manager",
        json={},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == RequestStatus.PENDING_MGR_APPROVAL.value
    assert body["data"]["mgr_approval_status"] == MgrApprovalStatus.PENDING.value
    assert body["data"]["manager_id"] == str(manager.id)
    assert body["data"]["requires_mgr_approval"] is True


async def test_cancel_terminal_request_returns_409(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.COMPLETED
    )

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/cancel",
        json={"rejected_reason": "No longer needed"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "CONFLICT"


async def test_cancel_non_terminal_request_sets_rejected_by_it_admin_cancel(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.patch(
        f"/api/v1/admin/requests/{request.id}/cancel",
        json={"rejected_reason": "Duplicate request"},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["status"] == RequestStatus.CANCELLED.value
    assert body["data"]["rejected_by"] == "it_admin_cancel"


async def test_get_request_detail_returns_joins(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    request = await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.get(
        f"/api/v1/admin/requests/{request.id}", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["id"] == str(request.id)
    assert body["data"]["category_name"] == active_category.name
    assert body["data"]["requester_name"] == requester.name
    assert body["data"]["item"] is None


async def test_list_requests_filters_by_status_and_search(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    await _create_request(
        requester_id=requester.id, category_id=active_category.id, status=RequestStatus.REQUESTED
    )

    response = await async_client.get(
        "/api/v1/admin/requests",
        params={"status": RequestStatus.REQUESTED.value, "search": requester.name},
        headers=_auth_headers(admin_token),
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body["data"]) >= 1
    assert all(row["status"] == RequestStatus.REQUESTED.value for row in body["data"])
    assert all(row["requester_name"] == requester.name for row in body["data"])


async def test_requests_endpoints_require_it_admin_role(async_client: httpx.AsyncClient) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get("/api/v1/admin/requests", headers=_auth_headers(token))
    assert response.status_code == 403
