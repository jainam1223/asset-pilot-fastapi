import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator

from app.models.enums import (
    DeviceStatus,
    HandoverStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
)
from app.schemas.auth import UserMeResponse

_CHANGEABLE_STATUSES = {
    DeviceStatus.AVAILABLE,
    DeviceStatus.UNDER_REPAIR,
    DeviceStatus.MAINTENANCE,
    DeviceStatus.LOST,
    DeviceStatus.RETIRED,
    DeviceStatus.RETURNED_TO_CLIENT,
}


class ItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    serial_no: str
    category_id: uuid.UUID
    owner_type: OwnerType
    client_name: str | None
    status: DeviceStatus
    current_owner_id: uuid.UUID | None
    purchase_date: date | None
    qr_code_token: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ItemListEntryResponse(ItemResponse):
    category_name: str
    current_owner_name: str | None


class CreateItemRequest(BaseModel):
    name: str
    serial_no: str
    category_id: uuid.UUID
    owner_type: OwnerType
    client_name: str | None = None
    purchase_date: date | None = None

    @model_validator(mode="after")
    def _client_name_required_for_client_owner(self) -> "CreateItemRequest":
        if self.owner_type == OwnerType.CLIENT and not self.client_name:
            raise ValueError("client_name is required when owner_type is 'client'.")
        return self


class UpdateItemRequest(BaseModel):
    name: str | None = None
    category_id: uuid.UUID | None = None
    client_name: str | None = None
    purchase_date: date | None = None

    @model_validator(mode="after")
    def _no_explicit_null_for_required_fields(self) -> "UpdateItemRequest":
        for field in ("name", "category_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ChangeItemStatusRequest(BaseModel):
    status: DeviceStatus
    it_note: str | None = None

    @model_validator(mode="after")
    def _status_must_be_changeable(self) -> "ChangeItemStatusRequest":
        if self.status not in _CHANGEABLE_STATUSES:
            raise ValueError(
                f"status '{self.status.value}' cannot be set directly; "
                "it is only set by the assignment/shipping lifecycle."
            )
        return self


class ItemCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    requires_mgr_approval: bool
    is_active: bool


class RequestSummaryResponse(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    category_id: uuid.UUID
    assigned_item_id: uuid.UUID | None
    requested_from: datetime
    requested_to: datetime
    assigned_from: datetime | None
    assigned_to: datetime | None
    status: RequestStatus
    priority: RequestPriority
    note: str | None
    requires_mgr_approval: bool
    mgr_approval_status: MgrApprovalStatus
    manager_id: uuid.UUID | None
    manager_decision_note: str | None
    manager_decided_at: datetime | None
    it_decided_by: uuid.UUID | None
    it_decision_note: str | None
    it_decided_at: datetime | None
    rejected_by: RejectedByEnum | None
    rejected_reason: str | None
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None
    is_wfh: bool
    ship_tracking_url: str | None
    ship_initiated_at: datetime | None
    ship_completed_at: datetime | None
    return_tracking_url: str | None
    return_initiated_at: datetime | None
    completed_at: datetime | None
    completed_by: uuid.UUID | None
    completed_next_status: DeviceStatus | None
    is_client_direct: bool
    created_at: datetime
    updated_at: datetime


class SupportRequestSummaryResponse(BaseModel):
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


class HandoverSummaryResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    owner_id: uuid.UUID
    borrower_id: uuid.UUID
    requested_duration_hours: int | None
    status: HandoverStatus
    requested_at: datetime
    decided_at: datetime | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class ItemDetailResponse(BaseModel):
    item: ItemResponse
    category: ItemCategoryResponse
    current_owner: UserMeResponse | None
    current_request: RequestSummaryResponse | None
    open_support: list[SupportRequestSummaryResponse]
    active_handover: HandoverSummaryResponse | None
