# M4 — Device Audit Log (service + timeline)

**Status:** Done
**Depends on:** M1
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M4 only.

## Goal

A shared, reusable `DeviceLogService.append(...)` that ALL device-touching modules (M5, M7–M11) call to write `device_log` rows correctly (event type, actor, milestone flag, linked request/support/extension/handover ids, from/to values, jsonb metadata), plus the read-side timeline endpoint.

## Context recap

`device_log` schema in M1. Milestone events (surfaced in timeline `milestones_only=true`): assigned, client_assigned, return_received, assignment_completed, support_opened, support_resolved, handover_accepted, handover_completed, status_changed, marked_lost, retired, returned_to_client. Non-milestone: device_created, device_edited, ship_*, extension_*, handover_requested/rejected/cancelled, swapped_out/swapped_in (per API metadata). **API §7:** `GET /admin/items/{itemId}/timeline?milestones_only=<bool default true>` → device_log rows ordered `occurred_at ASC`.

## Preconditions

M1 done (`DeviceLog` model). M2 done (`require_it_admin`).

## Scope checklist

- [ ] `DeviceLogRepository` (subclass base) with `list_for_item(item_id, milestones_only, pagination)` ordered `occurred_at ASC`.
- [ ] `DeviceLogService.append(*, item_id, event_type, actor_id, actor_role, request_id=None, support_request_id=None, extension_request_id=None, handover_request_id=None, from_value=None, to_value=None, note=None, metadata=None, is_milestone=None)` — if `is_milestone` is None, derive from an event→milestone map defined here (single source of truth).
- [ ] `get_timeline(item_id, milestones_only)` service method + schema `DeviceLogEntryResponse`.
- [ ] Router endpoint `GET /admin/items/{itemId}/timeline`. (Router file may be shared with M5's items router; if M5 not built yet, create `items.py` and M5 extends it.)
- [ ] DI wiring `get_device_log_repository`, `get_device_log_service`, `DeviceLogServiceDep`. Design `append` so other services receive `DeviceLogService` via DI and call it within the same request/session (writes flushed, committed by `get_db_session`).
- [ ] Tests: append writes a row with correct milestone flag; timeline returns milestone-only vs full correctly ordered.

## Out of scope

Inventory CRUD (M5), any write that produces logs (those live in their own modules and CALL this service).

## Acceptance criteria

`DeviceLogService.append(...)` inserts a row with correct `is_milestone` from the map; `GET /api/v1/admin/items/{seeded_item}/timeline` returns milestone rows ordered oldest→newest; `?milestones_only=false` returns all rows including sub-events.

## Suggested session prompt

"Read `specs/M04_device_audit_log.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build the shared `DeviceLogService.append(...)` (event→milestone map as single source of truth), `DeviceLogRepository`, and the `GET /admin/items/{itemId}/timeline` endpoint. Wire DI so later services inject `DeviceLogService`. Verify acceptance criteria. Mark M4 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
