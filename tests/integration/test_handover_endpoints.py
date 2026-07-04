"""API -> Service -> Repository -> Postgres, exercised through the real
`/admin/handover-requests` HTTP route. Requires Postgres to be reachable
(docker-compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.enums import DeviceStatus, HandoverStatus, OwnerType, UserRole
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Handover Admin",
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


async def _create_user(*, name: str) -> User:
    async with AsyncSessionLocal() as session:
        user = User(
            name=name,
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


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


async def _create_handover(
    *, item_id: uuid.UUID, owner_id: uuid.UUID, borrower_id: uuid.UUID, **overrides: object
) -> HandoverRequest:
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        defaults: dict[str, object] = dict(
            item_id=item_id,
            owner_id=owner_id,
            borrower_id=borrower_id,
            requested_duration_hours=24,
            status=HandoverStatus.REQUESTED,
            requested_at=now - timedelta(days=1),
        )
        defaults.update(overrides)
        handover = HandoverRequest(**defaults)
        session.add(handover)
        await session.commit()
        await session.refresh(handover)
        return handover


async def test_list_returns_seeded_handovers_with_names(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    owner = await _create_user(name="Owner One")
    borrower = await _create_user(name="Borrower One")
    item = await _create_item(category_id=active_category.id)

    statuses = [
        HandoverStatus.REQUESTED,
        HandoverStatus.ACCEPTED,
        HandoverStatus.REJECTED,
        HandoverStatus.CANCELLED,
        HandoverStatus.COMPLETED,
    ]
    for status in statuses:
        await _create_handover(item_id=item.id, owner_id=owner.id, borrower_id=borrower.id, status=status)

    response = await async_client.get(
        "/api/v1/admin/handover-requests", headers=_auth_headers(admin_token)
    )
    body = response.json()

    assert response.status_code == 200
    entries = [entry for entry in body["data"] if entry["item_id"] == str(item.id)]
    assert {entry["status"] for entry in entries} == {status.value for status in statuses}
    for entry in entries:
        assert entry["item_name"] == item.name
        assert entry["owner_name"] == owner.name
        assert entry["borrower_name"] == borrower.name


async def test_list_filters_by_status_and_item_id(
    async_client: httpx.AsyncClient, admin_token: str, active_category: ItemCategory
) -> None:
    owner = await _create_user(name="Owner Two")
    borrower = await _create_user(name="Borrower Two")
    item_a = await _create_item(category_id=active_category.id)
    item_b = await _create_item(category_id=active_category.id)

    await _create_handover(
        item_id=item_a.id, owner_id=owner.id, borrower_id=borrower.id, status=HandoverStatus.ACCEPTED
    )
    await _create_handover(
        item_id=item_a.id, owner_id=owner.id, borrower_id=borrower.id, status=HandoverStatus.REQUESTED
    )
    await _create_handover(
        item_id=item_b.id, owner_id=owner.id, borrower_id=borrower.id, status=HandoverStatus.ACCEPTED
    )

    status_response = await async_client.get(
        "/api/v1/admin/handover-requests",
        params={"status": HandoverStatus.ACCEPTED.value},
        headers=_auth_headers(admin_token),
    )
    status_entries = status_response.json()["data"]
    assert status_response.status_code == 200
    assert all(entry["status"] == HandoverStatus.ACCEPTED.value for entry in status_entries)
    assert {entry["item_id"] for entry in status_entries} >= {str(item_a.id), str(item_b.id)}

    item_response = await async_client.get(
        "/api/v1/admin/handover-requests",
        params={"item_id": str(item_a.id)},
        headers=_auth_headers(admin_token),
    )
    item_entries = item_response.json()["data"]
    assert item_response.status_code == 200
    assert len(item_entries) == 2
    assert all(entry["item_id"] == str(item_a.id) for entry in item_entries)


async def test_list_requires_it_admin_role(async_client: httpx.AsyncClient) -> None:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Regular Employee",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token(str(user.id), {"role": UserRole.EMPLOYEE.value, "email": user.email})

    response = await async_client.get(
        "/api/v1/admin/handover-requests", headers=_auth_headers(token)
    )

    assert response.status_code == 403
