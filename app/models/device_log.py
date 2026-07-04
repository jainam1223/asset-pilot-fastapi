"""`device_log` table — permanent, append-only per-device audit trail.

Append-only is enforced in Postgres via RULES (`device_log_no_update`,
`device_log_no_delete`) added by hand in the M1 migration — UPDATE/DELETE
statements against this table are silently turned into no-ops.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ActorRole, DeviceLogEvent


class DeviceLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "device_log"
    # NOTE: the partial index `idx_device_log_milestones`
    # (WHERE is_milestone = true) is hand-added directly in the Alembic
    # migration, not here.
    __table_args__ = (
        Index("idx_device_log_item_time", "item_id", "occurred_at"),
        Index("ix_device_log_request_id", "request_id"),
        Index("ix_device_log_event_type", "event_type"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id"), nullable=False)
    event_type: Mapped[DeviceLogEvent] = mapped_column(
        SAEnum(
            DeviceLogEvent,
            name="device_log_event",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    actor_role: Mapped[ActorRole] = mapped_column(
        SAEnum(
            ActorRole, name="actor_role", native_enum=True, values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=True
    )
    support_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_request.id"), nullable=True
    )
    extension_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extension_request.id"), nullable=True
    )
    handover_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("handover_request.id"), nullable=True
    )
    from_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # `metadata` is reserved by SQLAlchemy's declarative base; map the
    # `metadata` DB column onto a differently-named Python attribute.
    log_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
