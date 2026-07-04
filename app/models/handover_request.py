"""`handover_request` table — peer-to-peer device loan workflow."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import HandoverStatus


class HandoverRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "handover_request"
    # NOTE: the partial UNIQUE index `uq_one_active_handover_per_item`
    # (WHERE status = 'accepted') is hand-added directly in the Alembic
    # migration, not here.
    __table_args__ = (
        Index("ix_handover_request_item_id", "item_id"),
        Index("ix_handover_request_borrower_id", "borrower_id"),
        Index("ix_handover_request_owner_id", "owner_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    borrower_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    requested_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[HandoverStatus] = mapped_column(
        SAEnum(
            HandoverStatus,
            name="handover_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=HandoverStatus.REQUESTED,
        server_default=HandoverStatus.REQUESTED.value,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
