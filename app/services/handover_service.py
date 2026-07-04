"""Read-only IT audit view over peer-to-peer handovers (API §12). IT never
approves or mutates handovers — the workflow is employee-mobile-only.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.models.enums import HandoverStatus
from app.repositories.handover_request_repository import HandoverListRow, HandoverRequestRepository


@dataclass
class HandoverListResult:
    id: uuid.UUID
    item_id: uuid.UUID
    owner_id: uuid.UUID
    borrower_id: uuid.UUID
    requested_duration_hours: int | None
    status: HandoverStatus
    requested_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    item_name: str
    owner_name: str
    borrower_name: str


def _list_result_from(row: HandoverListRow) -> HandoverListResult:
    handover_request = row.handover_request
    return HandoverListResult(
        id=handover_request.id,
        item_id=handover_request.item_id,
        owner_id=handover_request.owner_id,
        borrower_id=handover_request.borrower_id,
        requested_duration_hours=handover_request.requested_duration_hours,
        status=handover_request.status,
        requested_at=handover_request.requested_at,
        decided_at=handover_request.decided_at,
        completed_at=handover_request.completed_at,
        note=handover_request.note,
        created_at=handover_request.created_at,
        updated_at=handover_request.updated_at,
        item_name=row.item_name,
        owner_name=row.owner_name,
        borrower_name=row.borrower_name,
    )


class HandoverService:
    def __init__(self, handover_request_repository: HandoverRequestRepository) -> None:
        self.handover_request_repository = handover_request_repository

    async def list(
        self, *, status: HandoverStatus | None, item_id: uuid.UUID | None
    ) -> list[HandoverListResult]:
        rows = await self.handover_request_repository.list_filtered(status=status, item_id=item_id)
        return [_list_result_from(row) for row in rows]
