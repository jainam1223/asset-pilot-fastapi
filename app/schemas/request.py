import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import (
    DeviceStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
)


class RequestResponse(BaseModel):
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


class RequestListEntryResponse(RequestResponse):
    category_name: str
    requester_name: str


class AssignedItemSummaryResponse(BaseModel):
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


class RequestDetailResponse(RequestResponse):
    category_name: str
    requester_name: str
    manager_name: str | None
    it_decided_by_name: str | None
    cancelled_by_name: str | None
    completed_by_name: str | None
    item: AssignedItemSummaryResponse | None


class RejectRequestRequest(BaseModel):
    rejected_reason: str
    it_decision_note: str | None = None


class CancelRequestRequest(BaseModel):
    rejected_reason: str


class EscalateToManagerRequest(BaseModel):
    manager_id: uuid.UUID | None = None
