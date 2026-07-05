# AssetPilot — IT Admin API Documentation

Generated from the current implementation (`app/api/v1/routers/*.py`, `app/schemas/*.py`, `app/models/enums.py`), cross-checked against the design spec (`_docs/IT_ADMIN_API_FLOW.md`, `_docs/IT_ADMIN_FE_DESIGN.html`). This is the source of truth for what's actually shipped — the "Used in" notes tell FE which screen/action triggers each call.

## Base info

- **Base path (all endpoints below except Health):** `/api/v1`
- **Health endpoints:** `/health/*` — outside `/api/v1`, no auth, own response shape (not the envelope below)
- **Auth:** `Authorization: Bearer <access_token>` header (JWT, HS256)
- **All `/admin/*` routes require role `it_admin`** — enforced server-side from the verified JWT `role` claim (not client-trusted). A non-admin authenticated user gets `403 FORBIDDEN`. An unauthenticated caller gets `401 UNAUTHORIZED`.
- **Content type:** JSON in/out.
- **FE screens referenced below** (from the design mockups) — the left nav in the admin app:

| Code | Screen |
|---|---|
| A01 | Admin Dashboard |
| A02 | Request Management (list) |
| A03 | Request Detail & Assign |
| A04 | Inventory Management (list) |
| A05 | Device Detail |
| A06 | Device Timeline |
| A07 | Direct Client Assignment |
| A08 | Support Requests & Resolve |
| A09 | Shipping & Returns |
| A10 | Maintenance (filtered inventory view) |
| A11 | Extension Requests |
| A12 | Handovers (read-only audit) |
| A13 | QR Management — **not built, no endpoints** |
| A14 | Settings & User Management |

## Response envelope

Every `/api/v1/*` endpoint (success or error) returns this shape:

**Success**
```json
{
  "status_code": 200,
  "data": { /* endpoint-specific — object, array, or null */ },
  "message": "Human-readable message.",
  "meta": {
    "timestamp": "2026-07-05T10:00:00Z",
    "request_id": "uuid-string",
    "pagination": { "page": 1, "page_size": 20, "total_items": 42, "total_pages": 3 }
  },
  "success": true
}
```
`meta.pagination` is present only on paginated list endpoints (marked below).

**Error**
```json
{
  "status_code": 422,
  "message": "Request validation failed.",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [{ "field": "body.name", "issue": "Field required" }]
  },
  "meta": { "timestamp": "...", "request_id": "..." },
  "success": false
}
```

| HTTP status | `error.code` | Meaning |
|---|---|---|
| 401 | `UNAUTHORIZED` | Missing/invalid/expired token — FE should redirect to login |
| 403 | `FORBIDDEN` | Authenticated but wrong role |
| 404 | `RESOURCE_NOT_FOUND` | Entity doesn't exist |
| 409 | `CONFLICT` | Valid request, wrong entity state (e.g. double-approve, deactivating a user who holds devices) — show as an inline "can't do that right now" message, not a generic error toast |
| 422 | `VALIDATION_ERROR` | Malformed input (body/query) — map `error.details[].field`/`.issue` to form fields |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_SERVER_ERROR` | Unhandled error |
| 503 | `SERVICE_UNAVAILABLE` | Dependency down (health checks) |

## Pagination (list endpoints marked "Paginated")

Query params: `page` (default `1`), `page_size` (default `20`, max `100`), `sort_by` (optional), `sort_order` (`asc`|`desc`, default `asc`).

## Enums

```
UserRole:            employee | manager | it_admin
DeviceStatus:         available | assigned | shipping_pending | return_shipping_pending |
                      under_repair | maintenance | lost | retired | returned_to_client
RequestStatus:        requested | pending_mgr_approval | pending_it_approval | assigned |
                      completed | rejected | cancelled
MgrApprovalStatus:    not_required | pending | approved | rejected
RejectedByEnum:       manager | it_admin | it_admin_cancel
RequestPriority:      low | medium | high
OwnerType:            company | client
SupportType:          update | damage | lost
SupportStatus:        open | in_progress | resolved
SupportResolution:    remote_resolved | repaired_in_place | swapped | marked_lost
ExtensionStatus:      pending | approved | rejected
HandoverStatus:       requested | accepted | rejected | cancelled | completed
ActorRole:            employee | manager | it_admin | system
DeviceLogEvent:       device_created | device_edited | assigned | client_assigned |
                      ship_outbound_initiated | ship_outbound_completed | return_ship_initiated |
                      return_received | assignment_completed | status_changed | support_opened |
                      support_resolved | support_auto_closed | extension_requested |
                      extension_approved | extension_rejected | handover_requested |
                      handover_accepted | handover_rejected | handover_cancelled |
                      handover_completed | marked_lost | retired | returned_to_client |
                      swapped_out | swapped_in
```

**Editable device statuses** via `PATCH /admin/items/{id}/status`: only `available | under_repair | maintenance | lost | retired | returned_to_client`. Other statuses (`assigned`, `shipping_pending`, `return_shipping_pending`) are lifecycle-managed by the assign/ship/return flows and cannot be set directly from this endpoint — the FE status dropdown on A04/A05/A10 should only offer the editable set.

**Allowed `next_status`** for `POST /admin/requests/{id}/complete-return`: only `available | under_repair | retired`.

---

## Module: Health (`/health`) — no auth, no `/api/v1` prefix

Infra probes, not FE-facing — used by Docker/K8s/Azure health checks, not the admin app.

| Method | Path | Description |
|---|---|---|
| GET | `/health/live` | Liveness probe. Returns `{"status": "ok"}` directly (not the envelope). |
| GET | `/health/ready` | Readiness probe — checks DB connectivity. Returns `200` if healthy, `503` otherwise, body: `{status, timestamp, checks: {database: {status, latency_ms, error}}}` (not the envelope). |

---

## Module: Auth (`/api/v1/auth`) — no admin role required

Used on the login screen and for maintaining a session across all admin screens.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | none | Register a new user, returns tokens. |
| POST | `/auth/login` | none | Email/password login, returns tokens. |
| POST | `/auth/refresh` | none | Exchange a refresh token for a new token pair. |
| GET | `/auth/me` | Bearer | Current authenticated user's profile. |

#### `POST /auth/register` (201)
**Used in:** not on any A01–A14 screen — the admin mockups have no self-registration screen; this exists as a generic account-creation endpoint. Confirm with backend whether FE should wire this up at all (see Notes at the bottom) or route all user creation through `POST /admin/users` (A14) instead.
Request:
```json
{ "name": "string", "email": "user@example.com", "role": "employee|manager|it_admin", "password": "min 8 chars" }
```
Response `data`:
```json
{ "access_token": "string", "refresh_token": "string", "token_type": "bearer" }
```

#### `POST /auth/login`
**Used in:** login screen. Call this first with the IT-Admin's email/password; store both tokens (e.g. `access_token` in memory, `refresh_token` in secure storage) before navigating into A01.
Request:
```json
{ "email": "user@example.com", "password": "string" }
```
Response `data`:
```json
{ "access_token": "string", "refresh_token": "string", "token_type": "bearer" }
```

#### `POST /auth/refresh`
**Used in:** background token-refresh logic (e.g. an axios/fetch interceptor that catches a `401` or refreshes proactively before expiry). Not a user-visible action.
Request:
```json
{ "refresh_token": "string" }
```
Response `data`:
```json
{ "access_token": "string", "refresh_token": "string", "token_type": "bearer" }
```

#### `GET /auth/me`
**Used in:** app shell bootstrap — call once after login (or on app reload with a stored token) to populate the logged-in admin's name/avatar in the header and confirm the token is still valid/role is still `it_admin`.
Response `data`:
```json
{ "id": "uuid", "name": "string", "email": "string", "role": "employee|manager|it_admin", "manager_id": "uuid|null", "is_active": true }
```

---

## Module: Dashboard (`/api/v1/admin/dashboard`) — IT Admin only — Screen A01

Landing screen after login. All three calls fire together on page load; none depend on each other.

| Method | Path | Paginated | Description |
|---|---|---|---|
| GET | `/admin/dashboard/summary` | no | KPI counts for the admin landing screen. |
| GET | `/admin/dashboard/recent-requests` | no (query `limit`, default 10) | Most recent requests. |
| GET | `/admin/dashboard/open-support` | no (query `limit`, default 10) | Open/in-progress support tickets. |

#### `GET /admin/dashboard/summary`
**Used in:** A01 KPI tiles (device status breakdown chart/cards + the 4 pending-count badges). Poll or refetch on tab focus to keep counts fresh.
Response `data`:
```json
{
  "status_breakdown": {
    "available": 0, "assigned": 0, "under_repair": 0, "maintenance": 0,
    "shipping_pending": 0, "return_shipping_pending": 0, "lost": 0, "retired": 0
  },
  "pending_requests_count": 0,
  "open_support_count": 0,
  "active_handovers_count": 0,
  "pending_extensions_count": 0
}
```
**FE derivation notes (no dedicated fields exist for these):**
- `status_breakdown` intentionally excludes `returned_to_client` — there is no `total_devices` field. FE cannot compute a true "Total devices" tile from this response alone (it would undercount any `returned_to_client` items); treat "Total devices" as sum-of-breakdown-plus-caveat, or ask backend for a dedicated field if an exact total is required.
- The A01 "In transit" KPI tile has no backing field — derive it client-side as `status_breakdown.shipping_pending + status_breakdown.return_shipping_pending`.

#### `GET /admin/dashboard/recent-requests?limit=10`
**Used in:** A01 "Recent Requests" widget. Row click should deep-link to A03 (`GET /admin/requests/{id}`) for that request's id.
Response `data`: array of **RequestListEntryResponse** (full shape defined under Requests module — `GET /admin/requests`):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime",
  "category_name": "string", "requester_name": "string"
}
```

#### `GET /admin/dashboard/open-support?limit=10`
**Used in:** A01 "Open Support" widget. Row click should deep-link to A08 detail view for that ticket's id.
Response `data`: array of **SupportListEntryResponse** (full shape defined under Support Requests module — `GET /admin/support-requests`):
```json
{
  "id": "uuid", "item_id": "uuid", "requester_id": "uuid", "request_id": "uuid|null",
  "type": "SupportType", "description": "string", "status": "SupportStatus",
  "resolution": "SupportResolution|null", "it_note": "string|null",
  "swapped_to_item_id": "uuid|null", "filed_at": "datetime",
  "resolved_by": "uuid|null", "resolved_at": "datetime|null", "auto_closed": false,
  "created_at": "datetime", "updated_at": "datetime",
  "item_name": "string", "requester_name": "string"
}
```

---

## Module: Dropdowns (`/api/v1/admin/dropdowns`) — IT Admin only

Shared reference data — not a screen of its own, but feeds form controls across several screens. Fetch once per session/form-mount and cache; this data changes rarely.

| Method | Path | Description |
|---|---|---|
| GET | `/admin/dropdowns/item-categories` | All item categories. |
| GET | `/admin/dropdowns/managers` | All users with role `manager`. |
| GET | `/admin/dropdowns/employees` | All users with role `employee`. |

#### `GET /admin/dropdowns/item-categories`
**Used in:** A04 "Add Device" form (category select) and A04/A08 filter bars.
Response `data`: array of
```json
{ "id": "uuid", "name": "string", "description": "string|null", "requires_mgr_approval": true, "is_active": true }
```

#### `GET /admin/dropdowns/managers`
**Used in:** A03 "Escalate to Manager" action — populates the manager picker before calling `PATCH /admin/requests/{id}/escalate-to-manager`.
Response `data`: array of **UserMeResponse**:
```json
{ "id": "uuid", "name": "string", "email": "string", "role": "manager", "manager_id": "uuid|null", "is_active": true }
```

#### `GET /admin/dropdowns/employees`
**Used in:** A07 Direct Client Assignment — populates the "assign to employee" picker before calling `POST /admin/items/{id}/direct-assign`.
Response `data`: array of **UserMeResponse**, always `role: "employee"` here:
```json
{ "id": "uuid", "name": "string", "email": "string", "role": "employee", "manager_id": "uuid|null", "is_active": true }
```

---

## Module: Inventory / Items (`/api/v1/admin/items`) — IT Admin only — Screens A04, A05, A06, A07, A10

| Method | Path | Paginated | Description |
|---|---|---|---|
| GET | `/admin/items` | yes | List devices with filters. |
| POST | `/admin/items` | — | Create a device. |
| GET | `/admin/items/client-available` | no | Client-owned devices currently available. |
| PATCH | `/admin/items/{item_id}` | — | Edit device metadata. |
| PATCH | `/admin/items/{item_id}/status` | — | Change device status directly. |
| GET | `/admin/items/{item_id}` | — | Full device detail (owner, active request, open support, active handover). |
| GET | `/admin/items/{item_id}/timeline` | — | Device audit log timeline. |
| GET | `/admin/items/{item_id}/bookings` | — | Booking calendar for this device. |
| POST | `/admin/items/{item_id}/direct-assign` | — | Directly assign a device to an employee (bypasses the request queue). |

#### `GET /admin/items`
**Used in:** A04 Inventory table (main list + filters: category/status/owner-type/search) **and** A10 Maintenance screen — A10 is this same endpoint called with `status=under_repair` or `status=maintenance` to build its filtered table, not a separate backend concept.
Query params: `category_id` (uuid), `status` (`DeviceStatus`), `owner_type` (`OwnerType`), `search` (string — matches device `name`/`serial_no`), plus pagination params. `status` accepts **one** value, not a list — A10's combined "Under Repair + Maintenance" table requires **two separate calls** (`status=under_repair` and `status=maintenance`) merged client-side; there is no OR-filter for multiple statuses in one request.
Response `data`: array of **ItemListEntryResponse**:
```json
{
  "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
  "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
  "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
  "created_at": "datetime", "updated_at": "datetime",
  "category_name": "string", "current_owner_name": "string|null"
}
```
`meta.pagination` included. Note: `updated_at` is a generic last-modified timestamp (also bumped by unrelated metadata edits via `PATCH .../{item_id}`) — if A04/A10's "Set at" column is meant to show the exact status-change time, it's only approximate here; the precise moment is in `GET .../{item_id}/timeline`.

#### `POST /admin/items` (201)
**Used in:** A04 "Add Device" form submit.
Request:
```json
{
  "name": "string", "serial_no": "string", "category_id": "uuid",
  "owner_type": "company|client", "client_name": "string|null (required if owner_type=client)",
  "purchase_date": "2026-01-01|null"
}
```
Response `data`: **ItemResponse**:
```json
{
  "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
  "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
  "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
  "created_at": "datetime", "updated_at": "datetime"
}
```
After success, refetch or optimistically prepend to the A04 list.

#### `GET /admin/items/client-available`
**Used in:** A07 Direct Client Assignment — populates the device picker (client-owned devices only, already filtered to `available`) before `POST /admin/items/{id}/direct-assign`.
Query params: `category_id` (uuid, optional), `search` (string, optional).
Response `data`: array of **ClientAvailableResponse** (`ItemResponse` fields + `category_name`):
```json
{
  "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
  "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
  "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
  "created_at": "datetime", "updated_at": "datetime", "category_name": "string"
}
```
Note: server-side filtering is `owner_type=client` **and** `status=available` — this is implicit (not a query param); FE doesn't need to (and can't) pass `status` here.

#### `PATCH /admin/items/{item_id}`
**Used in:** A04/A05 "Edit Device" form submit (name/category/client_name/purchase_date).
Request (all optional, partial update):
```json
{ "name": "string", "category_id": "uuid", "client_name": "string", "purchase_date": "date" }
```
`name`/`category_id` cannot be explicitly set to `null` if included. Response `data`: **ItemResponse** (same shape as `POST /admin/items` above).

#### `PATCH /admin/items/{item_id}/status`
**Used in:** the "Change Status" modal shared by A04, A05, and A10 (e.g. A10's Repair-queue row action opens this same modal, pre-filled with the target status).
Request:
```json
{ "status": "available|under_repair|maintenance|lost|retired|returned_to_client", "it_note": "string|null" }
```
Response `data`: **ItemResponse** (same shape as `POST /admin/items` above).

#### `GET /admin/items/{item_id}`
**Used in:** A05 Device Detail screen — the primary load call when navigating from A04's device row.
Response `data`:
```json
{
  "item": ItemResponse,
  "category": ItemCategoryResponse,
  "current_owner": UserMeResponse | null,
  "current_request": RequestSummaryResponse | null,
  "open_support": [SupportRequestSummaryResponse],
  "active_handover": HandoverSummaryResponse | null
}
```
`ItemResponse`, `ItemCategoryResponse`, and `UserMeResponse` here are the same shapes already defined above (`POST /admin/items` response, `GET /admin/dropdowns/item-categories` response, `GET /auth/me` response respectively).

`RequestSummaryResponse` (nested in `current_request`) carries `requester_name` alongside `requester_id`, resolved server-side, so A05's "Current Assignment" panel ("Requester: Arjun Mehta") can render directly — no client-side id→name join needed. This is independent of the item's own `current_owner` (usually the same person, but resolved separately since the request's requester and the device's current owner are structurally different fields):
```json
{
  "id": "uuid", "requester_id": "uuid", "requester_name": "string|null", "category_id": "uuid",
  "assigned_item_id": "uuid|null", "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime"
}
```

`SupportRequestSummaryResponse` (nested array in `open_support`) — same field set as the bare `SupportRequestResponse` shown under `PATCH /admin/support-requests/{id}/start` below, no extra name fields:
```json
{
  "id": "uuid", "item_id": "uuid", "requester_id": "uuid", "request_id": "uuid|null",
  "type": "SupportType", "description": "string", "status": "SupportStatus",
  "resolution": "SupportResolution|null", "it_note": "string|null",
  "swapped_to_item_id": "uuid|null", "filed_at": "datetime",
  "resolved_by": "uuid|null", "resolved_at": "datetime|null", "auto_closed": false,
  "created_at": "datetime", "updated_at": "datetime"
}
```

`HandoverSummaryResponse` (nested in `active_handover`) also carries `owner_name`/`borrower_name` (resolved server-side alongside `owner_id`/`borrower_id`) so A05's "Active Handover" panel (e.g. "Borrower · Karan Shah") can render directly — no client-side id→name join needed:
```json
{
  "id": "uuid", "item_id": "uuid",
  "owner_id": "uuid", "owner_name": "string|null",
  "borrower_id": "uuid", "borrower_name": "string|null",
  "requested_duration_hours": 0, "status": "HandoverStatus",
  "requested_at": "datetime", "decided_at": "datetime|null", "completed_at": "datetime|null",
  "note": "string|null", "created_at": "datetime", "updated_at": "datetime"
}
```

A05's "Process Return" button is **not** an `/admin/items/*` action — it maps to `POST /admin/requests/{request_id}/complete-return` in the Shipping & Returns module below (using `current_request.id`).

#### `GET /admin/items/{item_id}/timeline`
**Used in:** A06 Device Timeline — a tab/section within A05. Timeline is append-only (no edit/delete UI needed for entries).
Query param: `milestones_only` (bool, default `true`) — the timeline view's default toggle; flip to `false` for a FE "show all events" expand.
Response `data`: array of **DeviceLogEntryResponse**:
```json
{
  "id": "uuid", "item_id": "uuid", "event_type": "DeviceLogEvent", "actor_id": "uuid|null",
  "actor_name": "string|null", "actor_role": "ActorRole", "request_id": "uuid|null",
  "support_request_id": "uuid|null", "extension_request_id": "uuid|null", "handover_request_id": "uuid|null",
  "from_value": "string|null", "to_value": "string|null", "note": "string|null",
  "metadata": {}, "is_milestone": true, "occurred_at": "datetime"
}
```
`actor_name` is resolved server-side (left-joined on `actor_id`) so A06's "Actor: Arjun Mehta" labels render directly — no FE id→name lookup needed. It's `null` when `actor_id` is `null` (system-generated events, `actor_role: "system"`).
Note: `request_id`/`support_request_id`/etc. are raw UUIDs — there is no short sequential number (e.g. `#2018`) anywhere in the API; if the mockup's numbering is needed, it must be a FE-only display convention (e.g. last 6 chars of the UUID), not a real sequence.

#### `GET /admin/items/{item_id}/bookings`
**Used in:** A05 "Booking Calendar" widget for a device, and the calendar strip shown on A03 while assigning a device (so IT can see a candidate device's existing reservations before picking it).
Response `data`: array of **BookingResponse** (`RequestResponse` fields + `requester_name`):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime",
  "requester_name": "string"
}
```

#### `POST /admin/items/{item_id}/direct-assign` (201)
**Used in:** A07 Direct Client Assignment form submit — after picking an employee (`/admin/dropdowns/employees`) and an available client device (`/admin/items/client-available`).
Request:
```json
{ "employee_id": "uuid", "assigned_from": "datetime", "assigned_to": "datetime" }
```
`assigned_from`/`assigned_to` are full ISO-8601 datetimes (not date-only) even though the mockup's pickers show date-only values — FE should submit a time component (e.g. midnight local/UTC). `assigned_from` must be before `assigned_to`. Response `data`: **RequestResponse** (the auto-created, already-`assigned` request record — no separate approval step for client-direct assignments):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime"
}
```
There is **no `note` field** on this request — the mockup's Assignment Form "Note" textarea has nothing to bind to; the created request's `note` is always `null`. Treat it as unsupported until backend adds it, or drop the field from this form.

---

## Module: Requests & Approvals (`/api/v1/admin`) — IT Admin only — Screens A02, A03

Typical flow: A02 list → click a row → A03 detail. On A03, IT either **rejects**, **cancels**, **escalates to a manager** (if it needs manager sign-off first), or **assigns a device** (pulling suggestions, adjusting the date range, then confirming).

| Method | Path | Paginated | Description |
|---|---|---|---|
| GET | `/admin/requests` | yes | List all requests with filters. |
| GET | `/admin/requests/{request_id}` | — | Full request detail. |
| GET | `/admin/it/approvals` | yes | IT approval queue (requests awaiting IT decision). |
| PATCH | `/admin/requests/{request_id}/reject` | — | IT rejects a request. |
| PATCH | `/admin/requests/{request_id}/cancel` | — | IT cancels a request. |
| PATCH | `/admin/requests/{request_id}/escalate-to-manager` | — | Route request to a manager for approval. |
| GET | `/admin/requests/{request_id}/suggested-devices` | — | Deterministic device suggestions for this request. |
| PATCH | `/admin/requests/{request_id}/booking-range` | — | Adjust the assigned date range before/after assignment. |
| POST | `/admin/requests/{request_id}/assign` | — | Assign a device to fulfill the request. |

#### `GET /admin/requests`
**Used in:** A02 main table — the general "all requests" view (any status), distinct from A03's queue-scoped variant below.
Query params: `status` (`RequestStatus`), `category_id` (uuid), `priority` (`RequestPriority`), `requested_from` (datetime), `requested_to` (datetime), `search` (string — matches requester name/email), plus pagination.
Response `data`: array of **RequestListEntryResponse**:
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime",
  "category_name": "string", "requester_name": "string"
}
```
`meta.pagination` included.

#### `GET /admin/requests/{request_id}`
**Used in:** A03 Request Detail screen load.
Response `data`: **RequestDetailResponse** — all `RequestResponse` fields plus extras, flattened:
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime",
  "category_name": "string", "requester_name": "string",
  "manager_name": "string|null", "it_decided_by_name": "string|null",
  "cancelled_by_name": "string|null", "completed_by_name": "string|null",
  "item": {
    "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
    "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
    "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid"
  }
}
```
`item` is `AssignedItemSummaryResponse | null` — `null` while the request has no assigned device yet (e.g. `requested`/`pending_*_approval` states), otherwise the object shown above.

#### `GET /admin/it/approvals`
**Used in:** A02's dedicated "IT Approval Queue" tab/filter — the sidebar/queue badge count comes from `pending_requests_count` on A01, this endpoint returns the actual rows, pre-sorted by priority then oldest-first. No status filter param needed — it's always scoped to `pending_it_approval`.
Paginated, no filters. Response `data`: array of **RequestListEntryResponse** — identical shape to `GET /admin/requests` above.

**A02 status tab-chip counts** ("All · 312", "Pending RM · 12", "Pending IT · 16", etc., see mockup): there is no aggregate "counts by status" endpoint. `GET /admin/requests` only returns `meta.pagination.total_items` for whichever single `status` filter is currently applied. To populate all tab-chip counts simultaneously, FE must issue one `GET /admin/requests?status=X&page_size=1` call per status (reading `total_items` from each), or accept an approximate/lazy-loaded count per tab. Flag to backend if a single aggregate endpoint is wanted instead.

#### `PATCH /admin/requests/{request_id}/reject`
**Used in:** A03 "Reject" action — only valid while the request is `pending_it_approval`.
Request:
```json
{ "rejected_reason": "string", "it_decision_note": "string|null" }
```
Response `data`: **RequestResponse** (bare, no `category_name`/`requester_name` — same base fields as `GET /admin/requests` minus those two):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime"
}
```
This bare `RequestResponse` shape is reused verbatim by every other `RequestResponse`-returning endpoint below (`cancel`, `escalate-to-manager`, `booking-range`, `assign`, and the Shipping & Returns module's `ship`/`confirm-delivery`/`complete-return`).

#### `PATCH /admin/requests/{request_id}/cancel`
**Used in:** A03 "Cancel" action — usable while the request is in any non-terminal state (unlike reject, which requires `pending_it_approval`).
Request:
```json
{ "rejected_reason": "string" }
```
Response `data`: **RequestResponse** (same bare shape as `reject` above).

#### `PATCH /admin/requests/{request_id}/escalate-to-manager`
**Used in:** A03 "Escalate to Manager" action, paired with the `/admin/dropdowns/managers` picker. Only valid when the request doesn't already require manager approval.
Request:
```json
{ "manager_id": "uuid|null" }
```
Omit `manager_id` to default to the requester's own manager. Response `data`: **RequestResponse** (same bare shape as `reject` above).

#### `GET /admin/requests/{request_id}/suggested-devices`
**Used in:** A03's device-picker panel (labelled "AI ranking" in the mockup, but it's a deterministic sort by fewest active bookings then longest-free — no ML). Call on entering the Assign flow; IT picks one of the returned devices, optionally checks its calendar (`/admin/items/{id}/bookings`), then adjusts dates and confirms via `/assign`.
Response `data`: array of **SuggestedDeviceResponse** (`ItemResponse` fields + `category_name`, `active_bookings_count`):
```json
{
  "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
  "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
  "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
  "created_at": "datetime", "updated_at": "datetime",
  "category_name": "string", "active_bookings_count": 0
}
```

#### `PATCH /admin/requests/{request_id}/booking-range`
**Used in:** A03 "Adjust dates" on an already-`assigned` request (post-assignment date correction), not part of the initial assign form itself.
Request:
```json
{ "assigned_from": "datetime", "assigned_to": "datetime" }
```
`assigned_from` must be before `assigned_to`. Response `data`: **RequestResponse** (same bare shape as `reject` above).

#### `POST /admin/requests/{request_id}/assign`
**Used in:** A03 "Confirm Assignment" — final step of the assign flow after picking a device from `suggested-devices` and setting dates/WFH toggle.
Request:
```json
{ "item_id": "uuid", "assigned_from": "datetime", "assigned_to": "datetime", "is_wfh": false }
```
Response `data`: **RequestResponse** (same bare shape as `reject` above). If `is_wfh: true`, the request now needs shipping (A09) as a separate follow-up step — assigning does not auto-ship.

---

## Module: Shipping & Returns (`/api/v1/admin`) — IT Admin only — Screen A09

WFH device shipping lifecycle: outbound queue → ship → confirm delivery; separately, returns queue → complete return.

| Method | Path | Description |
|---|---|---|
| GET | `/admin/shipping/outbound` | Queue of requests awaiting outbound shipment. |
| GET | `/admin/shipping/returns` | Queue of WFH devices awaiting return. |
| POST | `/admin/requests/{request_id}/ship` | Mark a device as shipped (outbound). |
| POST | `/admin/requests/{request_id}/confirm-delivery` | Confirm the shipped device was delivered. |
| POST | `/admin/requests/{request_id}/complete-return` | Complete a WFH return and set the device's next status. |

#### `GET /admin/shipping/outbound`
**Used in:** A09 "Outbound" tab — WFH requests that are `assigned` but not yet shipped.
No query params (no search/date-range filtering exists here). Response `data`: array of **ShippingQueueEntryResponse** (`RequestResponse` fields + `item_name`, `requester_name`):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime",
  "item_name": "string", "requester_name": "string"
}
```
The mockup's "Outbound in transit N" header counter has no dedicated endpoint — derive it client-side from the returned array's length.

#### `GET /admin/shipping/returns`
**Used in:** A09 "Returns" tab — devices currently `return_shipping_pending`.
No query params. Response `data`: array of **ShippingQueueEntryResponse** — same shape as `GET /admin/shipping/outbound` above. Same client-side-count note applies to "Returns in transit N".

#### `POST /admin/requests/{request_id}/ship`
**Used in:** A09 Outbound row action "Mark Shipped" — opens a tracking-URL input, then calls this.
Request:
```json
{ "ship_tracking_url": "string" }
```
Response `data`: **RequestResponse** (bare shape — same as `PATCH /admin/requests/{id}/reject` response in the Requests & Approvals module above):
```json
{
  "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
  "requested_from": "datetime", "requested_to": "datetime",
  "assigned_from": "datetime|null", "assigned_to": "datetime|null",
  "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
  "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
  "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
  "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
  "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
  "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
  "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
  "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
  "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
  "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime"
}
```
Moves the row from "awaiting ship" to an in-transit state; device status becomes `shipping_pending`.
Preconditions (`422`/`409` — build inline errors, not generic toasts): the request must have `is_wfh: true` (422 if not a WFH request); the device's current status must be `assigned` (409 otherwise).

#### `POST /admin/requests/{request_id}/confirm-delivery`
**Used in:** A09 Outbound row action "Confirm Delivery" — call once the carrier confirms drop-off; no form needed.
No body. Response `data`: **RequestResponse** (bare shape, same as `ship` above). Device status returns to `assigned`.
Precondition: device status must be `shipping_pending` (409 otherwise).

#### `POST /admin/requests/{request_id}/complete-return`
**Used in:** A09 Returns row action "Complete Return" — opens a "next status" selector (`available` / `under_repair` / `retired`) then calls this.
Request:
```json
{ "next_status": "available|under_repair|retired" }
```
Response `data`: **RequestResponse** (bare shape, same as `ship` above). Note: this also auto-closes any open/in-progress support tickets on the device — refresh A08's list if it's open in another tab.
Precondition: device status must be `assigned` or `return_shipping_pending` (409 otherwise).

---

## Module: Support Requests (`/api/v1/admin/support-requests`) — IT Admin only — Screen A08

| Method | Path | Description |
|---|---|---|
| GET | `/admin/support-requests` | List support tickets with filters. |
| GET | `/admin/support-requests/{support_request_id}` | Full ticket detail. |
| PATCH | `/admin/support-requests/{support_request_id}/start` | Mark ticket in progress. |
| PATCH | `/admin/support-requests/{support_request_id}/resolve` | Resolve a ticket. |

#### `GET /admin/support-requests`
**Used in:** A08 main queue table.
Query params: `status` (`SupportStatus`), `type` (`SupportType`), `item_id` (uuid). Not paginated.
Response `data`: array of **SupportListEntryResponse**:
```json
{
  "id": "uuid", "item_id": "uuid", "requester_id": "uuid", "request_id": "uuid|null",
  "type": "SupportType", "description": "string", "status": "SupportStatus",
  "resolution": "SupportResolution|null", "it_note": "string|null",
  "swapped_to_item_id": "uuid|null", "filed_at": "datetime",
  "resolved_by": "uuid|null", "resolved_at": "datetime|null", "auto_closed": false,
  "created_at": "datetime", "updated_at": "datetime",
  "item_name": "string", "requester_name": "string"
}
```
**FE label mapping gap:** `SupportType` is only `update|damage|lost` — the A08 mockup's type badges show "Replace" / "Install" / "Repair" / "Lost", three of which don't match a backend enum value 1:1. FE must map its display labels onto this 3-value enum (e.g. Replace/Repair → `damage`, Install → `update`) rather than expecting a wider enum from the API.

#### `GET /admin/support-requests/{support_request_id}`
**Used in:** A08 ticket detail/resolve panel, opened from a row click.
Response `data`: **SupportDetailResponse** — bare `SupportRequestResponse` fields + `item: ItemResponse`, `requester: UserResponse`:
```json
{
  "id": "uuid", "item_id": "uuid", "requester_id": "uuid", "request_id": "uuid|null",
  "type": "SupportType", "description": "string", "status": "SupportStatus",
  "resolution": "SupportResolution|null", "it_note": "string|null",
  "swapped_to_item_id": "uuid|null", "filed_at": "datetime",
  "resolved_by": "uuid|null", "resolved_at": "datetime|null", "auto_closed": false,
  "created_at": "datetime", "updated_at": "datetime",
  "item": {
    "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
    "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
    "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
    "created_at": "datetime", "updated_at": "datetime"
  },
  "requester": {
    "id": "uuid", "name": "string", "email": "string", "role": "UserRole",
    "manager_id": "uuid|null", "is_active": true, "created_at": "datetime", "updated_at": "datetime"
  }
}
```

#### `PATCH /admin/support-requests/{support_request_id}/start`
**Used in:** A08 "Start" button on an `open` ticket. No form.
No body. Response `data`: **SupportRequestResponse** (bare, no `item_name`/`requester_name`):
```json
{
  "id": "uuid", "item_id": "uuid", "requester_id": "uuid", "request_id": "uuid|null",
  "type": "SupportType", "description": "string", "status": "SupportStatus",
  "resolution": "SupportResolution|null", "it_note": "string|null",
  "swapped_to_item_id": "uuid|null", "filed_at": "datetime",
  "resolved_by": "uuid|null", "resolved_at": "datetime|null", "auto_closed": false,
  "created_at": "datetime", "updated_at": "datetime"
}
```
If ticket `type = damage`, the underlying device flips to `under_repair` as a side effect.

#### `PATCH /admin/support-requests/{support_request_id}/resolve`
**Used in:** A08 "Resolve" panel — the resolution dropdown drives which extra fields the form shows: picking `swapped` reveals a replacement-device picker and an "old device next status" selector.
Request:
```json
{
  "resolution": "remote_resolved|repaired_in_place|swapped|marked_lost",
  "it_note": "string|null",
  "swapped_to_item_id": "uuid|null",
  "old_item_next_status": "DeviceStatus|null"
}
```
`swapped_to_item_id` and `old_item_next_status` are **required** when `resolution` is `swapped`. Response `data`: **SupportRequestResponse** (same bare shape as `start` above). Note: `marked_lost` also completes the tied request server-side — no separate "complete request" call needed.

Preconditions/errors to build inline UI for (all `409 CONFLICT` unless noted):
- Ticket must not already be `resolved` (409 if resolving twice).
- `resolution=swapped` or `resolution=marked_lost` requires the ticket to have a tied `request_id` — 409 if it's `null` (e.g. a ticket filed with no linked request can't be swapped/marked-lost).
- `remote_resolved` performs **no device status change** — the device keeps its current status; only `repaired_in_place`/`swapped`/`marked_lost` transition the device.
- `old_item_next_status` currently accepts **any** `DeviceStatus` value with no allow-list (unlike `complete-return`'s `next_status`, which is restricted to `available|under_repair|retired`). The mockup's selector implies a curated list (e.g. "Under repair") — FE should constrain its own dropdown to sensible values until/unless backend adds the same restriction.

---

## Module: Extension Requests (`/api/v1/admin/extension-requests`) — IT Admin only — Screen A11

Employee requests to extend an assignment's end date.

| Method | Path | Description |
|---|---|---|
| GET | `/admin/extension-requests` | List extension requests, optional `status` filter. |
| GET | `/admin/extension-requests/{extension_request_id}` | Full detail. |
| PATCH | `/admin/extension-requests/{extension_request_id}/approve` | Approve the extension. |
| PATCH | `/admin/extension-requests/{extension_request_id}/reject` | Reject the extension. |

#### `GET /admin/extension-requests`
**Used in:** A11 main table, typically defaulted to `status=pending`.
Query param: `status` (`ExtensionStatus`, optional). Response `data`: array of **ExtensionListEntryResponse**:
```json
{
  "id": "uuid", "original_request_id": "uuid", "requester_id": "uuid",
  "current_assigned_to": "datetime", "extended_to": "datetime", "status": "ExtensionStatus",
  "requires_mgr_approval": true, "manager_id": "uuid|null", "mgr_approval_status": "MgrApprovalStatus",
  "manager_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_note": "string|null", "it_decided_at": "datetime|null",
  "created_at": "datetime", "updated_at": "datetime",
  "item_name": "string", "requester_name": "string"
}
```

#### `GET /admin/extension-requests/{extension_request_id}`
**Used in:** A11 row-click detail panel.
Response `data`: **ExtensionDetailResponse** — bare `ExtensionRequestResponse` fields + `request: RequestResponse`, `item: ItemResponse`, `requester: UserResponse`:
```json
{
  "id": "uuid", "original_request_id": "uuid", "requester_id": "uuid",
  "current_assigned_to": "datetime", "extended_to": "datetime", "status": "ExtensionStatus",
  "requires_mgr_approval": true, "manager_id": "uuid|null", "mgr_approval_status": "MgrApprovalStatus",
  "manager_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_note": "string|null", "it_decided_at": "datetime|null",
  "created_at": "datetime", "updated_at": "datetime",
  "request": {
    "id": "uuid", "requester_id": "uuid", "category_id": "uuid", "assigned_item_id": "uuid|null",
    "requested_from": "datetime", "requested_to": "datetime",
    "assigned_from": "datetime|null", "assigned_to": "datetime|null",
    "status": "RequestStatus", "priority": "RequestPriority", "note": "string|null",
    "requires_mgr_approval": true, "mgr_approval_status": "MgrApprovalStatus",
    "manager_id": "uuid|null", "manager_decision_note": "string|null", "manager_decided_at": "datetime|null",
    "it_decided_by": "uuid|null", "it_decision_note": "string|null", "it_decided_at": "datetime|null",
    "rejected_by": "RejectedByEnum|null", "rejected_reason": "string|null",
    "cancelled_by": "uuid|null", "cancelled_at": "datetime|null",
    "is_wfh": false, "ship_tracking_url": "string|null", "ship_initiated_at": "datetime|null",
    "ship_completed_at": "datetime|null", "return_tracking_url": "string|null",
    "return_initiated_at": "datetime|null", "completed_at": "datetime|null",
    "completed_by": "uuid|null", "completed_next_status": "DeviceStatus|null",
    "is_client_direct": false, "created_at": "datetime", "updated_at": "datetime"
  },
  "item": {
    "id": "uuid", "name": "string", "serial_no": "string", "category_id": "uuid",
    "owner_type": "company|client", "client_name": "string|null", "status": "DeviceStatus",
    "current_owner_id": "uuid|null", "purchase_date": "2026-01-01|null", "qr_code_token": "uuid",
    "created_at": "datetime", "updated_at": "datetime"
  },
  "requester": {
    "id": "uuid", "name": "string", "email": "string", "role": "UserRole",
    "manager_id": "uuid|null", "is_active": true, "created_at": "datetime", "updated_at": "datetime"
  }
}
```

#### `PATCH /admin/extension-requests/{extension_request_id}/approve`
**Used in:** A11 "Approve" action. Only valid when `mgr_approval_status` is `not_required` or `approved` — if a manager approval is still `pending`, the FE should disable this button and show why.
Request:
```json
{ "it_note": "string|null" }
```
Response `data`: **ExtensionRequestResponse** (bare, no `item_name`/`requester_name`):
```json
{
  "id": "uuid", "original_request_id": "uuid", "requester_id": "uuid",
  "current_assigned_to": "datetime", "extended_to": "datetime", "status": "ExtensionStatus",
  "requires_mgr_approval": true, "manager_id": "uuid|null", "mgr_approval_status": "MgrApprovalStatus",
  "manager_note": "string|null", "manager_decided_at": "datetime|null",
  "it_decided_by": "uuid|null", "it_note": "string|null", "it_decided_at": "datetime|null",
  "created_at": "datetime", "updated_at": "datetime"
}
```
Approving pushes the new end date onto the parent request (`assigned_to`) automatically.

#### `PATCH /admin/extension-requests/{extension_request_id}/reject`
**Used in:** A11 "Reject" action. Only valid while `status` is `pending` — 409 if already approved/rejected (e.g. don't allow rejecting a decided extension).
Request:
```json
{ "it_note": "string|null" }
```
Response `data`: **ExtensionRequestResponse** (same bare shape as `approve` above).

---

## Module: Handovers (`/api/v1/admin/handover-requests`) — IT Admin only, read-only — Screen A12

Peer-to-peer device handovers are requested/accepted by employees directly (not via this API — that's a separate employee-facing flow outside this module's scope). IT only gets a read/audit view here — there is no approve/reject action for IT to call.

| Method | Path | Description |
|---|---|---|
| GET | `/admin/handover-requests` | List handovers, optional `status`/`item_id` filters. |

#### `GET /admin/handover-requests`
**Used in:** A12 audit table. Filter by `item_id` when reached via a "view handover history" link from A05 Device Detail.
Query params: `status` (`HandoverStatus`), `item_id` (uuid). Response `data`: array of **HandoverListItem**:
There is **no per-handover detail endpoint** (`GET /admin/handover-requests/{id}`) — the list already carries every field needed for a row, so a detail drill-down isn't required. A12's per-row "Timeline" action should call the device's own audit log — `GET /admin/items/{item_id}/timeline` — not a handover-specific endpoint that doesn't exist.
```json
{
  "id": "uuid", "item_id": "uuid", "owner_id": "uuid", "borrower_id": "uuid",
  "requested_duration_hours": 0, "status": "HandoverStatus",
  "requested_at": "datetime", "decided_at": "datetime|null", "completed_at": "datetime|null",
  "note": "string|null", "created_at": "datetime", "updated_at": "datetime",
  "item_name": "string", "owner_name": "string", "borrower_name": "string"
}
```

---

## Module: Users (`/api/v1/admin/users`) — IT Admin only — Screen A14

| Method | Path | Paginated | Description |
|---|---|---|---|
| GET | `/admin/users` | yes | List users with filters. |
| POST | `/admin/users` | — | Create a user (shared dev password — see note). |
| PATCH | `/admin/users/{user_id}/role` | — | Change a user's role. |
| PATCH | `/admin/users/{user_id}/deactivate` | — | Deactivate a user (hard-blocks with 409 if they hold devices/open requests). |
| PATCH | `/admin/users/{user_id}/activate` | — | Reactivate a user. |

**No endpoint sets or changes a user's manager.** `manager_id` is exposed as a read-only field on every user response (and joined as `manager_name` in the list), but neither `POST /admin/users` nor `PATCH /admin/users/{id}/role` (nor any other route) accepts a `manager_id` — there is currently no way to assign/reassign a user's manager via the IT-Admin API at all. A14's "Manager" column is therefore display-only; if the mockup implies an editable manager picker, that's an open gap to raise with backend, not something FE can wire today.

#### `GET /admin/users`
**Used in:** A14 Settings → Users table.
Query params: `role` (`UserRole`), `is_active` (bool), `search` (string — matches name/email), plus pagination.
Response `data`: array of **UserListItemResponse**:
```json
{
  "id": "uuid", "name": "string", "email": "string", "role": "UserRole",
  "manager_id": "uuid|null", "is_active": true, "created_at": "datetime", "updated_at": "datetime",
  "manager_name": "string|null"
}
```

#### `POST /admin/users` (201)
**Used in:** A14 "Invite User" / "Add User" form.
Request:
```json
{ "name": "string", "email": "user@example.com", "role": "employee|manager|it_admin" }
```
Response `data`: **UserResponse** (`UserListItemResponse` fields minus `manager_name`):
```json
{
  "id": "uuid", "name": "string", "email": "string", "role": "UserRole",
  "manager_id": "uuid|null", "is_active": true, "created_at": "datetime", "updated_at": "datetime"
}
```
This bare `UserResponse` shape is reused verbatim by `role`/`deactivate`/`activate` below.
**Password behavior (corrects a previous version of this doc):** this endpoint DOES set a password — every user created here gets the same hardcoded shared dev password (`"Password123!"`, `app/services/user_service.py`), identical to the one used for all seed users. The new user CAN log in immediately with that password. This is **not** a real invite flow (no invite token, no temp/random password, no forced reset, no email sent) — it's a shared static credential. Treat "Invite User" copy carefully: don't imply an emailed/secure invite happened. Flag to backend as a security shortcut if a real per-user invite/reset flow is needed before this ships.

#### `PATCH /admin/users/{user_id}/role`
**Used in:** A14 row action "Change Role".
Request:
```json
{ "role": "employee|manager|it_admin" }
```
Response `data`: **UserResponse** (same bare shape as `POST /admin/users` above).

#### `PATCH /admin/users/{user_id}/deactivate`
**Used in:** A14 row action "Deactivate". Handle the `409 CONFLICT` case explicitly in the UI (message like "Cannot deactivate — user still holds N device(s)/has open requests; return devices first") rather than a generic error.
No body. Response `data`: **UserResponse** (same bare shape as `POST /admin/users` above).

#### `PATCH /admin/users/{user_id}/activate`
**Used in:** A14 row action "Activate" (shown for already-deactivated users).
No body. Response `data`: **UserResponse** (same bare shape as `POST /admin/users` above).

---

## Quick endpoint index

```
Auth
  POST   /api/v1/auth/register                                        (no screen wired — see Notes)
  POST   /api/v1/auth/login                                           Login screen
  POST   /api/v1/auth/refresh                                         background / interceptor
  GET    /api/v1/auth/me                                               App shell bootstrap

Dashboard — A01
  GET    /api/v1/admin/dashboard/summary
  GET    /api/v1/admin/dashboard/recent-requests
  GET    /api/v1/admin/dashboard/open-support

Dropdowns — shared form data
  GET    /api/v1/admin/dropdowns/item-categories                       A04 add-device form
  GET    /api/v1/admin/dropdowns/managers                               A03 escalate-to-manager
  GET    /api/v1/admin/dropdowns/employees                              A07 direct assignment

Items / Inventory — A04, A05, A06, A07, A10
  GET    /api/v1/admin/items                                            A04 list / A10 filtered view
  POST   /api/v1/admin/items                                            A04 add device
  GET    /api/v1/admin/items/client-available                           A07 device picker
  PATCH  /api/v1/admin/items/{item_id}                                  A04/A05 edit device
  PATCH  /api/v1/admin/items/{item_id}/status                           A04/A05/A10 change-status modal
  GET    /api/v1/admin/items/{item_id}                                  A05 device detail
  GET    /api/v1/admin/items/{item_id}/timeline                         A06 timeline
  GET    /api/v1/admin/items/{item_id}/bookings                         A05 calendar / A03 assign panel
  POST   /api/v1/admin/items/{item_id}/direct-assign                    A07 confirm assignment

Requests & Approvals — A02, A03
  GET    /api/v1/admin/requests                                         A02 main table
  GET    /api/v1/admin/requests/{request_id}                            A03 detail load
  GET    /api/v1/admin/it/approvals                                     A02 IT approval queue tab
  PATCH  /api/v1/admin/requests/{request_id}/reject                     A03 reject action
  PATCH  /api/v1/admin/requests/{request_id}/cancel                     A03 cancel action
  PATCH  /api/v1/admin/requests/{request_id}/escalate-to-manager        A03 escalate action
  GET    /api/v1/admin/requests/{request_id}/suggested-devices          A03 device picker
  PATCH  /api/v1/admin/requests/{request_id}/booking-range              A03 adjust dates (post-assign)
  POST   /api/v1/admin/requests/{request_id}/assign                     A03 confirm assignment

Shipping & Returns — A09
  GET    /api/v1/admin/shipping/outbound                                A09 outbound tab
  GET    /api/v1/admin/shipping/returns                                 A09 returns tab
  POST   /api/v1/admin/requests/{request_id}/ship                       A09 mark shipped
  POST   /api/v1/admin/requests/{request_id}/confirm-delivery           A09 confirm delivery
  POST   /api/v1/admin/requests/{request_id}/complete-return            A09 complete return

Support Requests — A08
  GET    /api/v1/admin/support-requests                                 A08 queue table
  GET    /api/v1/admin/support-requests/{support_request_id}            A08 detail panel
  PATCH  /api/v1/admin/support-requests/{support_request_id}/start      A08 start action
  PATCH  /api/v1/admin/support-requests/{support_request_id}/resolve    A08 resolve panel

Extension Requests — A11
  GET    /api/v1/admin/extension-requests                               A11 main table
  GET    /api/v1/admin/extension-requests/{extension_request_id}        A11 detail panel
  PATCH  /api/v1/admin/extension-requests/{extension_request_id}/approve A11 approve action
  PATCH  /api/v1/admin/extension-requests/{extension_request_id}/reject  A11 reject action

Handovers (read-only) — A12
  GET    /api/v1/admin/handover-requests                                A12 audit table

Users — A14
  GET    /api/v1/admin/users                                            A14 users table
  POST   /api/v1/admin/users                                            A14 add/invite user
  PATCH  /api/v1/admin/users/{user_id}/role                             A14 change role
  PATCH  /api/v1/admin/users/{user_id}/deactivate                       A14 deactivate
  PATCH  /api/v1/admin/users/{user_id}/activate                         A14 activate

Health (no auth, outside /api/v1) — infra probes, not FE
  GET    /health/live
  GET    /health/ready
```

## Notes for FE integration

- **A13 QR Management and the A14 Category-CRUD tab have no backend endpoints** — out of scope for this build. Don't wire buttons for them yet.
- **`POST /auth/register` has no auth guard and isn't wired to any admin screen.** Confirm with backend whether FE should ever call it directly, or whether all user creation should go through `POST /admin/users` (A14) instead. Unlike an earlier version of this doc claimed, `POST /admin/users` **does** set a password (a shared hardcoded dev value — see the Users module note) so the created user can log in immediately; the remaining open question is whether that's acceptable for production, not whether login works at all.
- **No login screen exists in the IT-Admin mockup.** The Auth module (`login`/`refresh`/`me`) has no A0x screen backing it in this design file — it's included here because the admin app still needs it for session bootstrap; there's simply no corresponding mock to cross-check it against.
- **There is no API to set or change a user's manager** — `manager_id` is read-only everywhere. If A14 implies manager assignment is editable, that's a real gap, not an FE integration detail.
- **Email/notifications are no-ops.** Places the design doc mentions "email requester" (e.g. after booking-range changes) do not actually send anything server-side yet — don't build FE copy that promises an email was sent.
- **Handovers are peer-to-peer, not an IT action.** A12 is read-only by design; there's no reject/approve button to build there. Its "Timeline" row action should hit `GET /admin/items/{item_id}/timeline`, not a (nonexistent) handover-detail endpoint.
- **`suggested-devices` (A03) is a deterministic sort**, not ML — despite the mockup's "AI ranking" label, avoid FE copy implying machine learning.
- **Deactivating a user (A14) hard-blocks with 409** if they hold devices or have open requests — this is intentional (deviates from a literal "just flip is_active"); build the inline error state rather than treating it as a generic failure.
- **A02's status tab-chip counts and A09/A01's "in transit" style counters are all FE-derived** — from `meta.pagination.total_items` (one call per status) or from response-array length; there's no single aggregate-counts endpoint anywhere in this API.
