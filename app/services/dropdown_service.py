"""Shared dropdown data (API §14): active item categories, managers, and
employees, used by IT-Admin forms elsewhere in the flow.
"""

import uuid
from dataclasses import dataclass

from app.models.enums import UserRole
from app.models.item_category import ItemCategory
from app.models.user import User
from app.repositories.item_category_repository import ItemCategoryRepository
from app.repositories.user_repository import UserRepository


@dataclass
class CategoryOption:
    id: uuid.UUID
    name: str
    description: str | None
    requires_mgr_approval: bool
    is_active: bool


@dataclass
class UserOption:
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool


def _category_option_from(category: ItemCategory) -> CategoryOption:
    return CategoryOption(
        id=category.id,
        name=category.name,
        description=category.description,
        requires_mgr_approval=category.requires_mgr_approval,
        is_active=category.is_active,
    )


def _user_option_from(user: User) -> UserOption:
    return UserOption(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        manager_id=user.manager_id,
        is_active=user.is_active,
    )


class DropdownService:
    def __init__(
        self, item_category_repository: ItemCategoryRepository, user_repository: UserRepository
    ) -> None:
        self.item_category_repository = item_category_repository
        self.user_repository = user_repository

    async def list_item_categories(self) -> list[CategoryOption]:
        categories = await self.item_category_repository.list_active()
        return [_category_option_from(category) for category in categories]

    async def list_managers(self) -> list[UserOption]:
        users = await self.user_repository.list_active_by_role(UserRole.MANAGER)
        return [_user_option_from(user) for user in users]

    async def list_employees(self) -> list[UserOption]:
        users = await self.user_repository.list_active_by_role(UserRole.EMPLOYEE)
        return [_user_option_from(user) for user in users]
