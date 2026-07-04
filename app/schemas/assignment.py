"""Pydantic DTOs for the assignment engine (API §4/§5): suggested devices,
booking calendar, booking-range adjustment, assign, and client direct-assign.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.schemas.item import ItemResponse
from app.schemas.request import RequestResponse


class SuggestedDeviceResponse(ItemResponse):
    category_name: str
    active_bookings_count: int


class ClientAvailableResponse(ItemResponse):
    category_name: str


class BookingResponse(RequestResponse):
    requester_name: str


class BookingRangeRequest(BaseModel):
    assigned_from: datetime
    assigned_to: datetime

    @model_validator(mode="after")
    def _from_before_to(self) -> "BookingRangeRequest":
        if self.assigned_from >= self.assigned_to:
            raise ValueError("assigned_from must be before assigned_to.")
        return self


class AssignRequestRequest(BaseModel):
    item_id: uuid.UUID
    assigned_from: datetime
    assigned_to: datetime
    is_wfh: bool = False

    @model_validator(mode="after")
    def _from_before_to(self) -> "AssignRequestRequest":
        if self.assigned_from >= self.assigned_to:
            raise ValueError("assigned_from must be before assigned_to.")
        return self


class DirectAssignRequest(BaseModel):
    employee_id: uuid.UUID
    assigned_from: datetime
    assigned_to: datetime

    @model_validator(mode="after")
    def _from_before_to(self) -> "DirectAssignRequest":
        if self.assigned_from >= self.assigned_to:
            raise ValueError("assigned_from must be before assigned_to.")
        return self
