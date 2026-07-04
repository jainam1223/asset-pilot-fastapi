# Shared Context (read by every module spec)

This file holds everything common across modules — stack, structure, conventions, enums, findings/assumptions, and cross-cutting rules. Each `M<N>_*.md` spec assumes you've read this once. It is extracted from `_docs/IMPLEMENTATION_PLAN.md` (authoritative source — check there if anything here seems out of date) and `CLAUDE.md`.

## Product

Internal IT Asset Management (ITAM) MVP — device lifecycle: inventory → request → approval → assignment → optional WFH shipping → support/repair → peer handover → return → retirement, with a permanent append-only per-device audit trail. **This plan builds the IT-Admin API surface only** (per `_docs/IT_ADMIN_API_FLOW.md`); employee/manager actions exist only as seed data.

## Stack (pinned, from `pyproject.toml`)

Python ≥3.12, FastAPI 0.139.0, Starlette 1.3.1, uvicorn 0.50.0, SQLAlchemy[asyncio] 2.0.51, asyncpg 0.31.0, Alembic 1.18.5, Pydantic 2.13.4, pydantic-settings 2.14.2, redis 8.0.1, PyJWT[crypto] 2.13.0, bcrypt 5.0.0, structlog 26.1.0. DB = PostgreSQL 17. Pkg mgr = `uv`. Lint = ruff (line 110), types = mypy strict, tests = pytest + pytest-asyncio (`asyncio_mode=auto`).

## Existing structure (layer-based, strict 3-layer)

```
app/
  api/v1/routers/     # routers ONLY; use DI aliases; never touch session/repo directly
  api/v1/dependencies.py  # ALL DI wiring (Annotated aliases)
  api/health.py       # /health/live, /health/ready (outside /api/v1)
  core/               # config.py, security.py, logging.py, exceptions.py
  db/                 # base.py (Base + UUIDPrimaryKeyMixin + TimestampMixin), session.py, redis.py
  models/             # SQLAlchemy models (EMPTY — build here)
  schemas/            # Pydantic DTOs
  services/           # business logic; raises AppException; returns dataclasses (no HTTP)
  repositories/       # ONLY layer touching ORM session / Redis; base.py has SQLAlchemyRepository[Model]
  utils/              # response.py (envelope), pagination.py, request_context.py
  main.py             # create_app() factory
alembic/versions/     # migrations (only empty baseline exists)
tests/{unit,integration}/
```

## Conventions to follow (non-negotiable)

- **Layering:** router → service → repository. Routers import DI aliases from `dependencies.py`. Services raise `AppException` subclasses and return plain dataclasses. Only repositories touch the session/Redis.
- **Models:** subclass `Base` (from `app.db.base`), use `UUIDPrimaryKeyMixin` (uuid4 PK) + `TimestampMixin` (`created_at`/`updated_at`).
- **Repositories:** subclass `SQLAlchemyRepository[Model]`, set `model = X`, add domain queries. `create()` does `add`+`flush`+`refresh` (NO commit — `get_db_session` commits on clean exit, rolls back on exception).
- **DI:** add `get_<x>_service(...)` factory + `XServiceDep = Annotated[XService, Depends(get_x_service)]` in `dependencies.py`. Register routers in `app/api/v1/routers/__init__.py` (`api_v1_router.include_router(...)`).
- **Response envelope (every endpoint):** success `{status_code, data, message, meta:{timestamp, request_id, [pagination]}, success:true}`; error `{status_code, message, error:{code, message, details}, meta, success:false}`. Use `app/utils/response.py` (`success_response`/`error_response`). Global handlers already installed.
- **Errors:** raise `NotFoundException`(404), `ConflictException`(409), `ValidationException`(422), `UnauthorizedException`(401), `ForbiddenException`(403) from `app/core/exceptions.py` in the service layer.
- **Migrations:** author models, then `make makemigrations` (Alembic autogenerate imports `app.models` + `Base.metadata`). Review the generated file; add partial indexes / RULES by hand where autogenerate can't (see M1).

## Enums (16, from `db_schemas.dbml`)

Model as Python `enum.Enum` + SQLAlchemy `Enum`: `user_role`(employee, manager, it_admin); `device_status`(available, assigned, shipping_pending, return_shipping_pending, under_repair, maintenance, lost, retired, returned_to_client); `request_status`(requested, pending_mgr_approval, pending_it_approval, assigned, completed, rejected, cancelled); `mgr_approval_status`(not_required, pending, approved, rejected); `rejected_by_enum`(manager, it_admin, it_admin_cancel); `request_priority`(low, medium, high); `owner_type`(company, client); `support_type`(update, damage, lost); `support_status`(open, in_progress, resolved); `support_resolution`(remote_resolved, repaired_in_place, swapped, marked_lost); `extension_status`(pending, approved, rejected); `handover_status`(requested, accepted, rejected, cancelled, completed); `device_log_event`(device_created, device_edited, assigned, client_assigned, ship_outbound_initiated, ship_outbound_completed, return_ship_initiated, return_received, assignment_completed, status_changed, support_opened, support_resolved, support_auto_closed, extension_requested, extension_approved, extension_rejected, handover_requested, handover_accepted, handover_rejected, handover_cancelled, handover_completed, marked_lost, retired, returned_to_client, **swapped_out, swapped_in** ← added per decision); `actor_role`(employee, manager, it_admin, system).

## Findings & Assumptions (binding — do not re-litigate)

- **F1:** Only IT-Admin endpoints (`IT_ADMIN_API_FLOW.md`) are built. Employee/Manager flows are seed-only. Any manager-approval state on a request is set by the seed or by IT escalation, not by a manager endpoint.
- **F2:** Schema has no password field; ADD `password_hash varchar(255) NOT NULL` to `user` (M1) and build `/auth/*` (M2). Seed sets a shared dev password (M3).
- **F3:** `device_log_event` extended with `swapped_out`/`swapped_in` (M1) to match API §8.
- **F4 — Deactivation rule:** `PATCH /admin/users/{id}/deactivate` returns 409 `CONFLICT` if the user has any device with `current_owner_id = user.id` OR any request in a non-terminal status. Matches FE A14.
- **F5 — `is_wfh` source:** set by IT at assignment time (`POST /admin/requests/{id}/assign` body includes `is_wfh`), per API §4. No employee pre-set.
- **F6 — `marked_lost` resolution:** resolving a support ticket as `marked_lost` sets item→`lost` AND completes the tied request with `completed_next_status = NULL` (per API §8 gap note). IT later sets a manual next status via §6 status change.
- **F7 — QR management (A13) and Categories management tab (A14):** Out of scope for all modules. Category *dropdown* (`GET /admin/dropdowns/item-categories`) IS in scope (M5).
- **F8:** Schema filename drift (informational) — `db_schemas.dbml` is authoritative.
- **F9 — Seed source is TS/Prisma:** `db_seed.ts` uses Prisma camelCase + a seeded PRNG (mulberry32, seed 42). M3 re-implements its intent in Python (async SQLAlchemy), not a literal port. `user` emails use `@techcorp.internal`.
- **F10:** `device_log` is append-only — enforce via Postgres RULES (`ON UPDATE/DELETE DO INSTEAD NOTHING`) added in the M1 migration. Corrections are new rows, never edits.
- **F11:** "AI ranking" (FE A03) is UX-only: `GET /admin/requests/{id}/suggested-devices` is deterministic (fewest active requests, longest free) — no ML.

## Cross-cutting Concerns (apply to every module)

- **Auth/RBAC:** all `/admin/*` routers depend on `require_it_admin` (M2). `/auth/*` is public except `/me`. Never trust the client role — re-validate in the dependency.
- **Response shape:** every endpoint returns the standard envelope via `app/utils/response.py`. Lists use `PaginationParams`/`Page[T]` (`app/utils/pagination.py`) and populate `meta.pagination`. 204 = no body.
- **Errors:** raise `AppException` subclasses from the SERVICE layer only. Global handlers format them. Status-guard violations → `ConflictException`(409) for "valid entity, wrong state", `ValidationException`(422) for malformed input.
- **Device log discipline:** EVERY device-touching write pairs with a `DeviceLogService.append(...)` in the same transaction (M4). Milestone flag comes from the M4 event→milestone map. `actor_role='system'` + `actor_id=NULL` ONLY for `support_auto_closed`.
- **Invariants enforced by DB (M1):** one active request per item (`uq_one_active_request_per_item`), one accepted handover per item (`uq_one_active_handover_per_item`), append-only device_log (RULES). Services should still pre-check and raise friendly 409s rather than leaking IntegrityError.
- **Transactions:** `get_db_session` commits on clean return, rolls back on exception. Repositories `flush`+`refresh`, never commit. Multi-step writes in one service method share one session/transaction.
- **Layering:** router (DI aliases only) → service (logic, dataclasses, exceptions) → repository (only ORM/Redis). No cross-domain service imports where avoidable; when one module needs another domain's rows, query via its repository, not its service (e.g. M9↔M10).
- **Validation:** Pydantic v2 schemas at the API boundary; enum fields typed with the Python enums from `app/models/enums.py`.
- **Testing:** pytest + pytest-asyncio (`asyncio_mode=auto`); async httpx ASGI client fixture in `tests/conftest.py`. Add integration tests per module (endpoint → DB) + unit tests for tricky service logic (overlap detection, swap flow, auto-close cascade). Run `make test`, `make lint`, `make format`, mypy (strict) before marking a module Done.
- **Email/notifications:** out of scope — where the API says "email requester", leave a no-op/log stub, do not build a mailer.
- **Naming:** snake_case columns/fields matching `db_schemas.dbml` exactly; router prefixes exactly as in `IT_ADMIN_API_FLOW.md` (`/admin/...`), all under `settings.API_V1_PREFIX` (`/api/v1`).
- **Module workflow:** work ONE module per session; verify preconditions first; update Status in both this module's spec file AND `_docs/IMPLEMENTATION_PLAN.md`'s Module Index when done; don't modify another module's code without flagging it.
