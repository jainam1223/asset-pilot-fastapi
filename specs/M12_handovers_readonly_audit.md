# M12 — Handovers (read-only audit)

**Status:** Not Started
**Depends on:** M1, M4
**Complexity:** S

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M12 only.

## Goal

IT read-only visibility into peer-to-peer handover records (IT never approves handovers).

## Context recap (API §12; PROJECT rule 7)

`GET /admin/handover-requests` — filters `status, item_id` + item.name + owner/borrower names. Handovers NEVER change device status or `current_owner_id`. No IT write actions.

## Preconditions

M1 (HandoverRequest/Item/User models), M4 (only if a handover timeline surface is desired — timeline is already M4's item endpoint; handovers appear there via seed logs).

## Scope checklist

- [ ] `HandoverRepository`: filtered list + joins (item name, owner name, borrower name).
- [ ] `HandoverService.list(...)`.
- [ ] Schema `HandoverListItem`.
- [ ] Router `handovers.py` (prefix `/admin`) + register. Read-only (GET only).
- [ ] Tests: list returns seeded handovers with all statuses + names; filters work.

## Out of scope

Any handover write (request/accept/reject/complete are employee/mobile → seed only); status/owner mutation (forbidden by rule 7).

## Acceptance criteria

`GET /admin/handover-requests` returns seeded handovers (accepted/completed/rejected/cancelled/requested) with item + owner + borrower names; `?status=accepted` and `?item_id=` filter correctly; endpoint is GET-only.

## Suggested session prompt

"Read `specs/M12_handovers_readonly_audit.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build the read-only IT handover audit list (API §12) with status/item_id filters and owner/borrower/item name joins. No write endpoints. Verify acceptance criteria. Mark M12 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
