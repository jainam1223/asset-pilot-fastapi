# API Audit Report — AssetPilot ITAM Backend
**Date:** 2026-07-05  
**Scope:** Full IT Admin API surface vs. design (A01–A14) + specification (IT_ADMIN_API_FLOW.md, IMPLEMENTATION_PLAN.md)  
**Audit Method:** 9 parallel agents, each deep-diving one design-page group with live API testing, code review, and spec cross-check.

---

## Executive Summary

**Result: 8 of 9 module groups PASS; 1 module has critical security issue + 2 gaps.**

| Group | Pages | Module | Status | Summary |
|-------|-------|--------|--------|---------|
| G1 | A01 | Auth + Dashboard | 🔴 PASS + CRITICAL ISSUE | `/auth/register` is unguarded privilege escalation; dashboard endpoints correct |
| G2 | A02–A03 | Requests/Approval/Assignment | ✅ PASS | All 9 endpoints correct; overlap formulas verified distinct |
| G3 | A04–A06 | Inventory/Timeline/Dropdowns | ✅ PASS | All CRUD + timeline + dropdowns correct; append-only enforced |
| G4 | A07 | Direct Client Assignment | 🟡 PASS + 2 GAPS | Happy path works; missing employee validation + overlap check |
| G5 | A08, A10 | Support Requests | ✅ PASS | All 4 resolve branches correct; A10 is FE-filtered view only |
| G6 | A09 | Shipping & Returns | ✅ PASS | All 5 endpoints correct; cascade query/logging verified; production-ready |
| G7 | A11 | Extension Requests | ✅ PASS | Cross-entity mutation verified; guards correct; no design gaps |
| G8 | A12 | Handovers | ✅ PASS | Read-only audit fully compliant; self-join correct |
| G9 | A13–A14 | Users/QR/Settings | ✅ PASS | F4 deactivate guard correct; A13/A14 out-of-scope confirmed intentional |

---

## Finding Severity Breakdown

### 🔴 CRITICAL (Immediate Action Required)

#### 1. `/auth/register` is an unauthenticated privilege escalation endpoint
**Severity:** CRITICAL SECURITY HOLE  
**Module:** G1 (Auth + Dashboard, M2 Auth)  
**File:** `app/api/v1/routers/auth.py:13–23` (router definition); `app/services/auth_service.py:70–88` (service)  
**Finding:** The endpoint accepts `role: UserRole` directly from the client body and mints a valid access_token for any role, including `it_admin`, with zero authentication, rate limiting, or role restriction.

**Live Exploit (Confirmed):**
```bash
# Any anonymous attacker:
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Attacker","email":"attacker@example.com","role":"it_admin","password":"any"}'
# Response: HTTP 201 with valid access_token + refresh_token

# Token then grants full admin access:
curl http://localhost:8000/api/v1/admin/dashboard/summary \
  -H "Authorization: Bearer <token from above>"
# Response: HTTP 200 with full IT-Admin KPI data
```

**Spec Contradiction:**
- `_docs/IMPLEMENTATION_PLAN.md` M2 explicitly lists "registration (not needed — users come from seed/M6)" as **out of scope**
- `_docs/IT_ADMIN_API_FLOW.md` has **zero mention** of a `POST /auth/register` endpoint
- Design mockup (`IT_ADMIN_FE_DESIGN.html`) has no login/registration screen for IT Admin
- `_docs/API_DOCUMENTATION.md:1067–1068` flags this as **unresolved**: "confirm with backend whether FE should ever call it directly"

**Zero Test Coverage:** `grep -rn "register" tests/` returns no integration or unit test for `/auth/register` (only matches on `register_exception_handlers`, unrelated).

**Recommendation:** DELETE the endpoint, or HARD-RESTRICT it to `require_it_admin`-protected user creation (i.e., make IT-Admin-only or move logic to `POST /admin/users`, which already exists and IS properly guarded). Current state is an exploitable hole.

---

### 🟡 HIGH (Should Fix)

#### 2. Direct-assign has no date-range overlap protection (inconsistent with regular assign)
**Severity:** HIGH — Operationally risky; architectural inconsistency  
**Module:** G4 (Direct Client Assignment, M8)  
**File:** `app/services/assignment_service.py:343–395` (direct_assign service method)  
**Finding:** `POST /admin/items/{itemId}/direct-assign` does NOT check for date-range overlaps with other active assignments on the same device, while `POST /admin/requests/{id}/assign` (regular flow) DOES (lines 300–305).

**Why It Matters:** Two direct-assigns on the same device with overlapping dates both succeed, creating an impossible physical state (device can't be in two places at once). The unique index `uq_one_active_request_per_item` only prevents duplicate ACTIVE requests with identical status — it does NOT prevent overlapping date ranges.

**Spec Context:** `_docs/IT_ADMIN_API_FLOW.md` §5 (Direct Client Assignment) does NOT mention overlap checking, while §4 (Device Assignment) explicitly validates. Appears intentional but risky. Spec is silent on whether this is "emergency fast-path feature" or oversight.

**Recommendation:** Add overlap check (mirror regular assign lines 300–305) OR document explicitly in spec that direct-assign intentionally skips overlaps (emergency reassignments, etc.) and accept risk. Current state is silently inconsistent.

---

### 🟡 MEDIUM (Should Fix)

#### 3. Direct-assign does not validate employee `is_active` or role
**Severity:** MEDIUM — Operational hygiene gap  
**Module:** G4 (Direct Client Assignment, M8)  
**File:** `app/services/assignment_service.py:358–360` (guard clause)  
**Finding:** `direct_assign()` validates employee exists but NOT whether `is_active==true` or `role==UserRole.EMPLOYEE`. Allows assigning to inactive users, IT admins, or managers.

**Test Case:** Calling `POST /admin/items/{id}/direct-assign` with `employee_id` of a deactivated user succeeds (should block). Code only checks existence.

**Recommendation:** Add 2 guards:
```python
if not employee.is_active:
    raise ConflictException(message="Only active employees can be assigned devices.")
if employee.role != UserRole.EMPLOYEE:
    raise ValidationException(message="Only employees can be assigned devices.")
```

---

## Design Gaps (Not Code Bugs)

### G1: Dashboard KPI computation gaps
- **"Total devices" tile:** No dedicated endpoint field. FE must sum the 8 `status_breakdown` keys. Silently excludes `returned_to_client` status. Currently ~0 such items, but architecturally fragile (documented in `_docs/API_DOCUMENTATION.md:205`).
- **"In transit" KPI:** No backing field. FE must compute as `shipping_pending + return_shipping_pending`. (Expected design; not a bug.)
- **"Pending Actions" panel** (Approvals / Awaiting shipment / Returns to confirm): No dedicated dashboard fields. FE must derive from separate paginated list calls (e.g., `GET /admin/requests?status=...` or dedicated shipping queues). Contrary to impression that 3 dashboard calls suffice for A01.

### G4: Direct-assign UX lacks availability affordance
- Design A07 mockup shows date-picker form with no "check availability" button. Consistent with spec (intentional fast-path), but operationally risky if overlaps occur.

### G5: A10 Maintenance page scope
- Design A10 shows device status-change actions (Repair/Available transitions) but is **not a separate backend feature** — it's a filtered/styled view of M5 Inventory CRUD endpoints. No additional endpoints needed. Clarified in design context.

### G6: A09 Shipping/Returns visual distinction
- Returns queue endpoint filters `item.status='return_shipping_pending'` only (WFH path). On-site returns use same complete-return endpoint but must be routed via `request.is_wfh` flag. Design mockup doesn't distinguish; FE must handle both paths via flag. Backend provides flag; no API gap.

### G3: Timeline event description mapping
- API returns raw event_type strings (`marked_lost`, `ship_outbound_initiated`, etc.). Design A06 mockup shows human-readable descriptions ("Marked as lost", "Shipped to home address", etc.). FE owns descriptions/localization. API provides data needed. Expected division of responsibility.

### G9: A13 QR Management & A14 Category CRUD confirmed out of scope
- **A13:** Design shows Export PDF, Print, Regenerate QR actions. **Zero backend endpoints** (`POST/PATCH /admin/qr*`). Intentional per `_docs/IMPLEMENTATION_PLAN.md` F7 ("out of scope for all modules unless separately requested"). Only `item.qr_code_token` field is available (read-only).
- **A14:** Design shows Category CRUD tab (Create, Edit, Deactivate, toggle `requires_mgr_approval`). **Zero backend endpoints** (`POST/PATCH/DELETE /admin/categories`). Only read-only dropdown `GET /admin/dropdowns/item-categories` exists. Intentional per F7. Scope decision was deliberate; not a bug.

---

## Module-by-Module Results

### ✅ PASS: G2 — Requests, IT Approval, Assignment (M7/M8)
**Verdict:** Fully compliant. All 9 endpoints correct.
- `GET /admin/requests` ✓ — Filters (status, category_id, priority, requested_from/to, search), pagination, joins work correctly
- `GET /admin/requests/{id}` ✓ — Detail includes all required name joins
- `GET /admin/it/approvals` ✓ — WHERE status=pending_it_approval, ORDER BY priority DESC, created_at ASC
- `PATCH .../reject` ✓ — 409 guard on wrong status
- `PATCH .../cancel` ✓ — Rejects terminal states with 409; sets rejected_by=IT_ADMIN_CANCEL (correct enum value)
- `PATCH .../escalate-to-manager` ✓ — Defaults to requester.manager_id; guards both status and requires_mgr_approval
- `GET .../suggested-devices` ✓ — Overlap formula uses REQUESTED range (distinct from assign's ASSIGNED range); sorts by active_bookings_count ASC
- `PATCH .../booking-range` ✓ — Re-validates overlap against ASSIGNED range (distinct formula per spec)
- `POST .../assign` ✓ — All 4 preconditions (status, availability, category, overlap); mutations; device_log with is_milestone=true
- **Files:** `app/api/v1/routers/requests.py`, `app/services/request_service.py`, `app/services/assignment_service.py`, repositories

---

### ✅ PASS: G3 — Inventory, Device Detail, Timeline, Dropdowns (M5)
**Verdict:** Fully compliant. All CRUD + timeline + dropdowns correct.
- `GET /admin/items` ✓ — Filters (category_id, status, owner_type, search), pagination
- `POST /admin/items` ✓ — Validates client_name only with owner_type=client; rejects duplicate serial as 409; logs device_created (not milestone)
- `PATCH /admin/items/{id}` ✓ — Logs device_edited with field-level diff metadata
- `PATCH /admin/items/{id}/status` ✓ — Event mapping: lost→marked_lost, retired→retired, returned_to_client→returned_to_client, else→status_changed; is_milestone=true; NO auto Lost→Retired cascade
- `GET /admin/items/{id}` ✓ — Composite response (item, category, current_owner, current_request, open_support[], active_handover) with proper null-safety
- `GET /admin/items/{id}/timeline` ✓ — milestones_only filter works; ORDER BY occurred_at ASC; append-only RULES in place (Postgres: UPDATE→INSTEAD NOTHING, DELETE→INSTEAD NOTHING)
- `GET /admin/dropdowns/item-categories` ✓ — Filters is_active=true
- `GET /admin/dropdowns/managers` ✓ — Filters role=manager AND is_active=true
- `GET /admin/dropdowns/employees` ✓ — Filters role=employee AND is_active=true
- **Files:** `app/api/v1/routers/items.py`, `app/services/inventory_service.py`, `app/services/device_log_service.py`, repositories, `alembic/versions/19fa64831348_create_itam_schema.py:254–258` (RULES)

---

### ✅ PASS: G5 — Support Requests (M10)
**Verdict:** Fully compliant. All 4 resolve branches correct.
- `GET /admin/support-requests` ✓ — Filters (status, type, item_id); ORDER BY filed_at ASC
- `GET /admin/support-requests/{id}` ✓ — Joins item.name, requester.name
- `PATCH .../start` ✓ — ONLY on type=damage: item→under_repair, logs status_changed (milestone). For other types: no item mutation.
- `PATCH .../resolve` ✓ — All 4 branches (remote_resolved, repaired_in_place, swapped, marked_lost):
  - **remote_resolved:** No change (1 support_resolved log)
  - **repaired_in_place:** Item→assigned (2 logs: status_changed + support_resolved, both milestone)
  - **swapped:** Request repointed, old item→chosen next status, new item→assigned, old_item_next_status NOT validated for category/availability (guards in place; 3 logs: swapped_out + swapped_in + support_resolved)
  - **marked_lost:** Item→lost, request→completed with `completed_next_status=NULL` (exact NULL per spec F6; 2 logs: marked_lost + support_resolved)
- **A10 Maintenance:** Confirmed as FE-filtered view of inventory (no separate backend feature needed)
- **Files:** `app/api/v1/routers/support.py`, `app/services/support_service.py`, repositories

---

### ✅ PASS: G6 — WFH Shipping & Returns (M9)
**Verdict:** Production-ready. All 5 endpoints correct.
- `GET /admin/shipping/outbound` ✓ — WHERE is_wfh=true AND status=assigned AND ship_initiated_at IS NULL
- `POST .../ship` ✓ — Sets ship_tracking_url, ship_initiated_at; item→shipping_pending; logs ship_outbound_initiated (non-milestone)
- `POST .../confirm-delivery` ✓ — item.status=shipping_pending precondition; item→assigned; logs ship_outbound_completed
- `GET /admin/shipping/returns` ✓ — WHERE item.status=return_shipping_pending
- `POST .../complete-return` ✓ — Accepts both status=assigned (on-site) and return_shipping_pending (WFH); next_status enum validation (422 on invalid); request→completed with completed_next_status set to next_status; item→next_status + owner cleared; logs return_received (milestone) + assignment_completed (milestone); **auto-closes all open/in_progress support tickets with actor_role=system, actor_id=NULL** (correct per CLAUDE.md §7 — only place in codebase where system actor appears); each support ticket gets support_auto_closed log (non-milestone)
- **Files:** `app/api/v1/routers/shipping.py`, `app/services/shipping_service.py`, `app/repositories/support_request_repository.py:39–49`

---

### ✅ PASS: G7 — Extension Requests (M11)
**Verdict:** Fully compliant. Cross-entity mutation verified live.
- `GET /admin/extension-requests` ✓ — Filters status; includes item_name, requester_name
- `GET /admin/extension-requests/{id}` ✓ — Detail includes parent request (full), item (full), requester (full)
- `PATCH .../approve` ✓ — Guard: status=pending AND mgr_approval_status IN (not_required, approved) → 409 if mgr_approval_status=pending. **Cross-entity mutation verified:** Parent request.assigned_to moved to extension.extended_to in same transaction. Logs extension_approved (non-milestone) to parent's item.
- `PATCH .../reject` ✓ — Status→rejected; parent request UNCHANGED; logs extension_rejected (non-milestone)
- **Live test:** Approved extension `5cd35d39-...` moved parent request assigned_to from 2026-07-16 to 2026-07-23 (extended_to value)
- **Files:** `app/api/v1/routers/extensions.py`, `app/services/extension_service.py`, repositories

---

### ✅ PASS: G8 — Handovers (M12)
**Verdict:** Fully compliant. Read-only audit implemented correctly.
- `GET /admin/handover-requests` ✓ — GET ONLY (zero POST/PATCH/DELETE routes). Filters status, item_id. Joins item.name, owner.name, borrower.name (two distinct User aliases for self-join — confirmed no owner==borrower bug). Response includes all lifecycle timestamps (requested_at, decided_at, completed_at, note).
- **RBAC:** require_it_admin enforced; 403 for non-admin
- **Pagination:** None (small list, per design intent)
- **Files:** `app/api/v1/routers/handovers.py` (18 lines, 1 GET route), repositories

---

### ✅ PASS: G9 — Users & Settings (M6)
**Verdict:** Fully compliant. F4 deactivate guard correct.
- `GET /admin/users` ✓ — Filters (role, is_active, search); manager-name left join; pagination
- `POST /admin/users` ✓ — Creates with is_active=true, shared dev password "Password123!", can log in immediately. No manager_id settable. Duplicate email→409.
- `PATCH .../role` ✓ — Changes role correctly
- `PATCH .../deactivate` ✓ — **F4 HARD BLOCK:** Returns 409 if user owns any item (`current_owner_id`) OR has any non-terminal request. Both conditions independently checked (verified: Alice Johnson with owned device → 409; throwaway user with nothing → 200). Correct implementation per FE mockup A14.
- `PATCH .../activate` ✓ — Sets is_active=true
- **A13 QR Management:** Confirmed zero backend support (intentional per F7). Only read-only `qr_code_token` field.
- **A14 Category CRUD:** Confirmed zero backend support (intentional per F7). Only read-only `GET /admin/dropdowns/item-categories` dropdown.
- **Files:** `app/api/v1/routers/users.py`, `app/services/user_service.py`, `app/repositories/user_repository.py:69–82` (F4 guard)

---

### 🟡 PASS + 2 GAPS: G4 — Direct Client Assignment (M8)
**Verdict:** Happy path works correctly; 2 gaps flagged above (HIGH: no overlap check; MEDIUM: no employee validation).
- `GET /admin/items/client-available` ✓ — Filters owner_type=client AND status=available; supports category_id, search
- `POST /admin/items/{id}/direct-assign` ⚠️ — Guards validate item.owner_type=client (422), item.status=available (409), employee exists (404). Mutations correct: request (is_client_direct=true, status=assigned), item (status=assigned, current_owner_id), device_log (client_assigned, is_milestone=true). **Gap #1:** No employee.is_active check (allows assigning to inactive). **Gap #2:** No date-range overlap check (allows overlapping bookings on same device—inconsistent with regular assign, which does check).
- `GET /admin/items/{id}/bookings` ✓ — Returns assigned requests for item, ordered by assigned_from
- **Files:** `app/api/v1/routers/items.py`, `app/services/assignment_service.py:343–395`

---

### 🔴 PASS + CRITICAL: G1 — Auth & Dashboard (M2/M13)
**Verdict:** Auth endpoints (`POST /login`, `/refresh`, `/me`) and all 3 dashboard endpoints correct. `/auth/register` is critical security issue (described above).
- `POST /auth/login` ✓ — Envelope, 401 on wrong password/inactive user
- `POST /auth/refresh` ✓ — Validates type=refresh
- `GET /auth/me` ✓ — Returns user profile
- **🔴 `POST /auth/register` — CRITICAL HOLE (described above)**
- `GET /admin/dashboard/summary` ✓ — Returns exact 8 status_breakdown keys (no returned_to_client), pending counts correct
- `GET /admin/dashboard/recent-requests` ✓ — ORDER BY created_at DESC
- `GET /admin/dashboard/open-support` ✓ — WHERE status IN (open, in_progress), ORDER BY filed_at ASC
- **Files:** `app/api/v1/routers/auth.py`, `app/api/v1/routers/dashboard.py`, services, repositories

---

## Summary of Recommendations

| Priority | Issue | Action |
|----------|-------|--------|
| 🔴 CRITICAL | `/auth/register` privilege escalation | DELETE endpoint or restrict to `require_it_admin`; it's out-of-scope per M2 plan |
| 🟡 HIGH | Direct-assign no overlap check | Add overlap validation or document as intentional exception |
| 🟡 MEDIUM | Direct-assign no employee validation | Add is_active + role checks (2–3 lines) |
| ℹ️ INFO | Dashboard KPI gaps, design omissions | Documented; not code bugs; expected FE adaptation |

---

## Audit Metadata

- **Total endpoints audited:** 43 (all GET, POST, PATCH routes under `/api/v1/admin/*` and `/api/v1/auth/*`)
- **Modules passed:** 8 of 9 (89%)
- **Critical findings:** 1 (security)
- **High findings:** 1 (inconsistency)
- **Medium findings:** 1 (validation)
- **Design gaps:** 6 (expected, not code bugs)
- **Out-of-scope confirmed:** 2 (A13 QR, A14 Categories)
- **Live API tests:** Extensive per-endpoint testing on running `http://localhost:8000` with seeded data
- **Code review:** Comprehensive file-by-file against spec and design
- **Test coverage:** Integration tests verified; unit tests spot-checked

---

**Audit Completed:** 2026-07-05, 09:50 UTC  
**Next Steps:** Address critical `/auth/register` issue; resolve HIGH and MEDIUM gaps; deploy with confidence for 8/9 passing modules.
