"""`request` table — employee device requests through IT approval/assignment."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    DeviceStatus,
    MgrApprovalStatus,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
)


class Request(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "request"
    # NOTE: the partial UNIQUE index `uq_one_active_request_per_item`
    # (WHERE status NOT IN ('rejected', 'completed', 'cancelled')) is
    # hand-added directly in the Alembic migration, not here — autogenerate
    # handles plain indexes but the partial-unique DDL is authored by hand.
    __table_args__ = (
        Index("ix_request_requester_id", "requester_id"),
        Index("ix_request_status", "status"),
        Index("ix_request_assigned_item_id", "assigned_item_id"),
        Index("ix_request_category_id", "category_id"),
        Index("idx_request_it_queue", "priority", "created_at"),
        Index("idx_request_date_range", "assigned_item_id", "assigned_from", "assigned_to"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item_category.id"), nullable=False
    )
    assigned_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item.id"), nullable=True
    )

    requested_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(
            RequestStatus,
            name="request_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=RequestStatus.REQUESTED,
        server_default=RequestStatus.REQUESTED.value,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        SAEnum(
            RequestPriority,
            name="request_priority",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=RequestPriority.MEDIUM,
        server_default=RequestPriority.MEDIUM.value,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    requires_mgr_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    mgr_approval_status: Mapped[MgrApprovalStatus] = mapped_column(
        SAEnum(
            MgrApprovalStatus,
            name="mgr_approval_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=MgrApprovalStatus.NOT_REQUIRED,
        server_default=MgrApprovalStatus.NOT_REQUIRED.value,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    manager_decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    it_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    it_decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    it_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rejected_by: Mapped[RejectedByEnum | None] = mapped_column(
        SAEnum(
            RejectedByEnum,
            name="rejected_by_enum",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_wfh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    ship_tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ship_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    completed_next_status: Mapped[DeviceStatus | None] = mapped_column(
        SAEnum(
            DeviceStatus,
            name="device_status",
            native_enum=True,
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )

    is_client_direct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
