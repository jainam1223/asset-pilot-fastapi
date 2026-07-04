# M9 — WFH Shipping & Returns

**Status:** Not Started
**Depends on:** M4, M8
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M9 only.

## Goal

The WFH outbound/return shipping legs and the return-completion gate (IT picks next status), including the auto-close-support cascade.

## Context recap (API §10, §11; WORKFLOWS §3)

- `GET /admin/shipping/outbound` — WHERE is_wfh=true AND status=assigned AND ship_initiated_at IS NULL.
- `POST /admin/requests/{id}/ship` — body `{ship_tracking_url}`; set ship_initiated_at; item→shipping_pending; device_log `ship_outbound_initiated` (metadata tracking, not milestone).
- `POST /admin/requests/{id}/confirm-delivery` — requires item.status=shipping_pending; set ship_completed_at; item→assigned; device_log `ship_outbound_completed`.
- `GET /admin/shipping/returns` — WHERE item.status=return_shipping_pending.
- `POST /admin/requests/{id}/complete-return` — body `{next_status}` (available|under_repair|retired); requires item.status IN (assigned, return_shipping_pending); request→completed (completed_at/by, completed_next_status=next_status); item→next_status, current_owner_id=NULL; device_log `return_received` (milestone). **Cascade:** auto-close all open/in_progress support tickets for that item (auto_closed=true, status=resolved), each writing device_log `support_auto_closed` with actor_id=NULL, actor_role='system'. Also emit `assignment_completed` milestone.

## Preconditions

M8 (assigned requests exist), M4 (DeviceLogService), M5 (item status transitions), M10 optional (support tickets to auto-close — cascade must no-op safely if none). Note the return-initiation (`return_shipping_pending`, employee-set `return_tracking_url`) is an employee/mobile action → present only via seed; IT side only completes returns and confirms outbound.

## Scope checklist

- [ ] `RequestRepository` queries: outbound queue, returns queue.
- [ ] `ShippingService`: list_outbound, ship, confirm_delivery, list_returns, complete_return (+ support auto-close cascade using `SupportRepository` or a direct query; be careful not to hard-depend on M10 service — query support_request rows directly).
- [ ] Schemas for bodies/responses.
- [ ] Router `shipping.py` (prefix `/admin`) + register.
- [ ] Tests: ship sets shipping_pending + log; confirm-delivery requires shipping_pending; complete-return sets item next_status, nulls owner, completes request, auto-closes open support with system-actor logs.

## Out of scope

Support resolution (M10), extension (M11), on-site return *initiation* (IT initiates conceptually but the endpoint set here is `complete-return`; on-site returns just call complete-return directly).

## Acceptance criteria

`POST .../ship` moves item to shipping_pending with `ship_outbound_initiated` log; `confirm-delivery` returns it to assigned; `complete-return` with next_status=available completes the request, nulls current_owner_id, writes `return_received` (milestone) + `assignment_completed`, and any open support ticket for that item becomes resolved+auto_closed with a `support_auto_closed` (actor_role=system) log.

## Suggested session prompt

"Read `specs/M09_wfh_shipping_and_returns.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build WFH shipping (§10) and returns (§11): outbound/ship/confirm-delivery, returns queue, complete-return with IT-chosen next_status + owner clearing + the support auto-close cascade (system-actor logs). Query support rows directly (no hard M10 dependency). Verify acceptance criteria. Mark M9 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
