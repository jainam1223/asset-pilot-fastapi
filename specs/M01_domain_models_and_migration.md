# M1 — Domain Models & Migration

**Status:** Not Started
**Depends on:** — (foundation module)
**Complexity:** L

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M1 only.

## Goal

Define all 8 SQLAlchemy models + 16 enums (incl. added `swapped_out`/`swapped_in`) + the `password_hash` column on `user`, then produce ONE Alembic migration that creates every table, index, partial unique index, and the append-only RULES on `device_log`. This is the foundation for all other modules.

## Context recap — tables

(from `_docs/db_schemas.dbml`; add `TimestampMixin` = `created_at`/`updated_at timestamptz not null default now()` to every table via mixin)

- **user:** id(uuid PK), name(varchar255 NN), email(varchar255 NN UNIQUE), **password_hash(varchar255 NN — ADDED)**, role(user_role NN default employee), manager_id(uuid null FK→user.id), is_active(bool NN default true). Indexes: manager_id, role.
- **item_category:** id, name(varchar255 NN UNIQUE), description(text null), requires_mgr_approval(bool NN default false), is_active(bool NN default true).
- **item:** id, name(varchar255 NN), serial_no(varchar255 NN UNIQUE), category_id(uuid NN FK→item_category), owner_type(owner_type NN default company), client_name(varchar255 null), status(device_status NN default available), current_owner_id(uuid null FK→user), purchase_date(date null), qr_code_token(uuid NN UNIQUE default gen_random_uuid()). Indexes: status, category_id, current_owner_id, composite (category_id,status) `idx_item_available_by_category`.
- **request:** id, requester_id(NN FK→user), category_id(NN FK→item_category), assigned_item_id(null FK→item), requested_from/requested_to(timestamptz NN), assigned_from/assigned_to(timestamptz null), status(request_status NN default requested), priority(request_priority NN default medium), note(text null), requires_mgr_approval(bool NN default false), mgr_approval_status(mgr_approval_status NN default not_required), manager_id(null FK→user), manager_decision_note(text null), manager_decided_at(null), it_decided_by(null FK→user), it_decision_note(null), it_decided_at(null), rejected_by(rejected_by_enum null), rejected_reason(null), cancelled_by(null FK→user), cancelled_at(null), is_wfh(bool NN default false), ship_tracking_url(null), ship_initiated_at(null), ship_completed_at(null), return_tracking_url(null), return_initiated_at(null), completed_at(null), completed_by(null FK→user), completed_next_status(device_status null), is_client_direct(bool NN default false). Indexes: requester_id, status, assigned_item_id, category_id, (priority,created_at) `idx_request_it_queue`, **partial UNIQUE (assigned_item_id, status) `uq_one_active_request_per_item` WHERE status NOT IN ('rejected','completed','cancelled')**, (assigned_item_id, assigned_from, assigned_to) `idx_request_date_range`.
- **extension_request:** id, original_request_id(NN FK→request), requester_id(NN FK→user), current_assigned_to(timestamptz NN), extended_to(timestamptz NN), status(extension_status NN default pending), requires_mgr_approval(bool NN default false), manager_id(null FK→user), mgr_approval_status(NN default not_required), manager_note(null), manager_decided_at(null), it_decided_by(null FK→user), it_note(null), it_decided_at(null).
- **handover_request:** id, item_id(NN FK→item), owner_id(NN FK→user), borrower_id(NN FK→user), requested_duration_hours(int null), status(handover_status NN default requested), requested_at(timestamptz NN default now()), decided_at(null), completed_at(null), note(null). Indexes: item_id, borrower_id, owner_id, **partial UNIQUE (item_id, status) `uq_one_active_handover_per_item` WHERE status='accepted'**.
- **support_request:** id, item_id(NN FK→item), requester_id(NN FK→user), request_id(null FK→request), type(support_type NN), description(text NN), status(support_status NN default open), resolution(support_resolution null), it_note(null), swapped_to_item_id(null FK→item), filed_at(timestamptz NN default now()), resolved_by(null FK→user), resolved_at(null), auto_closed(bool NN default false). Indexes: item_id, status, request_id, filed_at `idx_support_open_queue`.
- **device_log (append-only):** id, item_id(NN FK→item), event_type(device_log_event NN), actor_id(null FK→user), actor_role(actor_role NN), request_id(null FK→request), support_request_id(null FK→support_request), extension_request_id(null FK→extension_request), handover_request_id(null FK→handover_request), from_value(text null), to_value(text null), note(text null), metadata(jsonb NN default '{}'::jsonb), is_milestone(bool NN default false), occurred_at(timestamptz NN default now()). Indexes: (item_id,occurred_at) `idx_device_log_item_time`, partial (item_id,occurred_at) `idx_device_log_milestones` WHERE is_milestone=true, request_id, event_type. **RULES:** `device_log_no_update` (ON UPDATE DO INSTEAD NOTHING), `device_log_no_delete` (ON DELETE DO INSTEAD NOTHING).

## Preconditions

`app/db/base.py` exports `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`. `app/models/__init__.py` is empty. `alembic/env.py` imports `app.models` + `Base.metadata`.

## Scope checklist

- [ ] One file per model in `app/models/` (e.g. `user.py`, `item_category.py`, `item.py`, `request.py`, `extension_request.py`, `handover_request.py`, `support_request.py`, `device_log.py`); define enums in `app/models/enums.py` (Python `enum.Enum`, mapped via SQLAlchemy `Enum(..., name="...")`).
- [ ] Import all models in `app/models/__init__.py` so autogenerate + relationships resolve.
- [ ] Self-referential `user.manager_id`; all FKs with correct nullability; `metadata` as JSONB (rename Python attr to avoid SQLAlchemy `metadata` clash — e.g. attribute `log_metadata`, `Column("metadata", JSONB)`).
- [ ] `make makemigrations m="create itam schema"`; review generated migration.
- [ ] Hand-add to migration: 2 partial UNIQUE indexes, `idx_device_log_milestones` partial index, and the 2 `device_log` RULES (raw `op.execute(...)` in `upgrade`, reverse in `downgrade`).
- [ ] `make migrate` (upgrade head) succeeds against a clean DB; `make migrate-down` reverses cleanly.

## Out of scope

Any repository/service/router/endpoint; seed data (M3); auth endpoints (M2).

## Acceptance criteria

`make migrate` creates all 8 tables + all enums + all indexes; `\d device_log` shows the two RULES; inserting then attempting `UPDATE`/`DELETE` on `device_log` is silently ignored (0 rows changed); a duplicate active `request` for the same `assigned_item_id` raises a unique violation; `make migrate-down` drops everything; `mypy` + `ruff` pass on `app/models/`.

## Suggested session prompt

"Read `specs/M01_domain_models_and_migration.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Implement all SQLAlchemy models + enums for the ITAM schema (8 tables incl. the added `user.password_hash` and the `swapped_out`/`swapped_in` device_log events), then generate and hand-finish the Alembic migration (partial unique indexes + device_log append-only RULES). Verify `make migrate`/`migrate-down` and the acceptance criteria. Do not build any endpoints. Mark M1 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md` when finished."
