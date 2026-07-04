"""JWT auth: login, refresh, and the current-user profile."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import AuthServiceDep, CurrentUser
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserMeResponse
from app.utils.response import success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, auth_service: AuthServiceDep) -> JSONResponse:
    result = await auth_service.authenticate(payload.email, payload.password)
    schema = TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
    )
    return success_response(data=schema.model_dump(), message="Login successful.")


@router.post("/refresh")
async def refresh(payload: RefreshRequest, auth_service: AuthServiceDep) -> JSONResponse:
    result = await auth_service.refresh(payload.refresh_token)
    schema = TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
    )
    return success_response(data=schema.model_dump(), message="Token refreshed.")


@router.get("/me")
async def me(current_user: CurrentUser, auth_service: AuthServiceDep) -> JSONResponse:
    profile = await auth_service.get_me(current_user.subject)
    schema = UserMeResponse(
        id=profile.id,
        name=profile.name,
        email=profile.email,
        role=profile.role,
        manager_id=profile.manager_id,
        is_active=profile.is_active,
    )
    return success_response(data=schema.model_dump(mode="json"), message="Current user profile.")
