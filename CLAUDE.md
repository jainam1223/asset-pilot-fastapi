# CLAUDE.md

Guidance for Claude Code sessions working on this repo. **Read this + `_docs/IMPLEMENTATION_PLAN.md` at the start of every session.**

## 1. Project overview

Backend for **AssetPilot**, an internal **IT Asset Management (ITAM)** platform. It manages the full device lifecycle — inventory → request → approval → assignment → optional WFH shipping → support/repair → peer handover → return → retirement — with a permanent append-only per-device audit trail. The scaffold is designed to later host two more modules (Ticket Management, AI Chatbot); **only the ITAM module is being built now, and only its IT-Admin API surface** (`_docs/IT_ADMIN_API_FLOW.md`). Employee/Manager actions exist as seed data, not endpoints.

**Current state:** infrastructure is complete; domain code is NOT. `app/models/` is empty and the only migration (`alembic/versions/cde138860334_baseline.py`) creates zero tables. The throwaway `ping` reference slice (and the unused Redis cache layer it demonstrated) has been removed — copy the `health` vertical slice's router → service → repository pattern instead.

## 2. Tech stack (pinned in `pyproject.toml`)

- **Python ≥3.12**, **FastAPI 0.139.0**, Starlette 1.3.1, uvicorn 0.50.0 (gunicorn in prod)
- **PostgreSQL 17** via **SQLAlchemy[asyncio] 2.0.51** + **asyncpg 0.31.0**; **Alembic 1.18.5** (async)
- **Pydantic 2.13.4** + **pydantic-settings 2.14.2**
- **Auth:** **PyJWT 2.13.0** (HS256, access+refresh) + **bcrypt 5.0.0** — NOT python-jose/passlib
- **structlog 26.1.0** (JSON in prod, console in dev)
- Pkg mgr: **uv** (`uv.lock`; `requirements.txt` is an export). Lint/format: **ruff** (line 110). Types: **mypy strict**. Tests: **pytest + pytest-asyncio** (`asyncio_mode=auto`).

## 3. Architecture & folder conventions

**Strict 3-layer, layer-based (NOT feature-based):** `router → service → repository`.
- **API/router** (`app/api/v1/routers/`): HTTP only. Imports DI aliases from `dependencies.py`; never constructs a session/repo/service; never touches ORM models.
- **Service** (`app/services/`): business logic; no HTTP awareness; raises `AppException` subclasses; returns plain `@dataclass` results.
- **Repository** (`app/repositories/`): the ONLY layer that touches the SQLAlchemy session.

```
app/
  api/
    health.py              # /health/live, /health/ready — OUTSIDE /api/v1 by design
    v1/
      dependencies.py      # ALL DI wiring (Annotated aliases) — one file
      routers/
        __init__.py        # api_v1_router aggregator (include_router each sub-router)
  core/    config.py  security.py  logging.py  exceptions.py
  db/      base.py (Base + UUIDPrimaryKeyMixin + TimestampMixin)  session.py
  models/                  # SQLAlchemy models  ← EMPTY; build domain models here
  schemas/                 # Pydantic request/response DTOs
  services/                # business logic
  repositories/  base.py (AbstractRepository + SQLAlchemyRepository[Model])
  utils/   response.py (envelope)  pagination.py  request_context.py
  main.py                  # create_app() factory + middleware + global exception handlers
alembic/versions/          # migrations
tests/{unit,integration}/  # conftest.py has async httpx ASGI client fixture
scripts/                   # e.g. seed.py (to be added)
```

**Where new code goes** (one file per model/domain area):
- Model → `app/models/<entity>.py` (+ import it in `app/models/__init__.py`); enums → `app/models/enums.py`.
- Pydantic DTOs → `app/schemas/<domain>.py`. Repository → `app/repositories/<domain>_repository.py`. Service → `app/services/<domain>_service.py`. Router → `app/api/v1/routers/<domain>.py`.
- Wire providers in `app/api/v1/dependencies.py`; register the router in `app/api/v1/routers/__init__.py`.
- Migration → `make makemigrations message="..."` (never hand-author the filename).

## 4. How to run things (from `Makefile`)

Most targets run inside the `api` container via `docker compose exec`. **DB/migration commands are the exception:** `make create-db`, `make migrate`, `make makemigrations`, `make migrate-down`, `make db-reset`, and `make shell-db` run **natively on the host** via `uv run`, against the external Postgres in `DATABASE_URL` — not through the container. They read `DATABASE_URL` out of `.env` directly (see `HOST_DATABASE_URL_CMD` in the `Makefile`). This needs `uv sync` (`make install`) run once on the host, outside Docker.

- `make install` — `uv sync` (deps incl. dev) · `make env` — verify `.env` exists (no template file is checked in; create it by hand — see README's "Environment configuration")
- `make up` / `make down` / `make down-v` (clean slate) / `make rebuild`
- `make create-db` (create target DB) · `make migrate` (upgrade head) · `make makemigrations message="..."` · `make migrate-down` (rollback one) · `make db-reset` (destructive local reset) — **all native/host, not the container**
- `make test` · `make test-unit` (`-m unit`) · `make test-integration` (`-m integration` — runs **inside the container**; needs local Postgres reachable from the Docker bridge, see §7) · `make coverage`
- `make lint` (ruff check + `mypy app tests`) · `make format` (ruff format + `--fix`) · `make pre-commit`
- `make health` (curls `/health/ready`) · `make shell-api` (container) / `make shell-db` (host, psql)
- **Seed:** `scripts/seed.py` + a `make seed` target are added in Module M3.

## 5. Coding conventions (cite the reference slice)

- **Router** returns `success_response(...)` and depends only on a DI alias. From `app/api/v1/routers/ping.py`:
  ```python
  @router.get("")
  async def ping(ping_service: PingServiceDep) -> JSONResponse:
      result = await ping_service.ping()
      schema = PingResponseSchema(message=result.message, count=result.count)
      return success_response(data=schema.model_dump(), message="pong")
  ```
- **Response envelope** (`app/utils/response.py`) — the ONLY way to build a body. Success: `{status_code, data, message, meta:{timestamp, request_id, [pagination]}, success:true}`. Error (built by global handlers): `{status_code, message, error:{code, message, details}, meta, success:false}`. Lists pass `pagination=PaginationMeta(...)`.
- **Service** returns dataclasses, no HTTP types (`app/services/ping_service.py` uses `@dataclass PingResult`). Raise domain exceptions from here only.
- **Exceptions** (`app/core/exceptions.py`): raise `NotFoundException`(404), `ConflictException`(409), `ValidationException`(422), `UnauthorizedException`(401), `ForbiddenException`(403). Global handlers in `app/main.py` translate them. **Convention for state guards:** wrong entity state for an action → `ConflictException`(409); malformed input → `ValidationException`(422).
- **Repository** subclasses `SQLAlchemyRepository[Model]`, sets `model = X`, adds query methods. `create()` does `add`+`flush`+`refresh` and **never commits** — `get_db_session` commits on clean return, rolls back on exception. Never commit inside a repository/service.
- **DI** (`app/api/v1/dependencies.py`): add a `get_<x>_service(dep: Dep) -> XService` factory + `XServiceDep = Annotated[XService, Depends(get_x_service)]`. Infra aliases already exist: `DbSession`, `CurrentUser`.
- **Models:** subclass `Base` (`app/db/base.py`), use `UUIDPrimaryKeyMixin` + `TimestampMixin`. snake_case columns matching `_docs/db_schemas.dbml` exactly. For the `device_log.metadata` JSONB column, use a differently-named Python attribute (SQLAlchemy reserves `metadata`).
- **Naming:** router prefixes exactly as in `IT_ADMIN_API_FLOW.md` (`/admin/...`), all under `settings.API_V1_PREFIX` (`/api/v1`).

## 6. Module execution workflow

1. **Read `_docs/IMPLEMENTATION_PLAN.md` first** and find the target module's status in the Module Index.
2. **One module per session** unless told otherwise. Verify the module's **Preconditions** before starting (e.g. `from app.models import User` resolves).
3. Follow the module's Scope checklist / Out-of-scope / Acceptance criteria — each module section is self-contained; use its "Suggested session prompt".
4. Before marking done: `make lint`, `make test`, and verify the module's acceptance criteria.
5. **Update the Status column** for that module in `_docs/IMPLEMENTATION_PLAN.md` (`Not Started` → `In Progress` → `Done`) so progress persists across sessions.
6. **Do not modify another module's code** without flagging it in your summary.

**Recommended order (see plan §3):** M1 Models/Migration → M2 Auth → then M3 Seed / M4 Audit Log / M6 Users (parallel) → M5 Inventory → M7 Requests → M8 Assignment → M9 Shipping / M10 Support / M11 Extensions → M12 Handovers → M13 Dashboard.

## 7. Known gaps & assumptions (from plan Findings)

- **Scope = IT-Admin API only.** Employee/Manager flows are seed-only; no endpoints.
- **Auth:** `user.password_hash` is ADDED (not in original schema); `/auth/login|refresh|me` built in M2 using `app/core/security.py`; seed users share a dev password.
- **`device_log_event` extended** with `swapped_out` / `swapped_in` (used by support swap, API §8).
- **`device_log` is append-only** — enforced by Postgres RULES (`ON UPDATE/DELETE DO INSTEAD NOTHING`). Corrections are new rows.
- **DB-enforced invariants:** one active request per item (`uq_one_active_request_per_item`), one accepted handover per item (`uq_one_active_handover_per_item`).
- **Deactivate user (M6):** intentionally **hard-blocks** (409) when the user holds devices/open requests — this resolves the API doc's open Gap #4 in favor of the FE mockup (A14), and deviates from the doc's literal "just flip is_active".
- **`marked_lost` (M10):** completes the tied request with `completed_next_status = NULL`; IT sets a real next status later via §6.
- **`is_wfh`** is set by IT at assignment time (API §4).
- **Out of scope entirely:** QR management (FE A13) and Category CRUD (FE A14 tab) — no API spec exists; email/notifications (leave no-op stubs where the spec says "email requester").
- **"AI ranking" (FE A03)** is UX phrasing — `suggested-devices` is a deterministic sort (fewest active requests, longest free), no ML.
- **No Postgres container; external/managed Postgres.** `docker-compose.yml` has no `postgres` service — `DATABASE_URL` in `.env` points at an external/managed Postgres instance reachable by hostname from both the `api` container and the host (no `host.docker.internal`/`extra_hosts` involved). The native DB commands in §4 (`create-db`/`migrate`/etc.) run on the host via `uv run` against that same `DATABASE_URL`.
- **Two environments only, one env file.** `Environment` (`app/core/config.py`) has exactly `development` and `production` — no staging/test. Locally, `Settings` loads `.env` (the only env file that exists; no `.env.example`/`.env.staging`/`.env.production`, no `ENVIRONMENT`-based file-picking). In production there is no env file at all — Azure App Service/Container Apps injects real process env vars, including secrets resolved from **Azure Key Vault** via App Service "Key Vault reference" app settings (`@Microsoft.KeyVault(...)`); Azure resolves those before the container starts, so no Key Vault SDK/code is needed in the app.

## 8. Things NOT to do

- Don't put DB/ORM access in routers or services — repositories only.
- Don't `commit()` in a repository or service — the session dependency owns the transaction.
- Don't build a response dict by hand — always use `success_response`/`error_response`.
- Don't raise `HTTPException` for domain errors — raise `AppException` subclasses from the service layer.
- Don't hand-write migration filenames or edit applied migrations — use `make makemigrations`, then hand-add only what autogenerate can't (partial indexes, RULES) inside the generated file.
- Don't `UPDATE`/`DELETE` `device_log` — it's append-only by design.
- Don't build employee/manager endpoints, QR, category-CRUD, or a mailer (out of scope).
- Don't cross module boundaries: when one service needs another domain's rows, query via that domain's **repository**, don't import its service (see plan M9↔M10).
- Don't rename the `metadata` clash carelessly — map the JSONB column with a non-`metadata` Python attribute name.
- Don't skip updating the module Status in `_docs/IMPLEMENTATION_PLAN.md` when finishing.
