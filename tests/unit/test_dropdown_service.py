"""`DropdownService` logic exercised against in-memory fake repositories."""

import uuid
from collections.abc import Iterable

import pytest

from app.models.enums import UserRole
from app.models.item_category import ItemCategory
from app.models.user import User
from app.repositories.item_category_repository import ItemCategoryRepository
from app.repositories.user_repository import UserRepository
from app.services.dropdown_service import DropdownService

pytestmark = pytest.mark.unit


class FakeItemCategoryRepository(ItemCategoryRepository):
    def __init__(self, categories: Iterable[ItemCategory] = ()) -> None:
        self._categories: list[ItemCategory] = list(categories)

    async def list_active(self) -> list[ItemCategory]:
        return [c for c in self._categories if c.is_active]


class FakeUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users: list[User] = list(users)

    async def list_active_by_role(self, role: UserRole) -> list[User]:
        return [u for u in self._users if u.role == role and u.is_active]


def _make_user(*, role: UserRole, is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        name="User",
        email=f"{uuid.uuid4().hex}@techcorp.internal",
        password_hash="hash",
        role=role,
        is_active=is_active,
    )


async def test_list_item_categories_returns_only_active() -> None:
    active = ItemCategory(id=uuid.uuid4(), name="Laptops", is_active=True)
    inactive = ItemCategory(id=uuid.uuid4(), name="Retired Category", is_active=False)
    service = DropdownService(FakeItemCategoryRepository([active, inactive]), FakeUserRepository())

    categories = await service.list_item_categories()

    assert [c.id for c in categories] == [active.id]


async def test_list_managers_returns_only_active_managers() -> None:
    active_manager = _make_user(role=UserRole.MANAGER, is_active=True)
    inactive_manager = _make_user(role=UserRole.MANAGER, is_active=False)
    employee = _make_user(role=UserRole.EMPLOYEE, is_active=True)
    service = DropdownService(
        FakeItemCategoryRepository(), FakeUserRepository([active_manager, inactive_manager, employee])
    )

    managers = await service.list_managers()

    assert [m.id for m in managers] == [active_manager.id]


async def test_list_employees_returns_only_active_employees() -> None:
    active_employee = _make_user(role=UserRole.EMPLOYEE, is_active=True)
    manager = _make_user(role=UserRole.MANAGER, is_active=True)
    service = DropdownService(FakeItemCategoryRepository(), FakeUserRepository([active_employee, manager]))

    employees = await service.list_employees()

    assert [e.id for e in employees] == [active_employee.id]
