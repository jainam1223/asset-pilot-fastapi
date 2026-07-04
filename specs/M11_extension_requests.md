# M11 — Extension Requests

**Status:** Not Started
**Depends on:** M4, M8
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M11 only.

## Goal

IT reviews assignment end-date extension requests and approves (moves parent request's `assigned_to`) or rejects.

## Context recap (API §9; WORKFLOWS §6)

- `GET /admin/extension-requests` — filter `status` + item.name + requester name.
- `GET /admin/extension-requests/{id}` — detail with parent request/item/requester.
- `PATCH /admin/extension-requests/{id}/approve` — body `{it_note}`; requires status=pending AND mgr_approval_status IN (not_required, approved); parent request.assigned_to→extended_to; row→approved; device_log `extension_approved` (not milestone).
- `PATCH /admin/extension-requests/{id}/reject` — body `{it_note}`; row→rejected; device_log `extension_rejected`.

## Preconditions

M8 (assigned requests with items — extension targets them), M4 (DeviceLogService).

## Scope checklist

- [ ] `ExtensionRepository`: filtered list + joins (parent request → item); get-with-joins.
- [ ] `ExtensionService`: list, get_detail, approve (guard mgr_approval_status; move parent assigned_to; log), reject (log).
- [ ] Schemas for filters/detail/`{it_note}` bodies.
- [ ] Router `extensions.py` (prefix `/admin`) + register.
- [ ] Tests: approve moves parent.assigned_to to extended_to + writes extension_approved log; approve when mgr_approval_status=pending →422/409; reject writes extension_rejected.

## Out of scope

Filing extensions (employee/mobile → seed only); the parent-completes-first auto-reject rule (system behavior; enforce only if trivially co-located, otherwise leave to seed representation).

## Acceptance criteria

`PATCH .../approve` on a pending extension with mgr_approval_status in (not_required, approved) sets the parent request's `assigned_to` to `extended_to`, sets the extension to approved, and writes an `extension_approved` device_log referencing the parent's item; approving a pending-manager extension →422/409; reject sets status=rejected + `extension_rejected` log.

## Suggested session prompt

"Read `specs/M11_extension_requests.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build extension-request review (API §9): list/detail/approve/reject; approve moves the parent request's `assigned_to` to `extended_to` and logs `extension_approved`. Guard on mgr_approval_status. Verify acceptance criteria. Mark M11 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
