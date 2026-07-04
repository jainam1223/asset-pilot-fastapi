# M13 — Admin Dashboard

**Status:** Done
**Depends on:** M5, M7, M9, M10, M11
**Complexity:** M

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M13 only.

## Goal

Aggregate KPI endpoints for the admin landing screen.

## Context recap (API §1; FE A01)

- `GET /admin/dashboard/summary` — `status_breakdown` = exactly these 8 keys per the spec JSON: available, assigned, under_repair, maintenance, shipping_pending, return_shipping_pending, lost, retired (do NOT add returned_to_client unless separately requested); `pending_requests_count` (status IN pending_mgr_approval, pending_it_approval), `open_support_count` (status IN open, in_progress), `active_handovers_count` (status='accepted'), `pending_extensions_count` (status='pending'). Run aggregates in parallel.
- `GET /admin/dashboard/recent-requests?limit=10` — request.* + category name + requester name, ORDER created_at DESC.
- `GET /admin/dashboard/open-support?limit=10` — support_request.* + item.name, WHERE status IN (open,in_progress), ORDER filed_at ASC.

## Preconditions

M5 (items), M7 (requests), M10 (support), M11 (extensions), and handover data (M1/seed). Reuse existing repositories; add count queries.

## Scope checklist

- [x] Count/aggregate queries (GROUP BY status for items; filtered counts for requests/support/handover/extension). Prefer a single grouped query per entity.
- [x] `DashboardService`: summary (parallel/gathered aggregates), recent_requests, open_support.
- [x] Schemas for the three responses.
- [x] Router `dashboard.py` (prefix `/admin/dashboard`) + register.
- [x] Tests against seeded data: counts are internally consistent (sum of status_breakdown == total items).

## Out of scope

Charts/time-series; QR/settings screens.

## Acceptance criteria

`GET /admin/dashboard/summary` returns all KPI fields with counts matching the seeded dataset (status_breakdown sums to total items); `recent-requests` returns newest-first limited rows with names; `open-support` returns only open/in_progress oldest-first.

## Suggested session prompt

"Read `specs/M13_admin_dashboard.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Build the dashboard KPI endpoints (API §1): summary (status breakdown + pending/open counts), recent-requests, open-support — reusing existing repositories with grouped count queries. Verify counts against seed. Mark M13 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
