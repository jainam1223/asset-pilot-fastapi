"""Pydantic DTOs for extension-request review (API §9)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ExtensionStatus, MgrApprovalStatus
from app.schemas.item import ItemResponse
from app.schemas.request import RequestResponse
from app.schemas.user import UserResponse


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


class ExtensionDetailResponse(ExtensionRequestResponse):
    request: RequestResponse
    item: ItemResponse
    requester: UserResponse


class ExtensionDecisionRequest(BaseModel):
    it_note: str | None = None
