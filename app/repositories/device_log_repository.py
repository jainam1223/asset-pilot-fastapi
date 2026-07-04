"""`device_log` table repository — reads over the append-only audit trail.

Writes go through `DeviceLogService.append`, which uses the inherited
`create()` from `SQLAlchemyRepository` (add + flush + refresh, no commit).
"""

import uuid

from sqlalchemy import select

from app.models.device_log import DeviceLog
from app.repositories.base import SQLAlchemyRepository
from app.utils.pagination import PaginationParams


class DeviceLogRepository(SQLAlchemyRepository[DeviceLog]):
    model = DeviceLog

    async def list_for_item(
        self,
        item_id: uuid.UUID,
        *,
        milestones_only: bool,
        pagination: PaginationParams | None = None,
    ) -> list[DeviceLog]:
        stmt = select(DeviceLog).where(DeviceLog.item_id == item_id)
        if milestones_only:
            stmt = stmt.where(DeviceLog.is_milestone.is_(True))
        stmt = stmt.order_by(DeviceLog.occurred_at.asc())

        if pagination is not None:
            stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
