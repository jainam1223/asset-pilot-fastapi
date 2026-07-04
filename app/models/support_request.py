"""`support_request` table — update/damage/lost tickets filed against an item."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SupportResolution, SupportStatus, SupportType


class SupportRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "support_request"
    __table_args__ = (
        Index("ix_support_request_item_id", "item_id"),
        Index("ix_support_request_status", "status"),
        Index("ix_support_request_request_id", "request_id"),
        Index("idx_support_open_queue", "filed_at"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=True
    )
    type: Mapped[SupportType] = mapped_column(
        SAEnum(
            SupportType, name="support_type", native_enum=True, values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SupportStatus] = mapped_column(
        SAEnum(
            SupportStatus,
            name="support_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=SupportStatus.OPEN,
        server_default=SupportStatus.OPEN.value,
    )

    resolution: Mapped[SupportResolution | None] = mapped_column(
        SAEnum(
            SupportResolution,
            name="support_resolution",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    it_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    swapped_to_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item.id"), nullable=True
    )

    filed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
