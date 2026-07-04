"""Python enums for every Postgres enum type in the ITAM schema.

Mapped onto columns via SQLAlchemy `Enum(..., name="...")` so the DB enum
type name matches `_docs/db_schemas.dbml` exactly.
"""

import enum


class UserRole(enum.StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    IT_ADMIN = "it_admin"


class DeviceStatus(enum.StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    SHIPPING_PENDING = "shipping_pending"
    RETURN_SHIPPING_PENDING = "return_shipping_pending"
    UNDER_REPAIR = "under_repair"
    MAINTENANCE = "maintenance"
    LOST = "lost"
    RETIRED = "retired"
    RETURNED_TO_CLIENT = "returned_to_client"


class RequestStatus(enum.StrEnum):
    REQUESTED = "requested"
    PENDING_MGR_APPROVAL = "pending_mgr_approval"
    PENDING_IT_APPROVAL = "pending_it_approval"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class MgrApprovalStatus(enum.StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RejectedByEnum(enum.StrEnum):
    MANAGER = "manager"
    IT_ADMIN = "it_admin"
    IT_ADMIN_CANCEL = "it_admin_cancel"


class RequestPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OwnerType(enum.StrEnum):
    COMPANY = "company"
    CLIENT = "client"


class SupportType(enum.StrEnum):
    UPDATE = "update"
    DAMAGE = "damage"
    LOST = "lost"


class SupportStatus(enum.StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class SupportResolution(enum.StrEnum):
    REMOTE_RESOLVED = "remote_resolved"
    REPAIRED_IN_PLACE = "repaired_in_place"
    SWAPPED = "swapped"
    MARKED_LOST = "marked_lost"


class ExtensionStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HandoverStatus(enum.StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class DeviceLogEvent(enum.StrEnum):
    DEVICE_CREATED = "device_created"
    DEVICE_EDITED = "device_edited"
    ASSIGNED = "assigned"
    CLIENT_ASSIGNED = "client_assigned"
    SHIP_OUTBOUND_INITIATED = "ship_outbound_initiated"
    SHIP_OUTBOUND_COMPLETED = "ship_outbound_completed"
    RETURN_SHIP_INITIATED = "return_ship_initiated"
    RETURN_RECEIVED = "return_received"
    ASSIGNMENT_COMPLETED = "assignment_completed"
    STATUS_CHANGED = "status_changed"
    SUPPORT_OPENED = "support_opened"
    SUPPORT_RESOLVED = "support_resolved"
    SUPPORT_AUTO_CLOSED = "support_auto_closed"
    EXTENSION_REQUESTED = "extension_requested"
    EXTENSION_APPROVED = "extension_approved"
    EXTENSION_REJECTED = "extension_rejected"
    HANDOVER_REQUESTED = "handover_requested"
    HANDOVER_ACCEPTED = "handover_accepted"
    HANDOVER_REJECTED = "handover_rejected"
    HANDOVER_CANCELLED = "handover_cancelled"
    HANDOVER_COMPLETED = "handover_completed"
    MARKED_LOST = "marked_lost"
    RETIRED = "retired"
    RETURNED_TO_CLIENT = "returned_to_client"
    SWAPPED_OUT = "swapped_out"
    SWAPPED_IN = "swapped_in"


class ActorRole(enum.StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    IT_ADMIN = "it_admin"
    SYSTEM = "system"
