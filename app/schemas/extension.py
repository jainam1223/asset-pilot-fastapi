"""Pydantic DTOs for extension-request review (API §9)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import (
    DeviceStatus,
    ExtensionStatus,
    MgrApprovalStatus,
    OwnerType,
    RequestStatus,
    UserRole,
)


class ExtensionRequestResponse(BaseModel):
    id: uuid.UUID
    original_request_id: uuid.UUID
    requester_id: uuid.UUID
    current_assigned_to: datetime
    extended_to: datetime
    status: ExtensionStatus
    requires_mgr_approval: bool
    manager_id: uuid.UUID | None
    mgr_approval_status: MgrApprovalStatus
    manager_note: str | None
    manager_decided_at: datetime | None
    it_decided_by: uuid.UUID | None
    it_note: str | None
    it_decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExtensionListEntryResponse(ExtensionRequestResponse):
    item_name: str
    requester_name: str


class ExtensionParentRequestResponse(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    category_id: uuid.UUID
    assigned_item_id: uuid.UUID | None
    assigned_from: datetime | None
    assigned_to: datetime | None
    status: RequestStatus


class ExtensionItemResponse(BaseModel):
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


class ExtensionRequesterResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool


class ExtensionDetailResponse(ExtensionRequestResponse):
    request: ExtensionParentRequestResponse
    item: ExtensionItemResponse
    requester: ExtensionRequesterResponse


class ExtensionDecisionRequest(BaseModel):
    it_note: str | None = None
