"""`/admin/support-requests` — the support queue: list/detail, start,
and resolve (API §8).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import ITAdminUser, SupportServiceDep, require_it_admin
from app.models.enums import SupportStatus, SupportType
from app.schemas.support import (
    ResolveSupportRequestRequest,
    SupportDetailResponse,
    SupportListEntryResponse,
    SupportRequestResponse,
)
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["support-requests"], dependencies=[Depends(require_it_admin)])


@router.get("/support-requests")
async def list_support_requests(
    support_service: SupportServiceDep,
    status: SupportStatus | None = Query(default=None),
    type: SupportType | None = Query(default=None),
    item_id: uuid.UUID | None = Query(default=None),
) -> JSONResponse:
    results = await support_service.list_support_requests(status=status, type_=type, item_id=item_id)
    data = [
        SupportListEntryResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Support requests.")


@router.get("/support-requests/{support_request_id}")
async def get_support_request_detail(
    support_request_id: uuid.UUID, support_service: SupportServiceDep
) -> JSONResponse:
    result = await support_service.get_detail(support_request_id)
    schema = SupportDetailResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Support request detail.")


@router.patch("/support-requests/{support_request_id}/start")
async def start_support_request(
    support_request_id: uuid.UUID, current_user: ITAdminUser, support_service: SupportServiceDep
) -> JSONResponse:
    result = await support_service.start(support_request_id, actor_id=uuid.UUID(current_user.subject))
    schema = SupportRequestResponse.model_validate(result, from_attributes=True)
    return success_response(
        data=schema.model_dump(mode="json"), message="Support request marked in progress."
    )


@router.patch("/support-requests/{support_request_id}/resolve")
async def resolve_support_request(
    support_request_id: uuid.UUID,
    payload: ResolveSupportRequestRequest,
    current_user: ITAdminUser,
    support_service: SupportServiceDep,
) -> JSONResponse:
    result = await support_service.resolve(
        support_request_id,
        resolution=payload.resolution,
        it_note=payload.it_note,
        swapped_to_item_id=payload.swapped_to_item_id,
        old_item_next_status=payload.old_item_next_status,
        actor_id=uuid.UUID(current_user.subject),
    )
    schema = SupportRequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Support request resolved.")
