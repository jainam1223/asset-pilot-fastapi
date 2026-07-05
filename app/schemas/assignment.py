"""Pydantic DTOs for the assignment engine (API §4/§5): suggested devices,
booking calendar, booking-range adjustment, assign, and client direct-assign.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.item import ItemResponse
from app.schemas.request import RequestResponse


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC so mixed naive/aware input can't crash comparison."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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

    _normalize_tz = field_validator("assigned_from", "assigned_to")(_as_utc)

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

    _normalize_tz = field_validator("assigned_from", "assigned_to")(_as_utc)

    @model_validator(mode="after")
    def _from_before_to(self) -> "AssignRequestRequest":
        if self.assigned_from >= self.assigned_to:
            raise ValueError("assigned_from must be before assigned_to.")
        return self


class DirectAssignRequest(BaseModel):
    employee_id: uuid.UUID
    assigned_from: datetime
    assigned_to: datetime

    _normalize_tz = field_validator("assigned_from", "assigned_to")(_as_utc)

    @model_validator(mode="after")
    def _from_before_to(self) -> "DirectAssignRequest":
        if self.assigned_from >= self.assigned_to:
            raise ValueError("assigned_from must be before assigned_to.")
        return self
