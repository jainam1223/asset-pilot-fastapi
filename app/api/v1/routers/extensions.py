"""`/admin/extension-requests` — IT review of assignment end-date
extensions: list/detail, approve, reject (API §9).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import ExtensionServiceDep, ITAdminUser, require_it_admin
from app.models.enums import ExtensionStatus
from app.schemas.extension import (
    ExtensionDecisionRequest,
    ExtensionDetailResponse,
    ExtensionListEntryResponse,
    ExtensionRequestResponse,
)
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["extension-requests"], dependencies=[Depends(require_it_admin)])


@router.get("/extension-requests")
async def list_extension_requests(
    extension_service: ExtensionServiceDep,
    status: ExtensionStatus | None = Query(default=None),
) -> JSONResponse:
    results = await extension_service.list_extension_requests(status=status)
    data = [
        ExtensionListEntryResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Extension requests.")


@router.get("/extension-requests/{extension_request_id}")
async def get_extension_request_detail(
    extension_request_id: uuid.UUID, extension_service: ExtensionServiceDep
) -> JSONResponse:
    result = await extension_service.get_detail(extension_request_id)
    schema = ExtensionDetailResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Extension request detail.")


@router.patch("/extension-requests/{extension_request_id}/approve")
async def approve_extension_request(
    extension_request_id: uuid.UUID,
    payload: ExtensionDecisionRequest,
    current_user: ITAdminUser,
    extension_service: ExtensionServiceDep,
) -> JSONResponse:
    result = await extension_service.approve(
        extension_request_id, it_note=payload.it_note, actor_id=uuid.UUID(current_user.subject)
    )
    schema = ExtensionRequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Extension request approved.")


@router.patch("/extension-requests/{extension_request_id}/reject")
async def reject_extension_request(
    extension_request_id: uuid.UUID,
    payload: ExtensionDecisionRequest,
    current_user: ITAdminUser,
    extension_service: ExtensionServiceDep,
) -> JSONResponse:
    result = await extension_service.reject(
        extension_request_id, it_note=payload.it_note, actor_id=uuid.UUID(current_user.subject)
    )
    schema = ExtensionRequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Extension request rejected.")
