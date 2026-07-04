"""`/admin/handover-requests` — read-only IT audit view of peer-to-peer
device handovers (API §12). IT never approves handovers; GET only.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import HandoverServiceDep, require_it_admin
from app.models.enums import HandoverStatus
from app.schemas.handover import HandoverListItem
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["handovers"], dependencies=[Depends(require_it_admin)])


@router.get("/handover-requests")
async def list_handover_requests(
    handover_service: HandoverServiceDep,
    status: HandoverStatus | None = Query(default=None),
    item_id: uuid.UUID | None = Query(default=None),
) -> JSONResponse:
    results = await handover_service.list(status=status, item_id=item_id)
    data = [
        HandoverListItem.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Handover requests.")
