"""Pydantic DTOs for the support queue (API §8)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.enums import DeviceStatus, SupportResolution, SupportStatus, SupportType
from app.schemas.item import ItemResponse
from app.schemas.user import UserResponse


class SupportRequestResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    requester_id: uuid.UUID
    request_id: uuid.UUID | None
    type: SupportType
    description: str
    status: SupportStatus
    resolution: SupportResolution | None
    it_note: str | None
    swapped_to_item_id: uuid.UUID | None
    filed_at: datetime
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    auto_closed: bool
    created_at: datetime
    updated_at: datetime


class SupportListEntryResponse(SupportRequestResponse):
    item_name: str
    requester_name: str


class SupportDetailResponse(SupportRequestResponse):
    item: ItemResponse
    requester: UserResponse


class ResolveSupportRequestRequest(BaseModel):
    resolution: SupportResolution
    it_note: str | None = None
    swapped_to_item_id: uuid.UUID | None = None
    old_item_next_status: DeviceStatus | None = None

    @model_validator(mode="after")
    def _swap_fields_required_for_swap(self) -> "ResolveSupportRequestRequest":
        if self.resolution == SupportResolution.SWAPPED and (
            self.swapped_to_item_id is None or self.old_item_next_status is None
        ):
            raise ValueError(
                "swapped_to_item_id and old_item_next_status are required when resolution is 'swapped'."
            )
        return self
