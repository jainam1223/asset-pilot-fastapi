"""Import every model so `Base.metadata` is fully populated for Alembic
autogenerate and so SQLAlchemy can resolve relationships/FKs by table name.
"""

from app.models.device_log import DeviceLog
from app.models.extension_request import ExtensionRequest
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User

__all__ = [
    "DeviceLog",
    "ExtensionRequest",
    "HandoverRequest",
    "Item",
    "ItemCategory",
    "Request",
    "SupportRequest",
    "User",
]
