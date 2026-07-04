"""Pydantic DTOs for the admin dashboard KPI endpoints (API §1).

`recent-requests` and `open-support` reuse the existing list-entry schemas
from their own domains (`RequestListEntryResponse`, `SupportListEntryResponse`)
since the response shape is identical.
"""

from pydantic import BaseModel


class StatusBreakdownResponse(BaseModel):
    available: int
    assigned: int
    under_repair: int
    maintenance: int
    shipping_pending: int
    return_shipping_pending: int
    lost: int
    retired: int


class DashboardSummaryResponse(BaseModel):
    status_breakdown: StatusBreakdownResponse
    pending_requests_count: int
    open_support_count: int
    active_handovers_count: int
    pending_extensions_count: int
