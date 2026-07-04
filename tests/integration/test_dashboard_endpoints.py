"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/dashboard/*` HTTP routes. Requires Postgres to be reachable
(docker-compose stack / host Postgres per README/CLAUDE.md).

This is a shared dev database with pre-existing rows from seed data and
other test runs, so assertions favor internal consistency and membership
over exact totals.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import (
    DeviceStatus,
    OwnerType,
    RequestPriority,
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
_STATUS_BREAKDOWN_KEYS = {
    "available",
    "assigned",
    "under_repair",
    "maintenance",
    "shipping_pending",
    "return_shipping_pending",
    "lost",
    "retired",
}


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Dashboard Admin",
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


async def _create_request(*, requester_id: uuid.UUID, category_id: uuid.UUID, **overrides: object) -> Request:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        defaults: dict[str, object] = dict(
            requester_id=requester_id,
            category_id=category_id,
            requested_from=now,
            requested_to=now + timedelta(days=7),
            status=RequestStatus.PENDING_IT_APPROVAL,
            priority=RequestPriority.MEDIUM,
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


async def test_summary_status_breakdown_sums_to_total_items(
    async_client: httpx.AsyncClient, admin_token: str
) -> None:
    async with AsyncSessionLocal() as session:
        total_items = (await session.execute(select(func.count()).select_from(Item))).scalar_one()

    response = await async_client.get("/api/v1/admin/dashboard/summary", headers=_auth_headers(admin_token))
    body = response.json()

    assert response.status_code == 200
    status_breakdown = body["data"]["status_breakdown"]
    assert set(status_breakdown.keys()) == _STATUS_BREAKDOWN_KEYS
    assert sum(status_breakdown.values()) == total_items
    for key in (
        "pending_requests_count",
        "open_support_count",
        "active_handovers_count",
        "pending_extensions_count",
    ):
        assert isinstance(body["data"][key], int)


async def test_summary_pending_requests_count_reflects_new_pending_request(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    before = await async_client.get("/api/v1/admin/dashboard/summary", headers=_auth_headers(admin_token))
    before_count = before.json()["data"]["pending_requests_count"]

    await _create_request(
        requester_id=requester.id,
        category_id=active_category.id,
        status=RequestStatus.PENDING_IT_APPROVAL,
    )

    after = await async_client.get("/api/v1/admin/dashboard/summary", headers=_auth_headers(admin_token))
    after_count = after.json()["data"]["pending_requests_count"]

    assert after_count == before_count + 1


async def test_recent_requests_returns_newest_first(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    older = await _create_request(requester_id=requester.id, category_id=active_category.id)
    newer = await _create_request(requester_id=requester.id, category_id=active_category.id)

    response = await async_client.get(
        "/api/v1/admin/dashboard/recent-requests",
        headers=_auth_headers(admin_token),
        params={"limit": 1000},
    )
    body = response.json()

    assert response.status_code == 200
    ids = [row["id"] for row in body["data"]]
    assert ids.index(str(newer.id)) < ids.index(str(older.id))

    created_ats = [row["created_at"] for row in body["data"]]
    assert created_ats == sorted(created_ats, reverse=True)

    entry = next(row for row in body["data"] if row["id"] == str(newer.id))
    assert entry["category_name"] == active_category.name
    assert entry["requester_name"] == requester.name


async def test_open_support_returns_only_open_and_in_progress_oldest_first(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory, requester: User
) -> None:
    open_item = await _create_item(category_id=active_category.id)
    open_ticket = await _create_support_request(
        item_id=open_item.id, requester_id=requester.id, status=SupportStatus.OPEN
    )
    resolved_item = await _create_item(category_id=active_category.id)
    resolved_ticket = await _create_support_request(
        item_id=resolved_item.id, requester_id=requester.id, status=SupportStatus.RESOLVED
    )

    response = await async_client.get(
        "/api/v1/admin/dashboard/open-support",
        headers=_auth_headers(admin_token),
        params={"limit": 1000},
    )
    body = response.json()

    assert response.status_code == 200
    ids = {row["id"] for row in body["data"]}
    statuses = {row["status"] for row in body["data"]}
    assert str(open_ticket.id) in ids
    assert str(resolved_ticket.id) not in ids
    assert statuses <= {SupportStatus.OPEN.value, SupportStatus.IN_PROGRESS.value}

    filed_ats = [row["filed_at"] for row in body["data"]]
    assert filed_ats == sorted(filed_ats)

    entry = next(row for row in body["data"] if row["id"] == str(open_ticket.id))
    assert entry["item_name"] == open_item.name


async def test_dashboard_endpoints_require_it_admin_role(async_client: httpx.AsyncClient) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get("/api/v1/admin/dashboard/summary", headers=_auth_headers(token))
    assert response.status_code == 403
