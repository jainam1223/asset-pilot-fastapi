"""`user` table repository."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.models.enums import RequestStatus, UserRole
from app.models.item import Item
from app.models.request import Request
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository
from app.utils.pagination import Page, PaginationParams

_NON_TERMINAL_REQUEST_STATUSES = (
    RequestStatus.REQUESTED,
    RequestStatus.PENDING_MGR_APPROVAL,
    RequestStatus.PENDING_IT_APPROVAL,
    RequestStatus.ASSIGNED,
)


@dataclass
class UserListRow:
    user: User
    manager_name: str | None


class UserRepository(SQLAlchemyRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_by_role(self, role: UserRole) -> list[User]:
        stmt = select(User).where(User.role == role, User.is_active.is_(True)).order_by(User.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_users(
        self,
        *,
        role: UserRole | None,
        is_active: bool | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[UserListRow]:
        manager = aliased(User)
        base_stmt = select(User, manager.name).outerjoin(manager, User.manager_id == manager.id)
        if role is not None:
            base_stmt = base_stmt.where(User.role == role)
        if is_active is not None:
            base_stmt = base_stmt.where(User.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            base_stmt = base_stmt.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one()

        stmt = base_stmt.order_by(User.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        rows = [UserListRow(user=user, manager_name=manager_name) for user, manager_name in result.all()]
        return Page(items=rows, total_items=total_items, page=pagination.page, page_size=pagination.page_size)

    async def has_active_devices_or_requests(self, user_id: uuid.UUID) -> bool:
        device_stmt = select(Item.id).where(Item.current_owner_id == user_id).limit(1)
        if (await self.session.execute(device_stmt)).first() is not None:
            return True

        request_stmt = (
            select(Request.id)
            .where(
                Request.requester_id == user_id,
                Request.status.in_(_NON_TERMINAL_REQUEST_STATUSES),
            )
            .limit(1)
        )
        return (await self.session.execute(request_stmt)).first() is not None
