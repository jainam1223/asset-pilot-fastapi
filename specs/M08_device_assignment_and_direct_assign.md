# M8 — Device Assignment & Client Direct Assign

**Status:** Not Started
**Depends on:** M4, M5, M7
**Complexity:** L

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M8 only.

## Goal

The core assignment engine — suggest conflict-free devices, inspect bookings, adjust confirmed ranges, assign a device to a request, and directly assign client-owned devices (bypassing the request lifecycle). Enforces the one-active-request-per-item and date-overlap invariants.

## Context recap (API §4, §5)

- `GET /admin/requests/{id}/suggested-devices` — available items in request.category_id, excluding date-overlap conflicts (against confirmed assigned_from/to of other active requests); response item.* + category name + `active_bookings_count`; sorted fewest active requests / longest free. (Deterministic — F11.)
- `GET /admin/items/{itemId}/bookings` — request rows WHERE assigned_item_id AND status='assigned' + requester name.
- `PATCH /admin/requests/{id}/booking-range` — body `{assigned_from, assigned_to}`; requires status=assigned; re-check overlap; email requester (stub email).
- `POST /admin/requests/{id}/assign` — body `{item_id, assigned_from, assigned_to, is_wfh}`; requires request.status=pending_it_approval, item available, category match, no overlap; sets request.assigned_item_id/dates/is_wfh/it_decided_by/at, status=assigned; item status=assigned + current_owner_id=requester; device_log `assigned` (milestone). If is_wfh → item goes to shipping first is handled in M9. Assign always sets status=`assigned`; the shipping module (M9) handles the transition into `shipping_pending` via its own endpoint.
- `GET /admin/items/client-available` — filters `category_id, search`; owner_type=client AND status=available.
- `POST /admin/items/{itemId}/direct-assign` — body `{employee_id, assigned_from, assigned_to}`; inserts request is_client_direct=true, status=assigned; item→assigned+owner; device_log `client_assigned` (milestone).

## Preconditions

M5 (items + status changes), M7 (request lifecycle), M4 (DeviceLogService). Understand `uq_one_active_request_per_item` (M1) — assign must not create a second active request for an item.

## Scope checklist

- [ ] `RequestRepository`/`ItemRepository` extensions: overlap query (`idx_request_date_range`), active-bookings count, suggested-devices query with sort.
- [ ] `AssignmentService`: suggested_devices, item_bookings, update_booking_range (overlap re-check + email stub), assign (all guards + item mutation + device_log), client_available, direct_assign.
- [ ] Overlap logic (two flavors — match the spec exactly): (a) **suggested-devices** excludes a candidate item if it has any request row where `assigned_from < request.requested_to AND assigned_to > request.requested_from` (compare candidate's existing bookings against THIS request's **requested** range); (b) **assign / booking-range** reject if the chosen dates overlap another active request's **assigned** range on that item (`assigned_from < other.assigned_to AND assigned_to > other.assigned_from`).
- [ ] Schemas for all bodies/responses (incl. `active_bookings_count`).
- [ ] Router endpoints (extend `requests.py`/`items.py` as appropriate); register.
- [ ] Tests: assign rejects non-available item (409), category mismatch (422), overlapping range (409); suggested-devices excludes conflicting items; direct-assign creates is_client_direct request + client_assigned log.

## Out of scope

Shipping transitions (M9), completing/returning (M9), support swaps (M10).

## Acceptance criteria

`POST /admin/requests/{id}/assign` on a pending_it_approval request with an available same-category item → request.status=assigned, item.status=assigned, current_owner_id=requester, one `assigned` milestone log; a second concurrent assign of the same item to another active request → 409 (unique index); `suggested-devices` returns only conflict-free items with `active_bookings_count`; `direct-assign` writes `client_assigned`.

## Suggested session prompt

"Read `specs/M08_device_assignment_and_direct_assign.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build the assignment engine (API §4/§5): suggested-devices (deterministic), bookings, booking-range, assign, client-available, direct-assign — enforcing category match, availability, date-overlap, and the one-active-request-per-item unique index; each device write calls `DeviceLogService`. Verify acceptance criteria. Mark M8 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
