# M2 — Auth & RBAC

**Status:** Not Started
**Depends on:** M1
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M2 only.

## Goal

Real JWT login for IT admins using the existing `app/core/security.py` primitives, plus an RBAC dependency that restricts `/admin/*` routes to `role = it_admin`.

## Context recap

`app/core/security.py` already provides `hash_password`/`verify_password` (bcrypt), `create_access_token`/`create_refresh_token`/`decode_token` (PyJWT HS256, `iss` + `type` claims), `TokenPayload`, and `get_current_user` (HTTPBearer, `auto_error=False`). `user` now has `password_hash` (M1). Envelope + exceptions per `00_CONTEXT.md`.

## Preconditions

M1 done (`from app.models import User`; `password_hash` column exists). `app/core/security.py` exports the primitives above. `app/api/v1/dependencies.py` defines `CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]`.

## Scope checklist

- [ ] `UserRepository` (subclass `SQLAlchemyRepository[User]`) with `get_by_email`.
- [ ] `AuthService`: `authenticate(email, password)` → verify hash, issue access+refresh; `refresh(token)` → validate `type=refresh`, reissue; `get_me(user_id)`.
- [ ] Schemas: `LoginRequest{email,password}`, `TokenResponse{access_token, refresh_token, token_type}`, `RefreshRequest{refresh_token}`, `UserMeResponse{id,name,email,role,manager_id,is_active}`.
- [ ] Router `app/api/v1/routers/auth.py` (prefix `/auth`): `POST /login`, `POST /refresh`, `GET /me` (uses `CurrentUser`). Register in `routers/__init__.py`.
- [ ] `require_it_admin` dependency (wraps `get_current_user`, raises `ForbiddenException` if `role != it_admin`); expose `ITAdminUser` Annotated alias in `dependencies.py`. All M5–M13 admin routers depend on it.
- [ ] DI wiring: `get_user_repository`, `get_auth_service`, `AuthServiceDep`.
- [ ] Tests: login success/wrong-password (401), refresh, `/me`, `require_it_admin` forbids non-admin (403).

## Out of scope

User CRUD (M6), registration (not needed — users come from seed/M6), password reset, employee/manager auth flows.

## Acceptance criteria

`POST /api/v1/auth/login` with a seeded admin's credentials returns 201/200 with access+refresh tokens in the envelope; wrong password → 401 `UNAUTHORIZED`; `GET /api/v1/auth/me` with the token returns the admin profile; a non-admin token hitting an `/admin/*` route → 403 `FORBIDDEN`.

## Suggested session prompt

"Read `specs/M02_auth_and_rbac.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build JWT auth (`/auth/login`, `/auth/refresh`, `/auth/me`) reusing `app/core/security.py`, plus a `require_it_admin` RBAC dependency for `/admin/*`. Add `UserRepository`+`AuthService`+schemas+DI. Verify the acceptance criteria. Mark M2 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
