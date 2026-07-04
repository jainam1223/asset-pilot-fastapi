# M7 — Request Management & IT Approval Queue

**Status:** Done
**Depends on:** M1, M2, M4
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M7 only.

## Goal

IT views/filters requests, sees request detail, works the IT approval queue, and can reject/cancel/escalate-to-manager. (Assignment itself is M8.)

## Context recap (API §2, §3)

- `GET /admin/requests` — filters `status, category_id, priority, requested_from, requested_to, search`(requester name/email); response request.* + category name + requester name; paginated.
- `GET /admin/requests/{id}` — detail with all joins + item.* if assigned.
- `GET /admin/it/approvals` — WHERE status='pending_it_approval' ORDER BY priority DESC, created_at ASC.
- `PATCH /admin/requests/{id}/reject` — body `{rejected_reason, it_decision_note}`; requires status=pending_it_approval → status=rejected, rejected_by='it_admin', it_decided_by/at set.
- `PATCH /admin/requests/{id}/cancel` — body `{rejected_reason}`; requires non-terminal → status=cancelled, cancelled_by/at, rejected_by='it_admin_cancel'.
- `PATCH /admin/requests/{id}/escalate-to-manager` — body `{manager_id?}` (default requester.manager_id); requires status=pending_it_approval AND requires_mgr_approval=false → set requires_mgr_approval=true, mgr_approval_status=pending, status=pending_mgr_approval, manager_id.

## Preconditions

M1 (Request/User/ItemCategory/Item models), M2, M4 (DeviceLogService — reject/cancel of an unassigned request writes no device_log since no item; escalate writes none either — logs are only for device-touching actions).

## Scope checklist

- [ ] `RequestRepository`: filtered list + joins; approval-queue query; get-with-joins.
- [ ] `RequestService`: list, get_detail, list_it_approvals, reject, cancel, escalate_to_manager (each with status guards raising `ValidationException`/`ConflictException`).
- [ ] Schemas for filters, detail, and the three PATCH bodies.
- [ ] Router `requests.py` (prefix `/admin`) with the 6 endpoints; register.
- [ ] Tests: reject on wrong status →422/409; escalate defaults manager_id from requester; cancel sets rejected_by='it_admin_cancel'.

## Out of scope

Assign/suggested-devices/booking (M8); shipping (M9); manager approval endpoint (out of scope entirely — mgr state is set by seed or escalation only).

## Acceptance criteria

`GET /admin/it/approvals` returns only pending_it_approval sorted by priority then oldest; `PATCH .../reject` flips a pending_it_approval request to rejected with rejected_by='it_admin'; `escalate-to-manager` moves it to pending_mgr_approval and sets mgr_approval_status=pending; cancelling a terminal request →409.

## Suggested session prompt

"Read `specs/M07_request_management_and_approval_queue.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build request listing/detail (§2), IT approval queue + reject/cancel/escalate-to-manager (§3) with correct status guards and `rejected_by` values. Verify acceptance criteria. Mark M7 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
