"""`/admin/dropdowns` — shared dropdown data for IT-Admin forms (API §14)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import DropdownServiceDep, require_it_admin
from app.schemas.auth import UserMeResponse
from app.schemas.item import ItemCategoryResponse
from app.utils.response import success_response

router = APIRouter(prefix="/admin/dropdowns", tags=["dropdowns"], dependencies=[Depends(require_it_admin)])


@router.get("/item-categories")
async def list_item_category_dropdown(dropdown_service: DropdownServiceDep) -> JSONResponse:
    categories = await dropdown_service.list_item_categories()
    data = [
        ItemCategoryResponse.model_validate(category, from_attributes=True).model_dump(mode="json")
        for category in categories
    ]
    return success_response(data=data, message="Item categories.")


@router.get("/managers")
async def list_manager_dropdown(dropdown_service: DropdownServiceDep) -> JSONResponse:
    managers = await dropdown_service.list_managers()
    data = [
        UserMeResponse.model_validate(manager, from_attributes=True).model_dump(mode="json")
        for manager in managers
    ]
    return success_response(data=data, message="Managers.")


@router.get("/employees")
async def list_employee_dropdown(dropdown_service: DropdownServiceDep) -> JSONResponse:
    employees = await dropdown_service.list_employees()
    data = [
        UserMeResponse.model_validate(employee, from_attributes=True).model_dump(mode="json")
        for employee in employees
    ]
    return success_response(data=data, message="Employees.")
