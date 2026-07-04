# M10 — Support Requests

**Status:** Not Started
**Depends on:** M4, M5, M8
**Complexity:** L

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M10 only.

## Goal

IT works the support queue: list/detail, start (→in_progress, damage moves item to under_repair), and resolve with the 4 resolutions incl. the swap flow using `swapped_out`/`swapped_in`.

## Context recap (API §8; WORKFLOWS §4)

- `GET /admin/support-requests` — filters `status, type, item_id` + item.name + requester name; order filed_at ASC.
- `GET /admin/support-requests/{id}` — detail with joins.
- `PATCH /admin/support-requests/{id}/start` — status→in_progress; if type=damage → item→under_repair + device_log `status_changed` (milestone).
- `PATCH /admin/support-requests/{id}/resolve` — body `{resolution, it_note, swapped_to_item_id?, old_item_next_status?}`:
  - `remote_resolved`: no device/status change.
  - `repaired_in_place`: item→assigned (same owner/request); device_log `status_changed` (from_value='under_repair', to_value='assigned', milestone) — this is in ADDITION to the `support_resolved` log below.
  - `swapped`: validate target item available + same category; repoint request.assigned_item_id to new item; old item→`old_item_next_status` + current_owner_id=NULL; new item→assigned + current_owner_id=requester; device_log `swapped_out` (old) + `swapped_in` (new) with metadata.
  - `marked_lost`: item→lost; complete the tied request with completed_next_status=NULL (F6, see `00_CONTEXT.md`).
  - All: set status=resolved, resolution, resolved_by/at; device_log `support_resolved` (milestone).

## Preconditions

M8 (assigned items/requests to file against — via seed), M5 (item status), M4 (DeviceLogService). Swap needs a second available same-category item.

## Scope checklist

- [ ] `SupportRepository`: filtered list + joins; get-with-joins.
- [ ] `SupportService`: list, get_detail, start, resolve (branch per resolution with all mutations + logs). Reuse M8/M9 helpers where sensible (request-complete logic).
- [ ] Schemas incl. conditional swap fields (`swapped_to_item_id`, `old_item_next_status` required only when resolution=swapped).
- [ ] Router `support.py` (prefix `/admin`) + register.
- [ ] Tests: start on damage moves item to under_repair; repaired_in_place returns to assigned; swap repoints request + writes swapped_out/swapped_in + validates target; marked_lost sets item lost + completes request with NULL next status.

## Out of scope

Filing support tickets (employee/mobile → seed only); auto-close on return (that's M9's cascade).

## Acceptance criteria

`PATCH .../start` on a damage ticket → item under_repair + status_changed log; `resolve` swapped with a valid same-category available target repoints `request.assigned_item_id`, sets old item to the chosen next status with owner cleared and new item assigned to requester, emitting `swapped_out`+`swapped_in`; `resolve` marked_lost sets item=lost and completes the tied request (next_status NULL); invalid swap target (wrong category / not available) →422/409.

## Suggested session prompt

"Read `specs/M10_support_requests.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build support queue + start + resolve (API §8) with all 4 resolutions, including the swap flow (repoint request, old/new item transitions, `swapped_out`/`swapped_in` logs) and marked_lost (item lost + complete request, next_status NULL). Verify acceptance criteria. Mark M10 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
