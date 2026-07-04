# ITAM Backend — Implementation Plan

> Module-by-module execution plan. Each module is built in its own session. Read this file + `CLAUDE.md` before starting any module. After finishing a module, set its **Status** in the Module Index below to `Done`.

## 1. Project Snapshot

**Product:** Internal IT Asset Management (ITAM) MVP — device lifecycle: inventory → request → approval → assignment → optional WFH shipping → support/repair → peer handover → return → retirement, with a permanent append-only per-device audit trail. **This plan builds the IT-Admin API surface only** (per `IT_ADMIN_API_FLOW.md`); employee/manager actions exist only as seed data.

**Stack (pinned, from `pyproject.toml`):** Python ≥3.12, FastAPI 0.139.0, Starlette 1.3.1, uvicorn 0.50.0, SQLAlchemy[asyncio] 2.0.51, asyncpg 0.31.0, Alembic 1.18.5, Pydantic 2.13.4, pydantic-settings 2.14.2, redis 8.0.1, PyJWT[crypto] 2.13.0, bcrypt 5.0.0, structlog 26.1.0. DB = PostgreSQL 17. Pkg mgr = `uv`. Lint = ruff (line 110), types = mypy strict, tests = pytest + pytest-asyncio (`asyncio_mode=auto`).

**Existing structure (layer-based, strict 3-layer):**
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

**Conventions to follow (non-negotiable):**
- **Layering:** router → service → repository. Routers import DI aliases from `dependencies.py`. Services raise `AppException` subclasses and return plain dataclasses. Only repositories touch the session/Redis.
- **Models:** subclass `Base` (from `app.db.base`), use `UUIDPrimaryKeyMixin` (uuid4 PK) + `TimestampMixin` (`created_at`/`updated_at`).
- **Repositories:** subclass `SQLAlchemyRepository[Model]`, set `model = X`, add domain queries. `create()` does `add`+`flush`+`refresh` (NO commit — `get_db_session` commits on clean exit, rolls back on exception).
- **DI:** add `get_<x>_service(...)` factory + `XServiceDep = Annotated[XService, Depends(get_x_service)]` in `dependencies.py`. Register routers in `app/api/v1/routers/__init__.py` (`api_v1_router.include_router(...)`).
- **Response envelope (every endpoint):** success `{status_code, data, message, meta:{timestamp, request_id, [pagination]}, success:true}`; error `{status_code, message, error:{code, message, details}, meta, success:false}`. Use `app/utils/response.py` (`success_response`/`error_response`). Global handlers already installed.
- **Errors:** raise `NotFoundException`(404), `ConflictException`(409), `ValidationException`(422), `UnauthorizedException`(401), `ForbiddenException`(403) from `app/core/exceptions.py` in the service layer.
- **Migrations:** author models, then `make makemigrations` (Alembic autogenerate imports `app.models` + `Base.metadata`). Review the generated file; add partial indexes / RULES by hand where autogenerate can't (see M1).

**Enums (16, from `db_schemas.dbml`) — model as Python `enum.Enum` + SQLAlchemy `Enum`:** `user_role`(employee, manager, it_admin); `device_status`(available, assigned, shipping_pending, return_shipping_pending, under_repair, maintenance, lost, retired, returned_to_client); `request_status`(requested, pending_mgr_approval, pending_it_approval, assigned, completed, rejected, cancelled); `mgr_approval_status`(not_required, pending, approved, rejected); `rejected_by_enum`(manager, it_admin, it_admin_cancel); `request_priority`(low, medium, high); `owner_type`(company, client); `support_type`(update, damage, lost); `support_status`(open, in_progress, resolved); `support_resolution`(remote_resolved, repaired_in_place, swapped, marked_lost); `extension_status`(pending, approved, rejected); `handover_status`(requested, accepted, rejected, cancelled, completed); `device_log_event`(device_created, device_edited, assigned, client_assigned, ship_outbound_initiated, ship_outbound_completed, return_ship_initiated, return_received, assignment_completed, status_changed, support_opened, support_resolved, support_auto_closed, extension_requested, extension_approved, extension_rejected, handover_requested, handover_accepted, handover_rejected, handover_cancelled, handover_completed, marked_lost, retired, returned_to_client, **swapped_out, swapped_in** ← added per decision 3); `actor_role`(employee, manager, it_admin, system).

## 2. Findings & Assumptions

- **F1 — Scope resolved:** Only IT-Admin endpoints (`IT_ADMIN_API_FLOW.md`) are built. Employee/Manager flows are seed-only. Any manager-approval state on a request is set by the seed or by IT escalation, not by a manager endpoint.
- **F2 — Auth model gap resolved:** schema has no password field; we ADD `password_hash varchar(255) NOT NULL` to `user` (M1) and build `/auth/*` (M2). Seed sets a shared dev password (M3).
- **F3 — Swap enum resolved:** `device_log_event` extended with `swapped_out`/`swapped_in` (M1) to match API §8.
- **F4 — Deactivation rule (assumption):** `PATCH /admin/users/{id}/deactivate` returns 409 `CONFLICT` if the user has any device with `current_owner_id = user.id` OR any request in a non-terminal status. Matches FE A14.
- **F5 — `is_wfh` source (assumption):** `is_wfh` is set by IT at assignment time (`POST /admin/requests/{id}/assign` body includes `is_wfh`), per API §4. No employee pre-set.
- **F6 — `marked_lost` resolution (assumption):** resolving a support ticket as `marked_lost` sets item→`lost` AND completes the tied request with `completed_next_status = NULL` (per API §8 gap note). IT later sets a manual next status via §6 status change.
- **F7 — QR management (A13) and Categories management tab (A14):** the FE shows a QR export/regenerate screen and a category CRUD tab, but `IT_ADMIN_API_FLOW.md` has **no** endpoints for them (only `qr_code_token` field + a categories dropdown). **Out of scope** for all modules unless separately requested; category *dropdown* (`GET /admin/dropdowns/item-categories`) IS in scope (M5).
- **F8 — Schema filename drift (informational):** `db_seed.ts`/`PROJECT.md` mention `schema_v3.dbml`; the real file is `db_schemas.dbml` and is authoritative.
- **F9 — Seed source is TS/Prisma:** `db_seed.ts` uses Prisma camelCase + a seeded PRNG (mulberry32, seed 42). M3 re-implements its intent in Python (async SQLAlchemy), not a literal port. `user` emails use `@techcorp.internal`.
- **F10 — device_log is append-only:** enforce via Postgres RULES (`ON UPDATE/DELETE DO INSTEAD NOTHING`) added in the M1 migration. Corrections are new rows, never edits.
- **F11 — "AI ranking" (FE A03) is UX-only:** `GET /admin/requests/{id}/suggested-devices` is deterministic (fewest active requests, longest free) — no ML.

## 3. Module Index

| # | Module | Depends On | Complexity | Status |
|---|--------|-----------|-----------|--------|
| M1 | Domain Models & Migration | — | L | Done |
| M2 | Auth & RBAC | M1 | M | Done |
| M3 | Seed Data | M1, M2 | L | Done |
| M4 | Device Audit Log (service + timeline) | M1 | M | Not Started |
| M5 | Inventory, Device Detail & Dropdowns | M1, M2, M4 | L | Not Started |
| M6 | User Management | M1, M2 | M | Not Started |
| M7 | Request Management & IT Approval Queue | M1, M2, M4 | M | Not Started |
| M8 | Device Assignment & Client Direct Assign | M4, M5, M7 | L | Not Started |
| M9 | WFH Shipping & Returns | M4, M8 | M | Not Started |
| M10 | Support Requests | M4, M5, M8 | L | Not Started |
| M11 | Extension Requests | M4, M8 | M | Not Started |
| M12 | Handovers (read-only audit) | M1, M4 | S | Not Started |
| M13 | Admin Dashboard | M5, M7, M9, M10, M11 | M | Not Started |

**Parallelism:** M1→M2 sequential. After M2: M3, M4, M6 can run in parallel. M5 needs M4. M7 needs M4. M8 needs M5+M7. M9/M10/M11 need M8. M12 needs only M1+M4. M13 is last (aggregates everything).

---

## M1 — Domain Models & Migration

**Goal:** Define all 8 SQLAlchemy models + 16 enums (incl. added `swapped_out`/`swapped_in`) + the `password_hash` column on `user`, then produce ONE Alembic migration that creates every table, index, partial unique index, and the append-only RULES on `device_log`. This is the foundation for all other modules.

**Context recap — tables (from `db_schemas.dbml`; add `TimestampMixin` = `created_at`/`updated_at timestamptz not null default now()` to every table via mixin):**
- **user:** id(uuid PK), name(varchar255 NN), email(varchar255 NN UNIQUE), **password_hash(varchar255 NN — ADDED)**, role(user_role NN default employee), manager_id(uuid null FK→user.id), is_active(bool NN default true). Indexes: manager_id, role.
- **item_category:** id, name(varchar255 NN UNIQUE), description(text null), requires_mgr_approval(bool NN default false), is_active(bool NN default true).
- **item:** id, name(varchar255 NN), serial_no(varchar255 NN UNIQUE), category_id(uuid NN FK→item_category), owner_type(owner_type NN default company), client_name(varchar255 null), status(device_status NN default available), current_owner_id(uuid null FK→user), purchase_date(date null), qr_code_token(uuid NN UNIQUE default gen_random_uuid()). Indexes: status, category_id, current_owner_id, composite (category_id,status) `idx_item_available_by_category`.
- **request:** id, requester_id(NN FK→user), category_id(NN FK→item_category), assigned_item_id(null FK→item), requested_from/requested_to(timestamptz NN), assigned_from/assigned_to(timestamptz null), status(request_status NN default requested), priority(request_priority NN default medium), note(text null), requires_mgr_approval(bool NN default false), mgr_approval_status(mgr_approval_status NN default not_required), manager_id(null FK→user), manager_decision_note(text null), manager_decided_at(null), it_decided_by(null FK→user), it_decision_note(null), it_decided_at(null), rejected_by(rejected_by_enum null), rejected_reason(null), cancelled_by(null FK→user), cancelled_at(null), is_wfh(bool NN default false), ship_tracking_url(null), ship_initiated_at(null), ship_completed_at(null), return_tracking_url(null), return_initiated_at(null), completed_at(null), completed_by(null FK→user), completed_next_status(device_status null), is_client_direct(bool NN default false). Indexes: requester_id, status, assigned_item_id, category_id, (priority,created_at) `idx_request_it_queue`, **partial UNIQUE (assigned_item_id, status) `uq_one_active_request_per_item` WHERE status NOT IN ('rejected','completed','cancelled')**, (assigned_item_id, assigned_from, assigned_to) `idx_request_date_range`.
- **extension_request:** id, original_request_id(NN FK→request), requester_id(NN FK→user), current_assigned_to(timestamptz NN), extended_to(timestamptz NN), status(extension_status NN default pending), requires_mgr_approval(bool NN default false), manager_id(null FK→user), mgr_approval_status(NN default not_required), manager_note(null), manager_decided_at(null), it_decided_by(null FK→user), it_note(null), it_decided_at(null).
- **handover_request:** id, item_id(NN FK→item), owner_id(NN FK→user), borrower_id(NN FK→user), requested_duration_hours(int null), status(handover_status NN default requested), requested_at(timestamptz NN default now()), decided_at(null), completed_at(null), note(null). Indexes: item_id, borrower_id, owner_id, **partial UNIQUE (item_id, status) `uq_one_active_handover_per_item` WHERE status='accepted'**.
- **support_request:** id, item_id(NN FK→item), requester_id(NN FK→user), request_id(null FK→request), type(support_type NN), description(text NN), status(support_status NN default open), resolution(support_resolution null), it_note(null), swapped_to_item_id(null FK→item), filed_at(timestamptz NN default now()), resolved_by(null FK→user), resolved_at(null), auto_closed(bool NN default false). Indexes: item_id, status, request_id, filed_at `idx_support_open_queue`.
- **device_log (append-only):** id, item_id(NN FK→item), event_type(device_log_event NN), actor_id(null FK→user), actor_role(actor_role NN), request_id(null FK→request), support_request_id(null FK→support_request), extension_request_id(null FK→extension_request), handover_request_id(null FK→handover_request), from_value(text null), to_value(text null), note(text null), metadata(jsonb NN default '{}'::jsonb), is_milestone(bool NN default false), occurred_at(timestamptz NN default now()). Indexes: (item_id,occurred_at) `idx_device_log_item_time`, partial (item_id,occurred_at) `idx_device_log_milestones` WHERE is_milestone=true, request_id, event_type. **RULES:** `device_log_no_update` (ON UPDATE DO INSTEAD NOTHING), `device_log_no_delete` (ON DELETE DO INSTEAD NOTHING).

**Preconditions:** `app/db/base.py` exports `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`. `app/models/__init__.py` is empty. `alembic/env.py` imports `app.models` + `Base.metadata`.

**Scope checklist:**
- [ ] One file per model in `app/models/` (e.g. `user.py`, `item_category.py`, `item.py`, `request.py`, `extension_request.py`, `handover_request.py`, `support_request.py`, `device_log.py`); define enums in `app/models/enums.py` (Python `enum.Enum`, mapped via SQLAlchemy `Enum(..., name="...")`).
- [ ] Import all models in `app/models/__init__.py` so autogenerate + relationships resolve.
- [ ] Self-referential `user.manager_id`; all FKs with correct nullability; `metadata` as JSONB (rename Python attr to avoid SQLAlchemy `metadata` clash — e.g. attribute `log_metadata`, `Column("metadata", JSONB)`).
- [ ] `make makemigrations m="create itam schema"`; review generated migration.
- [ ] Hand-add to migration: 2 partial UNIQUE indexes, `idx_device_log_milestones` partial index, and the 2 `device_log` RULES (raw `op.execute(...)` in `upgrade`, reverse in `downgrade`).
- [ ] `make migrate` (upgrade head) succeeds against a clean DB; `make migrate-down` reverses cleanly.

**Out of scope:** any repository/service/router/endpoint; seed data (M3); auth endpoints (M2).

**Acceptance criteria:** `make migrate` creates all 8 tables + all enums + all indexes; `\d device_log` shows the two RULES; inserting then attempting `UPDATE`/`DELETE` on `device_log` is silently ignored (0 rows changed); a duplicate active `request` for the same `assigned_item_id` raises a unique violation; `make migrate-down` drops everything; `mypy` + `ruff` pass on `app/models/`.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M1** and `CLAUDE.md`. Implement all SQLAlchemy models + enums for the ITAM schema (8 tables incl. the added `user.password_hash` and the `swapped_out`/`swapped_in` device_log events), then generate and hand-finish the Alembic migration (partial unique indexes + device_log append-only RULES). Verify `make migrate`/`migrate-down` and the acceptance criteria in the plan. Do not build any endpoints. Mark M1 Done in the plan when finished."

---

## M2 — Auth & RBAC

**Goal:** Real JWT login for IT admins using the existing `app/core/security.py` primitives, plus an RBAC dependency that restricts `/admin/*` routes to `role = it_admin`.

**Context recap:** `app/core/security.py` already provides `hash_password`/`verify_password` (bcrypt), `create_access_token`/`create_refresh_token`/`decode_token` (PyJWT HS256, `iss` + `type` claims), `TokenPayload`, and `get_current_user` (HTTPBearer, `auto_error=False`). `user` now has `password_hash` (M1). Envelope + exceptions from cross-cutting section.

**Preconditions:** M1 done (`from app.models import User`; `password_hash` column exists). `app/core/security.py` exports the primitives above. `app/api/v1/dependencies.py` defines `CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]`.

**Scope checklist:**
- [x] `UserRepository` (subclass `SQLAlchemyRepository[User]`) with `get_by_email`.
- [x] `AuthService`: `authenticate(email, password)` → verify hash, issue access+refresh; `refresh(token)` → validate `type=refresh`, reissue; `get_me(user_id)`.
- [x] Schemas: `LoginRequest{email,password}`, `TokenResponse{access_token, refresh_token, token_type}`, `RefreshRequest{refresh_token}`, `UserMeResponse{id,name,email,role,manager_id,is_active}`.
- [x] Router `app/api/v1/routers/auth.py` (prefix `/auth`): `POST /login`, `POST /refresh`, `GET /me` (uses `CurrentUser`). Register in `routers/__init__.py`.
- [x] `require_it_admin` dependency (wraps `get_current_user`, raises `ForbiddenException` if `role != it_admin`); expose `ITAdminUser` Annotated alias in `dependencies.py`. All M5–M13 admin routers depend on it.
- [x] DI wiring: `get_user_repository`, `get_auth_service`, `AuthServiceDep`.
- [x] Tests: login success/wrong-password (401), refresh, `/me`, `require_it_admin` forbids non-admin (403).

**Out of scope:** user CRUD (M6), registration (not needed — users come from seed/M6), password reset, employee/manager auth flows.

**Acceptance criteria:** `POST /api/v1/auth/login` with a seeded admin's credentials returns 201/200 with access+refresh tokens in the envelope; wrong password → 401 `UNAUTHORIZED`; `GET /api/v1/auth/me` with the token returns the admin profile; a non-admin token hitting an `/admin/*` route → 403 `FORBIDDEN`.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M2** and `CLAUDE.md`. Build JWT auth (`/auth/login`, `/auth/refresh`, `/auth/me`) reusing `app/core/security.py`, plus a `require_it_admin` RBAC dependency for `/admin/*`. Add `UserRepository`+`AuthService`+schemas+DI. Verify the acceptance criteria. Mark M2 Done."

---

## M3 — Seed Data

**Goal:** A Python seed script that populates a realistic demo dataset mirroring `db_seed.ts` intent, so every IT-Admin endpoint has data to operate on. Idempotent (truncate-and-reload).

**Context recap (from `db_seed.ts`):** deterministic (fixed seed). Counts: **38 users** (5 managers, 3 it_admins, 30 employees; employees `is_active` for first 28, 2 inactive; employee `manager_id` = random manager). Emails `first.last@techcorp.internal`. **All users get a shared dev password** (e.g. `Password123!`) hashed via `hash_password`. **10 item_categories** (Laptop*, Mobile Phone*, Monitor, Keyboard, Mouse, Headset, Charger, Tablet*, Dock, Legacy[inactive]; `*`=requires_mgr_approval). **~72 items** across categories + 4 client-owned (owner_type=client, client_name from a small pool, status=assigned) + special singles (1 under_repair, 1 maintenance, 1 lost, 1 retired). **Requests** across all statuses: completed (incl. 1 WFH), assigned/active (incl. 1 shipping_pending, 1 return_shipping_pending), pending_it_approval (6), pending_mgr_approval (4), requested (3), rejected (4), cancelled (3), client-direct (≤4). **3 extension_requests** (approved/pending/rejected). **~8 support_requests** (incl. 1 auto_closed, 1 resolved-swapped chain). **6 handover_requests** (accepted/completed/rejected/cancelled + 2 simultaneous requested on one device). **device_log:** ≥1 `device_created` per item + milestone/sub-events matching each entity, incl. one `support_auto_closed` with `actor_id=NULL, actor_role=system`.

**Preconditions:** M1 done (all models + migration applied). M2 done (`hash_password` available for seeded credentials).

**Scope checklist:**
- [x] `scripts/seed.py` (async, uses `AsyncSessionLocal`); wire a `make seed` target (and note re-runnability — truncate in FK-safe order: device_log, support_request, handover_request, extension_request, request, item, item_category, user).
- [x] Deterministic generation (fixed random seed) so the dataset is reproducible.
- [x] Respect all invariants: only one active request per item (unique index), only one accepted handover per item, valid FK targets, correct enum values, milestone flags on device_log.
- [x] Print a summary (rows per table) at the end.

**Out of scope:** any endpoint; QR PDF generation; a literal 1:1 port of the TS/Prisma code (re-implement intent in Python).

**Acceptance criteria:** `make seed` on a migrated DB inserts all rows with zero FK/unique violations and can be re-run without error; counts roughly match (38 users, 10 categories, ~72 items, requests spanning all 7 statuses, 3 extensions, ~8 support, 6 handovers); `SELECT count(*) FROM device_log` > items count; the shared dev password logs in via M2.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M3** and `CLAUDE.md`. Write `scripts/seed.py` (+ `make seed`) that reproduces the `db_seed.ts` dataset intent in async Python SQLAlchemy: 38 users (shared hashed dev password), 10 categories, ~72 items, requests across all statuses, extensions/support/handovers, and device_log entries. Respect all unique/partial-index invariants. Verify re-runnable + acceptance criteria. Mark M3 Done."

---

## M4 — Device Audit Log (service + timeline)

**Goal:** A shared, reusable `DeviceLogService.append(...)` that ALL device-touching modules (M5, M7–M11) call to write `device_log` rows correctly (event type, actor, milestone flag, linked request/support/extension/handover ids, from/to values, jsonb metadata), plus the read-side timeline endpoint.

**Context recap:** `device_log` schema in M1. Milestone events (surfaced in timeline `milestones_only=true`): assigned, client_assigned, return_received, assignment_completed, support_opened, support_resolved, handover_accepted, handover_completed, status_changed, marked_lost, retired, returned_to_client. Non-milestone: device_created, device_edited, ship_* , extension_*, handover_requested/rejected/cancelled, swapped_out/swapped_in (per API metadata). **API §7:** `GET /admin/items/{itemId}/timeline?milestones_only=<bool default true>` → device_log rows ordered `occurred_at ASC`.

**Preconditions:** M1 done (`DeviceLog` model). M2 done (`require_it_admin`).

**Scope checklist:**
- [ ] `DeviceLogRepository` (subclass base) with `list_for_item(item_id, milestones_only, pagination)` ordered `occurred_at ASC`.
- [ ] `DeviceLogService.append(*, item_id, event_type, actor_id, actor_role, request_id=None, support_request_id=None, extension_request_id=None, handover_request_id=None, from_value=None, to_value=None, note=None, metadata=None, is_milestone=None)` — if `is_milestone` is None, derive from an event→milestone map defined here (single source of truth).
- [ ] `get_timeline(item_id, milestones_only)` service method + schema `DeviceLogEntryResponse`.
- [ ] Router endpoint `GET /admin/items/{itemId}/timeline`. (Router file may be shared with M5's items router; if M5 not built yet, create `items.py` and M5 extends it.)
- [ ] DI wiring `get_device_log_repository`, `get_device_log_service`, `DeviceLogServiceDep`. Design `append` so other services receive `DeviceLogService` via DI and call it within the same request/session (writes flushed, committed by `get_db_session`).
- [ ] Tests: append writes a row with correct milestone flag; timeline returns milestone-only vs full correctly ordered.

**Out of scope:** inventory CRUD (M5), any write that produces logs (those live in their own modules and CALL this service).

**Acceptance criteria:** `DeviceLogService.append(...)` inserts a row with correct `is_milestone` from the map; `GET /api/v1/admin/items/{seeded_item}/timeline` returns milestone rows ordered oldest→newest; `?milestones_only=false` returns all rows including sub-events.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M4** and `CLAUDE.md`. Build the shared `DeviceLogService.append(...)` (event→milestone map as single source of truth), `DeviceLogRepository`, and the `GET /admin/items/{itemId}/timeline` endpoint. Wire DI so later services inject `DeviceLogService`. Verify acceptance criteria. Mark M4 Done."

---

## M5 — Inventory, Device Detail & Dropdowns

**Goal:** Device inventory CRUD, status changes (each logged), the composite device-detail view, and the shared dropdown endpoints.

**Context recap (API §6, §7, §14):**
- `GET /admin/items` — filters `category_id, status, owner_type, search`(name/serial_no); response item.* + category name + current_owner name; paginated.
- `POST /admin/items` — body `{name, serial_no, category_id, owner_type, client_name, purchase_date}`; device_log `device_created` (not milestone, to_value=available, actor it_admin).
- `PATCH /admin/items/{itemId}` — body `{name, category_id, client_name, purchase_date}`; device_log `device_edited` (not milestone, metadata field/old/new).
- `PATCH /admin/items/{itemId}/status` — body `{status, it_note}`; event map: lost→`marked_lost`, retired→`retired`, returned_to_client→`returned_to_client`, else→`status_changed`; always milestone, actor it_admin. No auto Lost→Retired.
- `GET /admin/items/{itemId}` — `{item, category, current_owner, current_request, open_support[], active_handover}`.
- `GET /admin/dropdowns/item-categories` (is_active=true), `/managers` (role=manager AND is_active), `/employees` (role=employee AND is_active).

**Preconditions:** M1 (Item/ItemCategory/User models), M2 (`require_it_admin`), M4 (`DeviceLogService`). Note: `current_request`, `open_support`, `active_handover` on the detail view depend on request/support/handover tables existing (M1 has them) — return empty/null gracefully if those modules' writes haven't populated data yet.

**Scope checklist:**
- [ ] `ItemRepository` (filters + search + joins for category/owner names), `ItemCategoryRepository`.
- [ ] `InventoryService`: list, create (+log), edit (+log with diff metadata), change_status (+mapped log), get_detail (assemble composite).
- [ ] Schemas for each request/response shape above.
- [ ] Router `items.py` (extends M4's if present): the 5 item endpoints; `dropdowns.py` for the 3 dropdowns.
- [ ] Validation: `serial_no` unique (→409 `CONFLICT`); `client_name` required only when `owner_type=client`; unknown id →404.
- [ ] DI wiring + tests (create/edit/status transitions produce correct device_log events).

**Out of scope:** assignment/return status changes driven by request lifecycle (M8/M9 set item.status through their own services); QR management (F7).

**Acceptance criteria:** `POST /admin/items` returns 201 with the item + writes a `device_created` log; `PATCH .../status` with `status=lost` writes a `marked_lost` milestone and does NOT auto-retire; `GET /admin/items/{id}` returns the composite with category + current_owner; `GET /admin/items?search=<serial>` filters correctly; dropdowns return only active rows.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M5** and `CLAUDE.md`. Build inventory CRUD + status change + composite device detail (API §6/§7) and the 3 dropdown endpoints (§14), each device-mutating write calling `DeviceLogService`. Verify acceptance criteria. Mark M5 Done."

---

## M6 — User Management

**Goal:** IT-Admin user administration: list, create, change role, activate/deactivate (with the hard-block rule).

**Context recap (API §13):**
- `GET /admin/users` — filters `role, is_active, search`(name/email) + manager name; paginated.
- `POST /admin/users` — body `{name, email, role}`; is_active=true; `manager_id` NOT set (self-service). NOTE: needs a `password_hash` — set a default/dev password or an "invited, unset" placeholder (choose: set the shared dev password so the created user can log in).
- `PATCH /admin/users/{id}/role` — body `{role}`.
- `PATCH /admin/users/{id}/deactivate` / `PATCH /admin/users/{id}/activate` — toggle is_active. **F4: deactivate is hard-blocked (409) if the user owns any item (`current_owner_id`) or has any non-terminal request.**

**Preconditions:** M1 (User model + password_hash), M2 (`require_it_admin`, `UserRepository`, `hash_password`).

**Scope checklist:**
- [ ] Extend `UserRepository`: list with filters + manager-name join; `has_active_devices_or_requests(user_id)`.
- [ ] `UserService`: list, create (hash a default password), change_role, activate, deactivate (raise `ConflictException` per F4).
- [ ] Schemas: `UserListItem`, `CreateUserRequest`, `ChangeRoleRequest`.
- [ ] Router `users.py` (prefix `/admin/users`) + register.
- [ ] Email uniqueness →409. Tests incl. deactivate-blocked path.

**Out of scope:** login/refresh (M2); manager assignment (self-service, not an admin endpoint); password reset.

**Acceptance criteria:** `POST /admin/users` creates a user that can log in via M2; `PATCH .../deactivate` on a user with an assigned device → 409 `CONFLICT`; on a user with none → 200 and `is_active=false`; `GET /admin/users?role=manager` filters correctly with manager names populated.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M6** and `CLAUDE.md`. Build IT-Admin user management (API §13): list/create/change-role/activate/deactivate, with the F4 hard-block on deactivation. New users get the shared dev password so they can log in. Verify acceptance criteria. Mark M6 Done."

---

## M7 — Request Management & IT Approval Queue

**Goal:** IT views/filters requests, sees request detail, works the IT approval queue, and can reject/cancel/escalate-to-manager. (Assignment itself is M8.)

**Context recap (API §2, §3):**
- `GET /admin/requests` — filters `status, category_id, priority, requested_from, requested_to, search`(requester name/email); response request.* + category name + requester name; paginated.
- `GET /admin/requests/{id}` — detail with all joins + item.* if assigned.
- `GET /admin/it/approvals` — WHERE status='pending_it_approval' ORDER BY priority DESC, created_at ASC.
- `PATCH /admin/requests/{id}/reject` — body `{rejected_reason, it_decision_note}`; requires status=pending_it_approval → status=rejected, rejected_by='it_admin', it_decided_by/at set.
- `PATCH /admin/requests/{id}/cancel` — body `{rejected_reason}`; requires non-terminal → status=cancelled, cancelled_by/at, rejected_by='it_admin_cancel'.
- `PATCH /admin/requests/{id}/escalate-to-manager` — body `{manager_id?}` (default requester.manager_id); requires status=pending_it_approval AND requires_mgr_approval=false → set requires_mgr_approval=true, mgr_approval_status=pending, status=pending_mgr_approval, manager_id.

**Preconditions:** M1 (Request/User/ItemCategory/Item models), M2, M4 (DeviceLogService — reject/cancel of an unassigned request writes no device_log since no item; escalate writes none either — logs are only for device-touching actions).

**Scope checklist:**
- [ ] `RequestRepository`: filtered list + joins; approval-queue query; get-with-joins.
- [ ] `RequestService`: list, get_detail, list_it_approvals, reject, cancel, escalate_to_manager (each with status guards raising `ValidationException`/`ConflictException`).
- [ ] Schemas for filters, detail, and the three PATCH bodies.
- [ ] Router `requests.py` (prefix `/admin`) with the 6 endpoints; register.
- [ ] Tests: reject on wrong status →422/409; escalate defaults manager_id from requester; cancel sets rejected_by='it_admin_cancel'.

**Out of scope:** assign/suggested-devices/booking (M8); shipping (M9); manager approval endpoint (out of scope entirely — mgr state is set by seed or escalation only).

**Acceptance criteria:** `GET /admin/it/approvals` returns only pending_it_approval sorted by priority then oldest; `PATCH .../reject` flips a pending_it_approval request to rejected with rejected_by='it_admin'; `escalate-to-manager` moves it to pending_mgr_approval and sets mgr_approval_status=pending; cancelling a terminal request →409.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M7** and `CLAUDE.md`. Build request listing/detail (§2), IT approval queue + reject/cancel/escalate-to-manager (§3) with correct status guards and `rejected_by` values. Verify acceptance criteria. Mark M7 Done."

---

## M8 — Device Assignment & Client Direct Assign

**Goal:** The core assignment engine — suggest conflict-free devices, inspect bookings, adjust confirmed ranges, assign a device to a request, and directly assign client-owned devices (bypassing the request lifecycle). Enforces the one-active-request-per-item and date-overlap invariants.

**Context recap (API §4, §5):**
- `GET /admin/requests/{id}/suggested-devices` — available items in request.category_id, excluding date-overlap conflicts (against confirmed assigned_from/to of other active requests); response item.* + category name + `active_bookings_count`; sorted fewest active requests / longest free. (Deterministic — F11.)
- `GET /admin/items/{itemId}/bookings` — request rows WHERE assigned_item_id AND status='assigned' + requester name.
- `PATCH /admin/requests/{id}/booking-range` — body `{assigned_from, assigned_to}`; requires status=assigned; re-check overlap; email requester (stub email).
- `POST /admin/requests/{id}/assign` — body `{item_id, assigned_from, assigned_to, is_wfh}`; requires request.status=pending_it_approval, item available, category match, no overlap; sets request.assigned_item_id/dates/is_wfh/it_decided_by/at, status=assigned; item status=assigned + current_owner_id=requester; device_log `assigned` (milestone). If is_wfh → item goes to shipping first is handled in M9 (assign sets status=assigned; shipping module transitions). Confirm with WORKFLOWS: WFH outbound sets shipping_pending — decide: assign sets `assigned`, then IT triggers `/ship` (M9) which sets shipping_pending. Keep assign→`assigned`.
- `GET /admin/items/client-available` — filters `category_id, search`; owner_type=client AND status=available.
- `POST /admin/items/{itemId}/direct-assign` — body `{employee_id, assigned_from, assigned_to}`; inserts request is_client_direct=true, status=assigned; item→assigned+owner; device_log `client_assigned` (milestone).

**Preconditions:** M5 (items + status changes), M7 (request lifecycle), M4 (DeviceLogService). Understand `uq_one_active_request_per_item` (M1) — assign must not create a second active request for an item.

**Scope checklist:**
- [ ] `RequestRepository`/`ItemRepository` extensions: overlap query (`idx_request_date_range`), active-bookings count, suggested-devices query with sort.
- [ ] `AssignmentService`: suggested_devices, item_bookings, update_booking_range (overlap re-check + email stub), assign (all guards + item mutation + device_log), client_available, direct_assign.
- [ ] Overlap logic (two flavors — match the spec exactly): (a) **suggested-devices** excludes a candidate item if it has any request row where `assigned_from < request.requested_to AND assigned_to > request.requested_from` (compare candidate's existing bookings against THIS request's **requested** range); (b) **assign / booking-range** reject if the chosen dates overlap another active request's **assigned** range on that item (`assigned_from < other.assigned_to AND assigned_to > other.assigned_from`).
- [ ] Schemas for all bodies/responses (incl. `active_bookings_count`).
- [ ] Router endpoints (extend `requests.py`/`items.py` as appropriate); register.
- [ ] Tests: assign rejects non-available item (409), category mismatch (422), overlapping range (409); suggested-devices excludes conflicting items; direct-assign creates is_client_direct request + client_assigned log.

**Out of scope:** shipping transitions (M9), completing/returning (M9), support swaps (M10).

**Acceptance criteria:** `POST /admin/requests/{id}/assign` on a pending_it_approval request with an available same-category item → request.status=assigned, item.status=assigned, current_owner_id=requester, one `assigned` milestone log; a second concurrent assign of the same item to another active request → 409 (unique index); `suggested-devices` returns only conflict-free items with `active_bookings_count`; `direct-assign` writes `client_assigned`.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M8** and `CLAUDE.md`. Build the assignment engine (API §4/§5): suggested-devices (deterministic), bookings, booking-range, assign, client-available, direct-assign — enforcing category match, availability, date-overlap, and the one-active-request-per-item unique index; each device write calls `DeviceLogService`. Verify acceptance criteria. Mark M8 Done."

---

## M9 — WFH Shipping & Returns

**Goal:** The WFH outbound/return shipping legs and the return-completion gate (IT picks next status), including the auto-close-support cascade.

**Context recap (API §10, §11; WORKFLOWS §3):**
- `GET /admin/shipping/outbound` — WHERE is_wfh=true AND status=assigned AND ship_initiated_at IS NULL.
- `POST /admin/requests/{id}/ship` — body `{ship_tracking_url}`; set ship_initiated_at; item→shipping_pending; device_log `ship_outbound_initiated` (metadata tracking, not milestone).
- `POST /admin/requests/{id}/confirm-delivery` — requires item.status=shipping_pending; set ship_completed_at; item→assigned; device_log `ship_outbound_completed`.
- `GET /admin/shipping/returns` — WHERE item.status=return_shipping_pending.
- `POST /admin/requests/{id}/complete-return` — body `{next_status}` (available|under_repair|retired); requires item.status IN (assigned, return_shipping_pending); request→completed (completed_at/by, completed_next_status=next_status); item→next_status, current_owner_id=NULL; device_log `return_received` (milestone). **Cascade:** auto-close all open/in_progress support tickets for that item (auto_closed=true, status=resolved), each writing device_log `support_auto_closed` with actor_id=NULL, actor_role='system'. Also emit `assignment_completed` milestone.

**Preconditions:** M8 (assigned requests exist), M4 (DeviceLogService), M5 (item status transitions), M10 optional (support tickets to auto-close — cascade must no-op safely if none). Note the return-initiation (`return_shipping_pending`, employee-set `return_tracking_url`) is an employee/mobile action → present only via seed; IT側 only completes returns and confirms outbound.

**Scope checklist:**
- [ ] `RequestRepository` queries: outbound queue, returns queue.
- [ ] `ShippingService`: list_outbound, ship, confirm_delivery, list_returns, complete_return (+ support auto-close cascade using `SupportRepository` or a direct query; be careful not to hard-depend on M10 service — query support_request rows directly).
- [ ] Schemas for bodies/responses.
- [ ] Router `shipping.py` (prefix `/admin`) + register.
- [ ] Tests: ship sets shipping_pending + log; confirm-delivery requires shipping_pending; complete-return sets item next_status, nulls owner, completes request, auto-closes open support with system-actor logs.

**Out of scope:** support resolution (M10), extension (M11), on-site return *initiation* (IT initiates conceptually but the endpoint set here is `complete-return`; on-site returns just call complete-return directly).

**Acceptance criteria:** `POST .../ship` moves item to shipping_pending with `ship_outbound_initiated` log; `confirm-delivery` returns it to assigned; `complete-return` with next_status=available completes the request, nulls current_owner_id, writes `return_received` (milestone) + `assignment_completed`, and any open support ticket for that item becomes resolved+auto_closed with a `support_auto_closed` (actor_role=system) log.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M9** and `CLAUDE.md`. Build WFH shipping (§10) and returns (§11): outbound/ship/confirm-delivery, returns queue, complete-return with IT-chosen next_status + owner clearing + the support auto-close cascade (system-actor logs). Query support rows directly (no hard M10 dependency). Verify acceptance criteria. Mark M9 Done."

---

## M10 — Support Requests

**Goal:** IT works the support queue: list/detail, start (→in_progress, damage moves item to under_repair), and resolve with the 4 resolutions incl. the swap flow using `swapped_out`/`swapped_in`.

**Context recap (API §8; WORKFLOWS §4):**
- `GET /admin/support-requests` — filters `status, type, item_id` + item.name + requester name; order filed_at ASC.
- `GET /admin/support-requests/{id}` — detail with joins.
- `PATCH /admin/support-requests/{id}/start` — status→in_progress; if type=damage → item→under_repair + device_log `status_changed` (milestone).
- `PATCH /admin/support-requests/{id}/resolve` — body `{resolution, it_note, swapped_to_item_id?, old_item_next_status?}`:
  - `remote_resolved`: no device/status change.
  - `repaired_in_place`: item→assigned (same owner/request); device_log `status_changed` (from_value='under_repair', to_value='assigned', milestone) — this is in ADDITION to the `support_resolved` log below.
  - `swapped`: validate target item available + same category; repoint request.assigned_item_id to new item; old item→`old_item_next_status` + current_owner_id=NULL; new item→assigned + current_owner_id=requester; device_log `swapped_out` (old) + `swapped_in` (new) with metadata.
  - `marked_lost`: item→lost; complete the tied request with completed_next_status=NULL (F6).
  - All: set status=resolved, resolution, resolved_by/at; device_log `support_resolved` (milestone).

**Preconditions:** M8 (assigned items/requests to file against — via seed), M5 (item status), M4 (DeviceLogService). Swap needs a second available same-category item.

**Scope checklist:**
- [ ] `SupportRepository`: filtered list + joins; get-with-joins.
- [ ] `SupportService`: list, get_detail, start, resolve (branch per resolution with all mutations + logs). Reuse M8/M9 helpers where sensible (request-complete logic).
- [ ] Schemas incl. conditional swap fields (`swapped_to_item_id`, `old_item_next_status` required only when resolution=swapped).
- [ ] Router `support.py` (prefix `/admin`) + register.
- [ ] Tests: start on damage moves item to under_repair; repaired_in_place returns to assigned; swap repoints request + writes swapped_out/swapped_in + validates target; marked_lost sets item lost + completes request with NULL next status.

**Out of scope:** filing support tickets (employee/mobile → seed only); auto-close on return (that's M9's cascade).

**Acceptance criteria:** `PATCH .../start` on a damage ticket → item under_repair + status_changed log; `resolve` swapped with a valid same-category available target repoints `request.assigned_item_id`, sets old item to the chosen next status with owner cleared and new item assigned to requester, emitting `swapped_out`+`swapped_in`; `resolve` marked_lost sets item=lost and completes the tied request (next_status NULL); invalid swap target (wrong category / not available) →422/409.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M10** and `CLAUDE.md`. Build support queue + start + resolve (API §8) with all 4 resolutions, including the swap flow (repoint request, old/new item transitions, `swapped_out`/`swapped_in` logs) and marked_lost (item lost + complete request, next_status NULL). Verify acceptance criteria. Mark M10 Done."

---

## M11 — Extension Requests

**Goal:** IT reviews assignment end-date extension requests and approves (moves parent request's `assigned_to`) or rejects.

**Context recap (API §9; WORKFLOWS §6):**
- `GET /admin/extension-requests` — filter `status` + item.name + requester name.
- `GET /admin/extension-requests/{id}` — detail with parent request/item/requester.
- `PATCH /admin/extension-requests/{id}/approve` — body `{it_note}`; requires status=pending AND mgr_approval_status IN (not_required, approved); parent request.assigned_to→extended_to; row→approved; device_log `extension_approved` (not milestone).
- `PATCH /admin/extension-requests/{id}/reject` — body `{it_note}`; row→rejected; device_log `extension_rejected`.

**Preconditions:** M8 (assigned requests with items — extension targets them), M4 (DeviceLogService).

**Scope checklist:**
- [ ] `ExtensionRepository`: filtered list + joins (parent request → item); get-with-joins.
- [ ] `ExtensionService`: list, get_detail, approve (guard mgr_approval_status; move parent assigned_to; log), reject (log).
- [ ] Schemas for filters/detail/`{it_note}` bodies.
- [ ] Router `extensions.py` (prefix `/admin`) + register.
- [ ] Tests: approve moves parent.assigned_to to extended_to + writes extension_approved log; approve when mgr_approval_status=pending →422/409; reject writes extension_rejected.

**Out of scope:** filing extensions (employee/mobile → seed only); the parent-completes-first auto-reject rule (system behavior; enforce only if trivially co-located, otherwise leave to seed representation).

**Acceptance criteria:** `PATCH .../approve` on a pending extension with mgr_approval_status in (not_required, approved) sets the parent request's `assigned_to` to `extended_to`, sets the extension to approved, and writes an `extension_approved` device_log referencing the parent's item; approving a pending-manager extension →422/409; reject sets status=rejected + `extension_rejected` log.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M11** and `CLAUDE.md`. Build extension-request review (API §9): list/detail/approve/reject; approve moves the parent request's `assigned_to` to `extended_to` and logs `extension_approved`. Guard on mgr_approval_status. Verify acceptance criteria. Mark M11 Done."

---

## M12 — Handovers (read-only audit)

**Goal:** IT read-only visibility into peer-to-peer handover records (IT never approves handovers).

**Context recap (API §12; PROJECT rule 7):** `GET /admin/handover-requests` — filters `status, item_id` + item.name + owner/borrower names. Handovers NEVER change device status or `current_owner_id`. No IT write actions.

**Preconditions:** M1 (HandoverRequest/Item/User models), M4 (only if a handover timeline surface is desired — timeline is already M4's item endpoint; handovers appear there via seed logs).

**Scope checklist:**
- [ ] `HandoverRepository`: filtered list + joins (item name, owner name, borrower name).
- [ ] `HandoverService.list(...)`.
- [ ] Schema `HandoverListItem`.
- [ ] Router `handovers.py` (prefix `/admin`) + register. Read-only (GET only).
- [ ] Tests: list returns seeded handovers with all statuses + names; filters work.

**Out of scope:** any handover write (request/accept/reject/complete are employee/mobile → seed only); status/owner mutation (forbidden by rule 7).

**Acceptance criteria:** `GET /admin/handover-requests` returns seeded handovers (accepted/completed/rejected/cancelled/requested) with item + owner + borrower names; `?status=accepted` and `?item_id=` filter correctly; endpoint is GET-only.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M12** and `CLAUDE.md`. Build the read-only IT handover audit list (API §12) with status/item_id filters and owner/borrower/item name joins. No write endpoints. Verify acceptance criteria. Mark M12 Done."

---

## M13 — Admin Dashboard

**Goal:** Aggregate KPI endpoints for the admin landing screen.

**Context recap (API §1; FE A01):**
- `GET /admin/dashboard/summary` — `status_breakdown` = exactly these 8 keys per the spec JSON: available, assigned, under_repair, maintenance, shipping_pending, return_shipping_pending, lost, retired (do NOT add returned_to_client unless separately requested); `pending_requests_count` (status IN pending_mgr_approval, pending_it_approval), `open_support_count` (status IN open, in_progress), `active_handovers_count` (status='accepted'), `pending_extensions_count` (status='pending'). Run aggregates in parallel.
- `GET /admin/dashboard/recent-requests?limit=10` — request.* + category name + requester name, ORDER created_at DESC.
- `GET /admin/dashboard/open-support?limit=10` — support_request.* + item.name, WHERE status IN (open,in_progress), ORDER filed_at ASC.

**Preconditions:** M5 (items), M7 (requests), M10 (support), M11 (extensions), and handover data (M1/seed). Reuse existing repositories; add count queries.

**Scope checklist:**
- [ ] Count/aggregate queries (GROUP BY status for items; filtered counts for requests/support/handover/extension). Prefer a single grouped query per entity.
- [ ] `DashboardService`: summary (parallel/gathered aggregates), recent_requests, open_support.
- [ ] Schemas for the three responses.
- [ ] Router `dashboard.py` (prefix `/admin/dashboard`) + register.
- [ ] Tests against seeded data: counts are internally consistent (sum of status_breakdown == total items).

**Out of scope:** charts/time-series; QR/settings screens.

**Acceptance criteria:** `GET /admin/dashboard/summary` returns all KPI fields with counts matching the seeded dataset (status_breakdown sums to total items); `recent-requests` returns newest-first limited rows with names; `open-support` returns only open/in_progress oldest-first.

**Suggested session prompt:** "Read `_docs/IMPLEMENTATION_PLAN.md` module **M13** and `CLAUDE.md`. Build the dashboard KPI endpoints (API §1): summary (status breakdown + pending/open counts), recent-requests, open-support — reusing existing repositories with grouped count queries. Verify counts against seed. Mark M13 Done."

---

## 4. Cross-cutting Concerns

- **Auth/RBAC:** all `/admin/*` routers depend on `require_it_admin` (M2). `/auth/*` is public except `/me`. Never trust the client role — re-validate in the dependency.
- **Response shape:** every endpoint returns the standard envelope via `app/utils/response.py`. Lists use `PaginationParams`/`Page[T]` (`app/utils/pagination.py`) and populate `meta.pagination`. 204 = no body.
- **Errors:** raise `AppException` subclasses from the SERVICE layer only (`NotFoundException`/`ConflictException`/`ValidationException`/`ForbiddenException`/`UnauthorizedException`). Global handlers format them. Status-guard violations (wrong request/support state for an action) → `ConflictException`(409) or `ValidationException`(422) — be consistent: use 409 for "valid entity, wrong state", 422 for malformed input.
- **Device log discipline:** EVERY device-touching write pairs with a `DeviceLogService.append(...)` in the same transaction (M4). Milestone flag comes from the M4 event→milestone map. `actor_role='system'` + `actor_id=NULL` ONLY for `support_auto_closed`.
- **Invariants enforced by DB (M1):** one active request per item (`uq_one_active_request_per_item`), one accepted handover per item (`uq_one_active_handover_per_item`), append-only device_log (RULES). Services should still pre-check and raise friendly 409s rather than leaking IntegrityError.
- **Transactions:** `get_db_session` commits on clean return, rolls back on exception. Repositories `flush`+`refresh`, never commit. Multi-step writes in one service method share one session/transaction.
- **Layering:** router (DI aliases only) → service (logic, dataclasses, exceptions) → repository (only ORM/Redis). No cross-domain service imports where avoidable; when M9 needs support rows, query via repository rather than importing M10's service.
- **Validation:** Pydantic v2 schemas at the API boundary; enum fields typed with the Python enums from `app/models/enums.py`.
- **Testing:** pytest + pytest-asyncio (`asyncio_mode=auto`); async httpx ASGI client fixture in `tests/conftest.py`. Add integration tests per module (endpoint → DB) + unit tests for tricky service logic (overlap detection, swap flow, auto-close cascade). Run `make test`, `make lint`, `make format`, mypy (strict) before marking a module Done.
- **Email/notifications:** PROJECT mentions email on domain events; **out of scope** — where the API says "email requester" (booking-range, etc.), leave a no-op/log stub, do not build a mailer.
- **Naming:** snake_case columns/fields matching `db_schemas.dbml` exactly; router prefixes exactly as in `IT_ADMIN_API_FLOW.md` (`/admin/...`), all under `settings.API_V1_PREFIX` (`/api/v1`).
- **Module workflow:** work ONE module per session; verify preconditions first; update the Status column in the Module Index when done; don't modify another module's code without flagging it.
