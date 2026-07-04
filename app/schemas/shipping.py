"""Pydantic DTOs for WFH shipping/returns (API §10/§11)."""

from pydantic import BaseModel, field_validator

from app.models.enums import DeviceStatus
from app.schemas.request import RequestResponse

_ALLOWED_NEXT_STATUSES = (DeviceStatus.AVAILABLE, DeviceStatus.UNDER_REPAIR, DeviceStatus.RETIRED)


class ShipRequestRequest(BaseModel):
    ship_tracking_url: str


class CompleteReturnRequest(BaseModel):
    next_status: DeviceStatus

    @field_validator("next_status")
    @classmethod
    def _validate_next_status(cls, value: DeviceStatus) -> DeviceStatus:
        if value not in _ALLOWED_NEXT_STATUSES:
            raise ValueError("next_status must be one of: available, under_repair, retired.")
        return value


class ShippingQueueEntryResponse(RequestResponse):
    item_name: str
    requester_name: str
