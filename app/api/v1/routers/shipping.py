"""`/admin/shipping` + `/admin/requests/{id}/ship|confirm-delivery|complete-return`
— WFH outbound shipping and returns (API §10/§11).
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import ITAdminUser, ShippingServiceDep, require_it_admin
from app.schemas.request import RequestResponse
from app.schemas.shipping import CompleteReturnRequest, ShippingQueueEntryResponse, ShipRequestRequest
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["shipping"], dependencies=[Depends(require_it_admin)])


@router.get("/shipping/outbound")
async def list_outbound_shipping_queue(shipping_service: ShippingServiceDep) -> JSONResponse:
    results = await shipping_service.list_outbound()
    data = [
        ShippingQueueEntryResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="Outbound shipping queue.")


@router.get("/shipping/returns")
async def list_return_shipping_queue(shipping_service: ShippingServiceDep) -> JSONResponse:
    results = await shipping_service.list_returns()
    data = [
        ShippingQueueEntryResponse.model_validate(result, from_attributes=True).model_dump(mode="json")
        for result in results
    ]
    return success_response(data=data, message="WFH return queue.")


@router.post("/requests/{request_id}/ship")
async def ship_request(
    request_id: uuid.UUID,
    payload: ShipRequestRequest,
    current_user: ITAdminUser,
    shipping_service: ShippingServiceDep,
) -> JSONResponse:
    result = await shipping_service.ship(
        request_id, ship_tracking_url=payload.ship_tracking_url, actor_id=uuid.UUID(current_user.subject)
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Device marked shipped.")


@router.post("/requests/{request_id}/confirm-delivery")
async def confirm_delivery(
    request_id: uuid.UUID, current_user: ITAdminUser, shipping_service: ShippingServiceDep
) -> JSONResponse:
    result = await shipping_service.confirm_delivery(
        request_id, actor_id=uuid.UUID(current_user.subject)
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Delivery confirmed.")


@router.post("/requests/{request_id}/complete-return")
async def complete_return(
    request_id: uuid.UUID,
    payload: CompleteReturnRequest,
    current_user: ITAdminUser,
    shipping_service: ShippingServiceDep,
) -> JSONResponse:
    result = await shipping_service.complete_return(
        request_id, next_status=payload.next_status, actor_id=uuid.UUID(current_user.subject)
    )
    schema = RequestResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Return completed.")
