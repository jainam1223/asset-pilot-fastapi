"""API -> Service -> Repository -> Postgres, exercised through the real
`GET /admin/items/{itemId}/timeline` HTTP route. Requires Postgres to be
reachable (docker-compose stack / host Postgres per README/CLAUDE.md).
"""

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.device_log import DeviceLog
from app.models.enums import ActorRole, DeviceLogEvent, UserRole
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.user import User

pytestmark = pytest.mark.integration

_PASSWORD = "S3cret-Pass!"


@pytest.fixture
async def admin_token() -> AsyncGenerator[str, None]:
    async with AsyncSessionLocal() as session:
        user = User(
            name="Timeline Admin",
            email=f"{uuid.uuid4().hex}@techcorp.internal",
            password_hash=hash_password(_PASSWORD),
            role=UserRole.IT_ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    try:
        yield create_access_token(str(user.id), {"role": UserRole.IT_ADMIN.value, "email": user.email})
    finally:
        async with AsyncSessionLocal() as session:
            db_user = await session.get(User, user.id)
            if db_user is not None:
                await session.delete(db_user)
                await session.commit()


@pytest.fixture
async def seeded_item_with_logs() -> AsyncGenerator[uuid.UUID, None]:
    """`device_log` is append-only by DB design (RULEs turn UPDATE/DELETE
    into no-ops) and `item_id` has no `ON DELETE CASCADE`, so once a device
    log row exists its item can never be deleted either. Test rows are
    randomly named/serialed so they don't collide across runs, and are
    intentionally left in place rather than cleaned up.
    """
    async with AsyncSessionLocal() as session:
        category = ItemCategory(name=f"Category-{uuid.uuid4().hex[:8]}")
        session.add(category)
        await session.flush()

        item = Item(name="Test Laptop", serial_no=uuid.uuid4().hex, category_id=category.id)
        session.add(item)
        await session.flush()

        created_log = DeviceLog(
            item_id=item.id,
            event_type=DeviceLogEvent.DEVICE_CREATED,
            actor_id=None,
            actor_role=ActorRole.SYSTEM,
            is_milestone=False,
        )
        assigned_log = DeviceLog(
            item_id=item.id,
            event_type=DeviceLogEvent.ASSIGNED,
            actor_id=None,
            actor_role=ActorRole.IT_ADMIN,
            is_milestone=True,
        )
        session.add_all([created_log, assigned_log])
        await session.commit()

        item_id = item.id

    yield item_id


async def test_timeline_default_returns_milestones_only_ordered(
    async_client: httpx.AsyncClient, admin_token: str, seeded_item_with_logs: uuid.UUID
) -> None:
    response = await async_client.get(
        f"/api/v1/admin/items/{seeded_item_with_logs}/timeline",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    events = [entry["event_type"] for entry in body["data"]]
    assert events == [DeviceLogEvent.ASSIGNED.value]


async def test_timeline_milestones_only_false_returns_all_rows_ordered(
    async_client: httpx.AsyncClient, admin_token: str, seeded_item_with_logs: uuid.UUID
) -> None:
    response = await async_client.get(
        f"/api/v1/admin/items/{seeded_item_with_logs}/timeline",
        params={"milestones_only": "false"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    body = response.json()

    assert response.status_code == 200
    events = [entry["event_type"] for entry in body["data"]]
    assert events == [DeviceLogEvent.DEVICE_CREATED.value, DeviceLogEvent.ASSIGNED.value]


async def test_timeline_without_token_returns_401(
    async_client: httpx.AsyncClient, seeded_item_with_logs: uuid.UUID
) -> None:
    response = await async_client.get(f"/api/v1/admin/items/{seeded_item_with_logs}/timeline")
    assert response.status_code == 401


async def test_timeline_forbids_non_admin_role(
    async_client: httpx.AsyncClient, seeded_item_with_logs: uuid.UUID
) -> None:
    token = create_access_token(str(uuid.uuid4()), {"role": UserRole.EMPLOYEE.value})
    response = await async_client.get(
        f"/api/v1/admin/items/{seeded_item_with_logs}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
