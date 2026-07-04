"""`/admin/items` — inventory CRUD, status changes, device detail & audit
timeline (API §6/§7).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import (
    AssignmentServiceDep,
    DeviceLogServiceDep,
    InventoryServiceDep,
    ITAdminUser,
    PaginationDep,
    require_it_admin,
)
from app.models.enums import DeviceStatus, OwnerType
from app.schemas.assignment import BookingResponse, ClientAvailableResponse, DirectAssignRequest
from app.schemas.auth import UserMeResponse
from app.schemas.device_log import DeviceLogEntryResponse
from app.schemas.item import (
    ChangeItemStatusRequest,
    CreateItemRequest,
    HandoverSummaryResponse,
    ItemCategoryResponse,
    ItemDetailResponse,
    ItemListEntryResponse,
    ItemResponse,
    RequestSummaryResponse,
    SupportRequestSummaryResponse,
    UpdateItemRequest,
)
from app.schemas.request import RequestResponse
from app.services.inventory_service import ItemDetail
from app.utils.response import success_response

router = APIRouter(prefix="/admin/items", tags=["items"], dependencies=[Depends(require_it_admin)])


def _item_detail_response(detail: ItemDetail) -> ItemDetailResponse:
    return ItemDetailResponse(
        item=ItemResponse.model_validate(detail.item, from_attributes=True),
        category=ItemCategoryResponse.model_validate(detail.category, from_attributes=True),
        current_owner=(
            UserMeResponse.model_validate(detail.current_owner, from_attributes=True)
            if detail.current_owner is not None
            else None
        ),
        current_request=(
            RequestSummaryResponse.model_validate(detail.current_request, from_attributes=True)
            if detail.current_request is not None
            else None
        ),
        open_support=[
            SupportRequestSummaryResponse.model_validate(support, from_attributes=True)
            for support in detail.open_support
        ],
        active_handover=(
            HandoverSummaryResponse.model_validate(detail.active_handover, from_attributes=True)
            if detail.active_handover is not None
            else None
        ),
    )


@router.get("")
async def list_items(
    inventory_service: InventoryServiceDep,
    pagination: PaginationDep,
    category_id: uuid.UUID | None = Query(default=None),
    status: DeviceStatus | None = Query(default=None),
    owner_type: OwnerType | None = Query(default=None),
    search: str | None = Query(default=None),
) -> JSONResponse:
    page = await inventory_service.list_items(
        category_id=category_id,
        status=status,
        owner_type=owner_type,
        search=search,
        pagination=pagination,
    )
    data = [
        ItemListEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in page.items
    ]
    return success_response(data=data, message="Device inventory.", pagination=page.to_meta())


@router.post("", status_code=201)
async def create_item(
    payload: CreateItemRequest, current_user: ITAdminUser, inventory_service: InventoryServiceDep
) -> JSONResponse:
    result = await inventory_service.create_item(
        name=payload.name,
        serial_no=payload.serial_no,
        category_id=payload.category_id,
        owner_type=payload.owner_type,
        client_name=payload.client_name,
        purchase_date=payload.purchase_date,
        actor_id=uuid.UUID(current_user.subject),
    )
    schema = ItemResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), status_code=201, message="Device created.")


@router.get("/client-available")
async def list_client_available(
    assignment_service: AssignmentServiceDep,
    category_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
) -> JSONResponse:
    results = await assignment_service.client_available(category_id=category_id, search=search)
    data = [
        ClientAvailableResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Available client-owned devices.")


@router.patch("/{item_id}")
async def edit_item(
    item_id: uuid.UUID,
    payload: UpdateItemRequest,
    current_user: ITAdminUser,
    inventory_service: InventoryServiceDep,
) -> JSONResponse:
    result = await inventory_service.edit_item(
        item_id, updates=payload.model_dump(exclude_unset=True), actor_id=uuid.UUID(current_user.subject)
    )
    schema = ItemResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Device updated.")


@router.patch("/{item_id}/status")
async def change_item_status(
    item_id: uuid.UUID,
    payload: ChangeItemStatusRequest,
    current_user: ITAdminUser,
    inventory_service: InventoryServiceDep,
) -> JSONResponse:
    result = await inventory_service.change_status(
        item_id, status=payload.status, it_note=payload.it_note, actor_id=uuid.UUID(current_user.subject)
    )
    schema = ItemResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Device status updated.")


@router.get("/{item_id}")
async def get_item_detail(item_id: uuid.UUID, inventory_service: InventoryServiceDep) -> JSONResponse:
    detail = await inventory_service.get_detail(item_id)
    return success_response(
        data=_item_detail_response(detail).model_dump(mode="json"), message="Device detail."
    )


@router.get("/{item_id}/timeline")
async def get_item_timeline(
    item_id: uuid.UUID,
    device_log_service: DeviceLogServiceDep,
    milestones_only: bool = Query(default=True),
) -> JSONResponse:
    entries = await device_log_service.get_timeline(item_id, milestones_only=milestones_only)
    data = [
        DeviceLogEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in entries
    ]
    return success_response(data=data, message="Device timeline.")


@router.get("/{item_id}/bookings")
async def get_item_bookings(item_id: uuid.UUID, assignment_service: AssignmentServiceDep) -> JSONResponse:
    results = await assignment_service.item_bookings(item_id)
    data = [
        BookingResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Device booking calendar.")


@router.post("/{item_id}/direct-assign")
async def direct_assign_item(
    item_id: uuid.UUID,
    payload: DirectAssignRequest,
    current_user: ITAdminUser,
    assignment_service: AssignmentServiceDep,
) -> JSONResponse:
    result = await assignment_service.direct_assign(
        item_id,
        employee_id=payload.employee_id,
        assigned_from=payload.assigned_from,
        assigned_to=payload.assigned_to,
        actor_id=uuid.UUID(current_user.subject),
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(
        data=schema.model_dump(mode="json"), status_code=201, message="Device directly assigned."
    )
