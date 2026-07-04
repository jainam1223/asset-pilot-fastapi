"""`/admin/requests` + `/admin/it/approvals` — request listing/detail and
the IT approval queue actions (API §2/§3).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import (
    AssignmentServiceDep,
    ITAdminUser,
    PaginationDep,
    RequestServiceDep,
    require_it_admin,
)
from app.models.enums import RequestPriority, RequestStatus
from app.schemas.assignment import AssignRequestRequest, BookingRangeRequest, SuggestedDeviceResponse
from app.schemas.request import (
    AssignedItemSummaryResponse,
    CancelRequestRequest,
    EscalateToManagerRequest,
    RejectRequestRequest,
    RequestDetailResponse,
    RequestListEntryResponse,
    RequestResponse,
)
from app.services.request_service import RequestDetail
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["requests"], dependencies=[Depends(require_it_admin)])


def _detail_response(detail: RequestDetail) -> RequestDetailResponse:
    return RequestDetailResponse(
        id=detail.id,
        requester_id=detail.requester_id,
        category_id=detail.category_id,
        assigned_item_id=detail.assigned_item_id,
        requested_from=detail.requested_from,
        requested_to=detail.requested_to,
        assigned_from=detail.assigned_from,
        assigned_to=detail.assigned_to,
        status=detail.status,
        priority=detail.priority,
        note=detail.note,
        requires_mgr_approval=detail.requires_mgr_approval,
        mgr_approval_status=detail.mgr_approval_status,
        manager_id=detail.manager_id,
        manager_decision_note=detail.manager_decision_note,
        manager_decided_at=detail.manager_decided_at,
        it_decided_by=detail.it_decided_by,
        it_decision_note=detail.it_decision_note,
        it_decided_at=detail.it_decided_at,
        rejected_by=detail.rejected_by,
        rejected_reason=detail.rejected_reason,
        cancelled_by=detail.cancelled_by,
        cancelled_at=detail.cancelled_at,
        is_wfh=detail.is_wfh,
        ship_tracking_url=detail.ship_tracking_url,
        ship_initiated_at=detail.ship_initiated_at,
        ship_completed_at=detail.ship_completed_at,
        return_tracking_url=detail.return_tracking_url,
        return_initiated_at=detail.return_initiated_at,
        completed_at=detail.completed_at,
        completed_by=detail.completed_by,
        completed_next_status=detail.completed_next_status,
        is_client_direct=detail.is_client_direct,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        category_name=detail.category_name,
        requester_name=detail.requester_name,
        manager_name=detail.manager_name,
        it_decided_by_name=detail.it_decided_by_name,
        cancelled_by_name=detail.cancelled_by_name,
        completed_by_name=detail.completed_by_name,
        item=(
            AssignedItemSummaryResponse.model_validate(detail.item, from_attributes=True)
            if detail.item is not None
            else None
        ),
    )


@router.get("/requests")
async def list_requests(
    request_service: RequestServiceDep,
    pagination: PaginationDep,
    status: RequestStatus | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    priority: RequestPriority | None = Query(default=None),
    requested_from: datetime | None = Query(default=None),
    requested_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None),
) -> JSONResponse:
    page = await request_service.list_requests(
        status=status,
        category_id=category_id,
        priority=priority,
        requested_from=requested_from,
        requested_to=requested_to,
        search=search,
        pagination=pagination,
    )
    data = [
        RequestListEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in page.items
    ]
    return success_response(data=data, message="Requests.", pagination=page.to_meta())


@router.get("/requests/{request_id}")
async def get_request_detail(request_id: uuid.UUID, request_service: RequestServiceDep) -> JSONResponse:
    detail = await request_service.get_detail(request_id)
    return success_response(data=_detail_response(detail).model_dump(mode="json"), message="Request detail.")


@router.get("/it/approvals")
async def list_it_approvals(request_service: RequestServiceDep, pagination: PaginationDep) -> JSONResponse:
    page = await request_service.list_it_approvals(pagination=pagination)
    data = [
        RequestListEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in page.items
    ]
    return success_response(data=data, message="IT approval queue.", pagination=page.to_meta())


@router.patch("/requests/{request_id}/reject")
async def reject_request(
    request_id: uuid.UUID,
    payload: RejectRequestRequest,
    current_user: ITAdminUser,
    request_service: RequestServiceDep,
) -> JSONResponse:
    result = await request_service.reject(
        request_id,
        rejected_reason=payload.rejected_reason,
        it_decision_note=payload.it_decision_note,
        actor_id=uuid.UUID(current_user.subject),
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Request rejected.")


@router.patch("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: uuid.UUID,
    payload: CancelRequestRequest,
    current_user: ITAdminUser,
    request_service: RequestServiceDep,
) -> JSONResponse:
    result = await request_service.cancel(
        request_id, rejected_reason=payload.rejected_reason, actor_id=uuid.UUID(current_user.subject)
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Request cancelled.")


@router.patch("/requests/{request_id}/escalate-to-manager")
async def escalate_to_manager(
    request_id: uuid.UUID, payload: EscalateToManagerRequest, request_service: RequestServiceDep
) -> JSONResponse:
    result = await request_service.escalate_to_manager(request_id, manager_id=payload.manager_id)
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Request escalated to manager.")


@router.get("/requests/{request_id}/suggested-devices")
async def get_suggested_devices(
    request_id: uuid.UUID, assignment_service: AssignmentServiceDep
) -> JSONResponse:
    results = await assignment_service.suggested_devices(request_id)
    data = [
        SuggestedDeviceResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Suggested devices.")


@router.patch("/requests/{request_id}/booking-range")
async def update_booking_range(
    request_id: uuid.UUID, payload: BookingRangeRequest, assignment_service: AssignmentServiceDep
) -> JSONResponse:
    result = await assignment_service.update_booking_range(
        request_id, assigned_from=payload.assigned_from, assigned_to=payload.assigned_to
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Booking range updated.")


@router.post("/requests/{request_id}/assign")
async def assign_device(
    request_id: uuid.UUID,
    payload: AssignRequestRequest,
    current_user: ITAdminUser,
    assignment_service: AssignmentServiceDep,
) -> JSONResponse:
    result = await assignment_service.assign(
        request_id,
        item_id=payload.item_id,
        assigned_from=payload.assigned_from,
        assigned_to=payload.assigned_to,
        is_wfh=payload.is_wfh,
        actor_id=uuid.UUID(current_user.subject),
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Device assigned.")
