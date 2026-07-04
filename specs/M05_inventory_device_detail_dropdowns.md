# M5 — Inventory, Device Detail & Dropdowns

**Status:** Done
**Depends on:** M1, M2, M4
**Complexity:** L

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M5 only.

## Goal

Device inventory CRUD, status changes (each logged), the composite device-detail view, and the shared dropdown endpoints.

## Context recap (API §6, §7, §14)

- `GET /admin/items` — filters `category_id, status, owner_type, search`(name/serial_no); response item.* + category name + current_owner name; paginated.
- `POST /admin/items` — body `{name, serial_no, category_id, owner_type, client_name, purchase_date}`; device_log `device_created` (not milestone, to_value=available, actor it_admin).
- `PATCH /admin/items/{itemId}` — body `{name, category_id, client_name, purchase_date}`; device_log `device_edited` (not milestone, metadata field/old/new).
- `PATCH /admin/items/{itemId}/status` — body `{status, it_note}`; event map: lost→`marked_lost`, retired→`retired`, returned_to_client→`returned_to_client`, else→`status_changed`; always milestone, actor it_admin. No auto Lost→Retired.
- `GET /admin/items/{itemId}` — `{item, category, current_owner, current_request, open_support[], active_handover}`.
- `GET /admin/dropdowns/item-categories` (is_active=true), `/managers` (role=manager AND is_active), `/employees` (role=employee AND is_active).

## Preconditions

M1 (Item/ItemCategory/User models), M2 (`require_it_admin`), M4 (`DeviceLogService`). Note: `current_request`, `open_support`, `active_handover` on the detail view depend on request/support/handover tables existing (M1 has them) — return empty/null gracefully if those modules' writes haven't populated data yet.

## Scope checklist

- [ ] `ItemRepository` (filters + search + joins for category/owner names), `ItemCategoryRepository`.
- [ ] `InventoryService`: list, create (+log), edit (+log with diff metadata), change_status (+mapped log), get_detail (assemble composite).
- [ ] Schemas for each request/response shape above.
- [ ] Router `items.py` (extends M4's if present): the 5 item endpoints; `dropdowns.py` for the 3 dropdowns.
- [ ] Validation: `serial_no` unique (→409 `CONFLICT`); `client_name` required only when `owner_type=client`; unknown id →404.
- [ ] DI wiring + tests (create/edit/status transitions produce correct device_log events).

## Out of scope

Assignment/return status changes driven by request lifecycle (M8/M9 set item.status through their own services); QR management (see F7 in `00_CONTEXT.md`).

## Acceptance criteria

`POST /admin/items` returns 201 with the item + writes a `device_created` log; `PATCH .../status` with `status=lost` writes a `marked_lost` milestone and does NOT auto-retire; `GET /admin/items/{id}` returns the composite with category + current_owner; `GET /admin/items?search=<serial>` filters correctly; dropdowns return only active rows.

## Suggested session prompt

"Read `specs/M05_inventory_device_detail_dropdowns.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build inventory CRUD + status change + composite device detail (API §6/§7) and the 3 dropdown endpoints (§14), each device-mutating write calling `DeviceLogService`. Verify acceptance criteria. Mark M5 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
