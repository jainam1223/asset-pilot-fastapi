"""`/admin/users` — IT-Admin user administration (API §13)."""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import PaginationDep, UserServiceDep, require_it_admin
from app.models.enums import UserRole
from app.schemas.user import ChangeRoleRequest, CreateUserRequest, UserListItemResponse, UserResponse
from app.utils.response import success_response

router = APIRouter(prefix="/admin/users", tags=["users"], dependencies=[Depends(require_it_admin)])


@router.get("")
async def list_users(
    user_service: UserServiceDep,
    pagination: PaginationDep,
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> JSONResponse:
    page = await user_service.list_users(role=role, is_active=is_active, search=search, pagination=pagination)
    data = [
        UserListItemResponse.model_validate(entry, from_attributes=True).model_dump(mode="json")
        for entry in page.items
    ]
    return success_response(data=data, message="Users.", pagination=page.to_meta())


@router.post("", status_code=201)
async def create_user(payload: CreateUserRequest, user_service: UserServiceDep) -> JSONResponse:
    result = await user_service.create_user(name=payload.name, email=payload.email, role=payload.role)
    schema = UserResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), status_code=201, message="User created.")


@router.patch("/{user_id}/role")
async def change_role(
    user_id: uuid.UUID, payload: ChangeRoleRequest, user_service: UserServiceDep
) -> JSONResponse:
    result = await user_service.change_role(user_id, role=payload.role)
    schema = UserResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="User role updated.")


@router.patch("/{user_id}/deactivate")
async def deactivate_user(user_id: uuid.UUID, user_service: UserServiceDep) -> JSONResponse:
    result = await user_service.deactivate(user_id)
    schema = UserResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="User deactivated.")


@router.patch("/{user_id}/activate")
async def activate_user(user_id: uuid.UUID, user_service: UserServiceDep) -> JSONResponse:
    result = await user_service.activate(user_id)
    schema = UserResponse.model_validate(result, from_attributes=True)
    return success_response(data=schema.model_dump(mode="json"), message="User activated.")
