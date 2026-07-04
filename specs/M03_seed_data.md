# M3 — Seed Data

**Status:** Done
**Depends on:** M1, M2
**Complexity:** L

> Read `specs/00_CONTEXT.md` and `CLAUDE.md` first for shared stack/conventions/enums. This file is the complete spec for M3 only.

## Goal

A Python seed script that populates a realistic demo dataset mirroring `_docs/db_seed.ts` intent, so every IT-Admin endpoint has data to operate on. Idempotent (truncate-and-reload).

## Context recap

(from `_docs/db_seed.ts`) Deterministic (fixed seed). Counts: **38 users** (5 managers, 3 it_admins, 30 employees; employees `is_active` for first 28, 2 inactive; employee `manager_id` = random manager). Emails `first.last@techcorp.internal`. **All users get a shared dev password** (e.g. `Password123!`) hashed via `hash_password`. **10 item_categories** (Laptop*, Mobile Phone*, Monitor, Keyboard, Mouse, Headset, Charger, Tablet*, Dock, Legacy[inactive]; `*`=requires_mgr_approval). **~72 items** across categories + 4 client-owned (owner_type=client, client_name from a small pool, status=assigned) + special singles (1 under_repair, 1 maintenance, 1 lost, 1 retired). **Requests** across all statuses: completed (incl. 1 WFH), assigned/active (incl. 1 shipping_pending, 1 return_shipping_pending), pending_it_approval (6), pending_mgr_approval (4), requested (3), rejected (4), cancelled (3), client-direct (≤4). **3 extension_requests** (approved/pending/rejected). **~8 support_requests** (incl. 1 auto_closed, 1 resolved-swapped chain). **6 handover_requests** (accepted/completed/rejected/cancelled + 2 simultaneous requested on one device). **device_log:** ≥1 `device_created` per item + milestone/sub-events matching each entity, incl. one `support_auto_closed` with `actor_id=NULL, actor_role=system`.

## Preconditions

M1 done (all models + migration applied). M2 done (`hash_password` available for seeded credentials).

## Scope checklist

- [x] `scripts/seed.py` (async, uses `AsyncSessionLocal`); wire a `make seed` target (and note re-runnability — truncate in FK-safe order: device_log, support_request, handover_request, extension_request, request, item, item_category, user).
- [x] Deterministic generation (fixed random seed) so the dataset is reproducible.
- [x] Respect all invariants: only one active request per item (unique index), only one accepted handover per item, valid FK targets, correct enum values, milestone flags on device_log.
- [x] Print a summary (rows per table) at the end.

## Out of scope

Any endpoint; QR PDF generation; a literal 1:1 port of the TS/Prisma code (re-implement intent in Python).

## Acceptance criteria

`make seed` on a migrated DB inserts all rows with zero FK/unique violations and can be re-run without error; counts roughly match (38 users, 10 categories, ~72 items, requests spanning all 7 statuses, 3 extensions, ~8 support, 6 handovers); `SELECT count(*) FROM device_log` > items count; the shared dev password logs in via M2.

## Suggested session prompt

"Read `specs/M03_seed_data.md` and `specs/00_CONTEXT.md` plus `CLAUDE.md`. Write `scripts/seed.py` (+ `make seed`) that reproduces the `db_seed.ts` dataset intent in async Python SQLAlchemy: 38 users (shared hashed dev password), 10 categories, ~72 items, requests across all statuses, extensions/support/handovers, and device_log entries. Respect all unique/partial-index invariants. Verify re-runnable + acceptance criteria. Mark M3 Done in this spec file and in `_docs/IMPLEMENTATION_PLAN.md`."
