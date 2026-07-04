import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListItemResponse(UserResponse):
    manager_name: str | None


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: UserRole


class ChangeRoleRequest(BaseModel):
    role: UserRole
