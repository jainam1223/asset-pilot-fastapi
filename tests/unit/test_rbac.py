import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.dependencies import ITAdminUser, require_it_admin
from app.core.exceptions import ForbiddenException
from app.core.security import TokenPayload, create_access_token

pytestmark = pytest.mark.unit


async def test_require_it_admin_allows_it_admin() -> None:
    token = TokenPayload(subject="user-1", claims={"role": "it_admin"})
    result = await require_it_admin(token)
    assert result is token


async def test_require_it_admin_forbids_employee() -> None:
    token = TokenPayload(subject="user-1", claims={"role": "employee"})
    with pytest.raises(ForbiddenException):
        await require_it_admin(token)


async def test_require_it_admin_forbids_manager() -> None:
    token = TokenPayload(subject="user-1", claims={"role": "manager"})
    with pytest.raises(ForbiddenException):
        await require_it_admin(token)


async def test_require_it_admin_forbids_missing_role_claim() -> None:
    token = TokenPayload(subject="user-1", claims={})
    with pytest.raises(ForbiddenException):
        await require_it_admin(token)


def _build_admin_gated_app() -> FastAPI:
    """Throwaway app wiring `ITAdminUser` through FastAPI's real DI (bearer
    header -> `get_current_user` -> `require_it_admin`), unlike the tests
    above which call `require_it_admin` directly with a hand-built
    `TokenPayload`. Reuses the app's real exception handlers so
    `ForbiddenException`/`UnauthorizedException` translate into the
    standard envelope, exactly as they would on a real `/admin/*` route.
    """
    from app.main import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/admin/whoami")
    async def whoami(current_user: ITAdminUser) -> dict[str, str]:
        return {"subject": current_user.subject}

    return app


async def test_it_admin_dependency_chain_allows_admin_token() -> None:
    app = _build_admin_gated_app()
    token = create_access_token("user-1", {"role": "it_admin"})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["subject"] == "user-1"


async def test_it_admin_dependency_chain_forbids_employee_token() -> None:
    app = _build_admin_gated_app()
    token = create_access_token("user-1", {"role": "employee"})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/whoami", headers={"Authorization": f"Bearer {token}"})
    body = response.json()

    assert response.status_code == 403
    assert body["error"]["code"] == "FORBIDDEN"
