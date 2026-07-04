import uuid

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserMeResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    manager_id: uuid.UUID | None
    is_active: bool
