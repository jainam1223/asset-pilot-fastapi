"""`/admin/dashboard` — KPI aggregates for the admin landing screen (API §1)."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import DashboardServiceDep, require_it_admin
from app.schemas.dashboard import DashboardSummaryResponse
from app.schemas.request import RequestListEntryResponse
from app.schemas.support import SupportListEntryResponse
from app.utils.response import success_response

router = APIRouter(prefix="/admin/dashboard", tags=["dashboard"], dependencies=[Depends(require_it_admin)])


@router.get("/summary")
async def get_summary(dashboard_service: DashboardServiceDep) -> JSONResponse:
    summary = await dashboard_service.get_summary()
    schema = DashboardSummaryResponse.model_validate(summary, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="Dashboard summary.")


@router.get("/recent-requests")
async def get_recent_requests(
    dashboard_service: DashboardServiceDep, limit: int = Query(default=10, ge=1)
) -> JSONResponse:
    entries = await dashboard_service.get_recent_requests(limit=limit)
    data = [
        RequestListEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in entries
    ]
    return success_response(data=data, message="Recent requests.")


@router.get("/open-support")
async def get_open_support(
    dashboard_service: DashboardServiceDep, limit: int = Query(default=10, ge=1)
) -> JSONResponse:
    entries = await dashboard_service.get_open_support(limit=limit)
    data = [
        SupportListEntryResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in entries
    ]
    return success_response(data=data, message="Open support requests.")
