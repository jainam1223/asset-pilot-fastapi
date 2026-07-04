"""`item` table — physical devices."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeviceStatus, OwnerType


class Item(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "item"
    __table_args__ = (
        Index("ix_item_status", "status"),
        Index("ix_item_category_id", "category_id"),
        Index("ix_item_current_owner_id", "current_owner_id"),
        Index("idx_item_available_by_category", "category_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_no: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item_category.id"), nullable=False
    )
    owner_type: Mapped[OwnerType] = mapped_column(
        SAEnum(
            OwnerType, name="owner_type", native_enum=True, values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
        default=OwnerType.COMPANY,
        server_default=OwnerType.COMPANY.value,
    )
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[DeviceStatus] = mapped_column(
        SAEnum(
            DeviceStatus,
            name="device_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=DeviceStatus.AVAILABLE,
        server_default=DeviceStatus.AVAILABLE.value,
    )
    current_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qr_code_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
