"""`extension_request` table — employee-filed extensions to an active request."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExtensionStatus, MgrApprovalStatus


class ExtensionRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extension_request"

    original_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    current_assigned_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extended_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ExtensionStatus] = mapped_column(
        SAEnum(
            ExtensionStatus,
            name="extension_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ExtensionStatus.PENDING,
        server_default=ExtensionStatus.PENDING.value,
    )

    requires_mgr_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    mgr_approval_status: Mapped[MgrApprovalStatus] = mapped_column(
        SAEnum(
            MgrApprovalStatus,
            name="mgr_approval_status",
            native_enum=True,
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=MgrApprovalStatus.NOT_REQUIRED,
        server_default=MgrApprovalStatus.NOT_REQUIRED.value,
    )
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    it_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    it_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    it_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
