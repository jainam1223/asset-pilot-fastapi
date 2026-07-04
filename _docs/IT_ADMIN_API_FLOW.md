# IT_ADMIN_API_FLOW.md — Desktop (IT Admin) Module

> Scope: IT Admin operations only. Manager approval flows are handled via the
> mobile app. All endpoints scoped to the authenticated IT Admin via JWT
> (`:userId`). List endpoints support standard pagination (omitted below).
> Every state-changing write involving a device is paired with a `device_log`
> insert per `WORKFLOWS.md` §9–10.

---

## 1. Dashboard

### Get Summary KPIs

- **Endpoint:** `GET /admin/dashboard/summary`
- **Method:** GET
- **Request Args:** none
- **Response:**

```json
{
  "status_breakdown": {
    "available": 0,
    "assigned": 0,
    "under_repair": 0,
    "maintenance": 0,
    "shipping_pending": 0,
    "return_shipping_pending": 0,
    "lost": 0,
    "retired": 0
  },
  "pending_requests_count": 0,
  "open_support_count": 0,
  "active_handovers_count": 0,
  "pending_extensions_count": 0
}
```

- **Backend Logic:** Parallel aggregates — `item` grouped by `status`; `request WHERE status IN ('pending_mgr_approval','pending_it_approval')`; `support_request WHERE status IN ('open','in_progress')`; `handover_request WHERE status = 'accepted'`; `extension_request WHERE status = 'pending'`.

### Get Recent Requests

- **Endpoint:** `GET /admin/dashboard/recent-requests`
- **Method:** GET
- **Request Args:** `limit` (default 10)
- **Response:** `request.*` + `item_category.name` + requester `name` from `user`
- **Backend Logic:** `request JOIN user JOIN item_category ORDER BY created_at DESC LIMIT :limit`.

### Get Open Support Snapshot

- **Endpoint:** `GET /admin/dashboard/open-support`
- **Method:** GET
- **Request Args:** `limit` (default 10)
- **Response:** `support_request.*` + `item.name`
- **Backend Logic:** `support_request WHERE status IN ('open','in_progress') JOIN item ORDER BY filed_at ASC LIMIT :limit`.

---

## 2. Request Management

### List All Requests

- **Endpoint:** `GET /admin/requests`
- **Method:** GET
- **Request Args:** `status, category_id, priority, requested_from, requested_to, search` (all optional)
- **Response:** `request.*` + `item_category.name` + requester `name` from `user`
- **Backend Logic:** `request JOIN user JOIN item_category` with optional filters. `search` matches requester `name`/`email`. All rows permanent (`PROJECT.md` Rule 2) — completed/rejected requests remain queryable indefinitely.

### Get Request Detail

- **Endpoint:** `GET /admin/requests/{id}`
- **Method:** GET
- **Request Args:** `id` (path)
- **Response:** `request.*` + `item_category.name` + requester/manager/decision-actor names from `user` + `item.*` via `assigned_item_id` if set
- **Backend Logic:** Single-row `request` fetch with all joins.

---

## 3. IT Approval Queue

### List IT Approval Queue

- **Endpoint:** `GET /admin/it/approvals`
- **Method:** GET
- **Request Args:** none
- **Response:** `request.*` + `item_category.name` + requester `name` from `user`
- **Backend Logic:** `request WHERE status = 'pending_it_approval' ORDER BY priority DESC, created_at ASC` (`idx_request_it_queue`).

### Reject Request

- **Endpoint:** `PATCH /admin/requests/{id}/reject`
- **Method:** PATCH
- **Request Args:** `{ rejected_reason, it_decision_note }`
- **Response:** `request.*`
- **Backend Logic:** Validate `status = 'pending_it_approval'`. Update `status = 'rejected'`, `rejected_by = 'it_admin'`, `rejected_reason`, `it_decision_note`, `it_decided_by = :userId`, `it_decided_at = now()`.

### Cancel Request

- **Endpoint:** `PATCH /admin/requests/{id}/cancel`
- **Method:** PATCH
- **Request Args:** `{ rejected_reason }`
- **Response:** `request.*`
- **Backend Logic:** Validate `status` is non-terminal. Update `status = 'cancelled'`, `cancelled_by = :userId`, `cancelled_at = now()`, `rejected_by = 'it_admin_cancel'`, `rejected_reason`.

### Escalate to Manager

- **Endpoint:** `PATCH /admin/requests/{id}/escalate-to-manager`
- **Method:** PATCH
- **Request Args:** `{ manager_id }` (optional — defaults to requester's `user.manager_id`)
- **Response:** `request.*`
- **Backend Logic:** Validate `status = 'pending_it_approval'`, `requires_mgr_approval = false`. Update `requires_mgr_approval = true`, `mgr_approval_status = 'pending'`, `manager_id`, `status = 'pending_mgr_approval'`.

---

## 4. Device Assignment

### Get Suggested Devices

- **Endpoint:** `GET /admin/requests/{id}/suggested-devices`
- **Method:** GET
- **Request Args:** `id` (path)
- **Response:** `item.*` + `item_category.name` + `active_bookings_count`
- **Backend Logic:** `item WHERE category_id = request.category_id AND status = 'available'` (`idx_item_available_by_category`), excluding devices with a conflicting `request` row where `assigned_from < request.requested_to AND assigned_to > request.requested_from` (`idx_request_date_range`). Sorted by fewest active requests, then longest free.

### Get Device Booking Calendar

- **Endpoint:** `GET /admin/items/{itemId}/bookings`
- **Method:** GET
- **Request Args:** `itemId` (path)
- **Response:** `[ request.* + requester name from user ]`
- **Backend Logic:** `request WHERE assigned_item_id = :itemId AND status = 'assigned' ORDER BY assigned_from`.

### Adjust Existing Booking Range

- **Endpoint:** `PATCH /admin/requests/{id}/booking-range`
- **Method:** PATCH
- **Request Args:** `{ assigned_from, assigned_to }`
- **Response:** `request.*`
- **Backend Logic:** Validate `status = 'assigned'`. Update range, re-check no new overlap on the same device with any other active request. Triggers email notification to the affected requester per `WORKFLOWS.md` §5.

### Assign Device to Request

- **Endpoint:** `POST /admin/requests/{id}/assign`
- **Method:** POST
- **Request Args:** `{ item_id, assigned_from, assigned_to, is_wfh }`
- **Response:** `request.*`
- **Backend Logic:** Validate `request.status = 'pending_it_approval'`, `item.status = 'available'`, `item.category_id = request.category_id`, no overlapping active request on `item`. Update `request`: `assigned_item_id = item_id`, `assigned_from`, `assigned_to`, `is_wfh`, `it_decided_by = :userId`, `it_decided_at = now()`, `status = 'assigned'`. Update `item`: `status = 'assigned'`, `current_owner_id = request.requester_id`. `device_log` insert: `event_type = 'assigned'`, `actor_role = 'it_admin'`, `item_id`, `request_id`, `is_milestone = true`. WFH shipment is initiated separately via §10.

---

## 5. Direct Client Device Assignment

### List Available Client Devices

- **Endpoint:** `GET /admin/items/client-available`
- **Method:** GET
- **Request Args:** `category_id, search` (optional)
- **Response:** `item.*` + `item_category.name`
- **Backend Logic:** `item WHERE owner_type = 'client' AND status = 'available'`.

### Direct-Assign Client Device

- **Endpoint:** `POST /admin/items/{itemId}/direct-assign`
- **Method:** POST
- **Request Args:** `{ employee_id, assigned_from, assigned_to }`
- **Response:** `request.*`
- **Backend Logic:** Validate `item.owner_type = 'client'`, `item.status = 'available'`. Insert `request`: `is_client_direct = true`, `status = 'assigned'`, `category_id = item.category_id`, `requester_id = employee_id`, `assigned_item_id = itemId`, `assigned_from`, `assigned_to`, `it_decided_by = :userId`, `it_decided_at = now()`. Update `item`: `status = 'assigned'`, `current_owner_id = employee_id`. `device_log` insert: `event_type = 'client_assigned'`, `actor_role = 'it_admin'`, `item_id = itemId`, `request_id`, `is_milestone = true`.

---

## 6. Inventory Management

### List Devices

- **Endpoint:** `GET /admin/items`
- **Method:** GET
- **Request Args:** `category_id, status, owner_type, search` (all optional)
- **Response:** `item.*` + `item_category.name` + `current_owner` name from `user`
- **Backend Logic:** `item JOIN item_category LEFT JOIN user ON current_owner_id` with filters. `search` matches `name`/`serial_no`.

### Create Device

- **Endpoint:** `POST /admin/items`
- **Method:** POST
- **Request Args:** `{ name, serial_no, category_id, owner_type, client_name, purchase_date }`
- **Response:** `item.*`
- **Backend Logic:** Insert `item`, `status` defaults to `'available'`. `client_name` only set when `owner_type = 'client'`. `device_log` insert: `event_type = 'device_created'`, `actor_role = 'it_admin'`, `item_id`, `is_milestone = false`.

### Edit Device

- **Endpoint:** `PATCH /admin/items/{itemId}`
- **Method:** PATCH
- **Request Args:** `{ name, category_id, client_name, purchase_date }`
- **Response:** `item.*`
- **Backend Logic:** Update provided fields. `device_log` insert: `event_type = 'device_edited'`, `actor_role = 'it_admin'`, `item_id`, `is_milestone = false`.

### Change Device Status

- **Endpoint:** `PATCH /admin/items/{itemId}/status`
- **Method:** PATCH
- **Request Args:** `{ status, it_note }`
- **Response:** `item.*`
- **Backend Logic:** Update `item.status`. `device_log.event_type` by target: `lost` → `marked_lost`; `retired` → `retired`; `returned_to_client` → `returned_to_client`; all others (`available`, `under_repair`, `maintenance`) → `status_changed`. `actor_role = 'it_admin'` always — never system-triggered. `is_milestone = true`. No automatic Lost → Retired transition (`PROJECT.md` Rule 5).

---

## 7. Device Detail & Timeline

### Get Device Detail

- **Endpoint:** `GET /admin/items/{itemId}`
- **Method:** GET
- **Request Args:** `itemId` (path)
- **Response:**

```json
{
  "item": "item.*",
  "category": "item_category.*",
  "current_owner": "user.*",
  "current_request": "request.*",
  "open_support": "[ support_request.* ]",
  "active_handover": "handover_request.*"
}
```

- **Backend Logic:** `item` + active `request` (`assigned_item_id = itemId AND status = 'assigned'`) + `support_request WHERE item_id = itemId AND status IN ('open','in_progress')` + `handover_request WHERE item_id = itemId AND status = 'accepted'`.

### Get Device Timeline

- **Endpoint:** `GET /admin/items/{itemId}/timeline`
- **Method:** GET
- **Request Args:** `milestones_only` (boolean, default `true`)
- **Response:** `[ device_log.* ]`
- **Backend Logic:** `device_log WHERE item_id = :itemId [AND is_milestone = true] ORDER BY occurred_at ASC`. Append-only — no update/delete path exists by design.

---

## 8. Support Requests

### List Support Requests

- **Endpoint:** `GET /admin/support-requests`
- **Method:** GET
- **Request Args:** `status, type, item_id` (all optional)
- **Response:** `support_request.*` + `item.name` + requester `name` from `user`
- **Backend Logic:** `support_request JOIN item JOIN user` with filters. Default order `filed_at ASC` (`idx_support_open_queue`).

### Get Support Request Detail

- **Endpoint:** `GET /admin/support-requests/{id}`
- **Method:** GET
- **Request Args:** `id` (path)
- **Response:** `support_request.*` + `item.*` + requester `user.*`
- **Backend Logic:** Single-row fetch with joins.

### Mark In Progress

- **Endpoint:** `PATCH /admin/support-requests/{id}/start`
- **Method:** PATCH
- **Request Args:** none
- **Response:** `support_request.*`
- **Backend Logic:** Update `status = 'in_progress'`. If `type = 'damage'`: `item.status = 'under_repair'`, `device_log` insert: `event_type = 'status_changed'`, `support_request_id`, `item_id`, `actor_role = 'it_admin'`, `is_milestone = true`.

### Resolve Support Request

- **Endpoint:** `PATCH /admin/support-requests/{id}/resolve`
- **Method:** PATCH
- **Request Args:** `{ resolution, it_note, swapped_to_item_id, old_item_next_status }` (last two only when `resolution = 'swapped'`)
- **Response:** `support_request.*`
- **Backend Logic:** Update `support_request`: `status = 'resolved'`, `resolution`, `it_note`, `resolved_by = :userId`, `resolved_at = now()`. Then by `resolution`:
  - `remote_resolved`: no `item.status` change.
  - `repaired_in_place`: `item.status = 'assigned'`. `device_log`: `status_changed`, `from_value = 'under_repair'`, `to_value = 'assigned'`, `is_milestone = true`.
  - `swapped`: validate `swapped_to_item_id.status = 'available'` and same `category_id`. Repoint `request.assigned_item_id = swapped_to_item_id`. Old item: `status = old_item_next_status`, `current_owner_id = NULL`. New item: `status = 'assigned'`, `current_owner_id = request.requester_id`. `device_log` on old item: `swapped_out`, `metadata: { swapped_to_item_id }`, `is_milestone = true`. `device_log` on new item: `swapped_in`, `metadata: { swapped_from_item_id }`, `is_milestone = true`.
  - `marked_lost`: `item.status = 'lost'`. Complete tied `request`: `status = 'completed'`, `completed_at = now()`, `completed_by = :userId`, `completed_next_status = NULL`. `device_log`: `marked_lost`, `is_milestone = true`.
  - All cases: `device_log` insert: `event_type = 'support_resolved'`, `support_request_id`, `item_id`, `actor_role = 'it_admin'`, `is_milestone = true`.

---

## 9. Extension Requests

### List Extension Requests

- **Endpoint:** `GET /admin/extension-requests`
- **Method:** GET
- **Request Args:** `status` (optional)
- **Response:** `extension_request.*` + `item.name` + requester `name` from `user`
- **Backend Logic:** `extension_request JOIN request JOIN item JOIN user`.

### Get Extension Request Detail

- **Endpoint:** `GET /admin/extension-requests/{id}`
- **Method:** GET
- **Request Args:** `id` (path)
- **Response:** `extension_request.*` + parent `request.*` + `item.*` + requester `user.*`
- **Backend Logic:** Single-row fetch with joins.

### Approve Extension

- **Endpoint:** `PATCH /admin/extension-requests/{id}/approve`
- **Method:** PATCH
- **Request Args:** `{ it_note }`
- **Response:** `extension_request.*`
- **Backend Logic:** Validate `status = 'pending'`, `mgr_approval_status IN ('not_required','approved')`. Update parent `request.assigned_to = extension_request.extended_to`. Update `extension_request`: `status = 'approved'`, `it_decided_by = :userId`, `it_note`, `it_decided_at = now()`. `device_log` insert on parent device: `event_type = 'extension_approved'`, `extension_request_id`, `item_id`, `actor_role = 'it_admin'`, `is_milestone = false`.

### Reject Extension

- **Endpoint:** `PATCH /admin/extension-requests/{id}/reject`
- **Method:** PATCH
- **Request Args:** `{ it_note }`
- **Response:** `extension_request.*`
- **Backend Logic:** Update `status = 'rejected'`, `it_decided_by = :userId`, `it_note`, `it_decided_at = now()`. `device_log` insert: `event_type = 'extension_rejected'`, `extension_request_id`, `item_id`, `actor_role = 'it_admin'`, `is_milestone = false`.

---

## 10. WFH Shipping

### Get Outbound Shipping Queue

- **Endpoint:** `GET /admin/shipping/outbound`
- **Method:** GET
- **Request Args:** none
- **Response:** `request.*` + `item.name` + requester `name` from `user`
- **Backend Logic:** `request WHERE is_wfh = true AND status = 'assigned' AND ship_initiated_at IS NULL`.

### Mark Shipped

- **Endpoint:** `POST /admin/requests/{id}/ship`
- **Method:** POST
- **Request Args:** `{ ship_tracking_url }`
- **Response:** `request.*`
- **Backend Logic:** Validate `request.is_wfh = true`, `item.status = 'assigned'`. Update `request.ship_tracking_url`, `ship_initiated_at = now()`. Update `item.status = 'shipping_pending'`. `device_log` insert: `event_type = 'ship_outbound_initiated'`, `item_id`, `actor_role = 'it_admin'`, `metadata: { ship_tracking_url }`, `is_milestone = false`.

### Confirm Delivery

- **Endpoint:** `POST /admin/requests/{id}/confirm-delivery`
- **Method:** POST
- **Request Args:** none
- **Response:** `request.*`
- **Backend Logic:** Validate `item.status = 'shipping_pending'`. Update `request.ship_completed_at = now()`, `item.status = 'assigned'`. `device_log` insert: `event_type = 'ship_outbound_completed'`, `item_id`, `actor_role = 'it_admin'`, `is_milestone = false`.

---

## 11. Device Returns

### Get WFH Return Queue

- **Endpoint:** `GET /admin/shipping/returns`
- **Method:** GET
- **Request Args:** none
- **Response:** `request.*` + `item.name` + requester `name` from `user`
- **Backend Logic:** `request JOIN item WHERE item.status = 'return_shipping_pending'`.

### Complete Return

- **Endpoint:** `POST /admin/requests/{id}/complete-return`
- **Method:** POST
- **Request Args:** `{ next_status }` (`available | under_repair | retired`)
- **Response:** `request.*`
- **Backend Logic:** Validate `item.status IN ('assigned','return_shipping_pending')` — `assigned` for on-site, `return_shipping_pending` for WFH. Update `request`: `status = 'completed'`, `completed_at = now()`, `completed_by = :userId`, `completed_next_status = next_status`. Update `item`: `status = next_status`, `current_owner_id = NULL`. `device_log` insert: `event_type = 'return_received'`, `item_id`, `actor_role = 'it_admin'`, `to_value = next_status`, `is_milestone = true`. Cascade: auto-close any `support_request WHERE item_id = itemId AND status IN ('open','in_progress')` — set `status = 'resolved'`, `auto_closed = true`, `resolved_at = now()`; `device_log` insert per ticket: `event_type = 'support_auto_closed'`, `actor_role = 'system'`, `is_milestone = false`.

---

## 12. Temporary Handovers (Audit View)

IT view is read-only. Workflow is peer-to-peer via employee mobile app (`WORKFLOWS.md` §7).

### List Handovers

- **Endpoint:** `GET /admin/handover-requests`
- **Method:** GET
- **Request Args:** `status, item_id` (optional)
- **Response:** `handover_request.*` + `item.name` + owner/borrower `name` from `user`
- **Backend Logic:** `handover_request JOIN item JOIN user (owner) JOIN user (borrower)` with filters.

---

## 13. User Management

### List Users

- **Endpoint:** `GET /admin/users`
- **Method:** GET
- **Request Args:** `role, is_active, search` (all optional)
- **Response:** `user.*` + manager `name` from `user`
- **Backend Logic:** `user LEFT JOIN user ON manager_id` with filters. `search` matches `name`/`email`.

### Invite User

- **Endpoint:** `POST /admin/users`
- **Method:** POST
- **Request Args:** `{ name, email, role }`
- **Response:** `user.*`
- **Backend Logic:** Insert `user`, `is_active = true`. `manager_id` not set here — self-service via employee profile per `PROJECT.md`.

### Edit User Role

- **Endpoint:** `PATCH /admin/users/{id}/role`
- **Method:** PATCH
- **Request Args:** `{ role }`
- **Response:** `user.*`
- **Backend Logic:** Update `user.role`.

### Deactivate / Activate User

- **Endpoint:** `PATCH /admin/users/{id}/deactivate` · `PATCH /admin/users/{id}/activate`
- **Method:** PATCH
- **Request Args:** none
- **Response:** `user.*`
- **Backend Logic:** Update `user.is_active`. No cascade to active devices/requests — requires manual IT-initiated return per the "employee leaves company" edge case in `WORKFLOWS.md`.

---

## 14. Dropdowns

### Item Categories

- **Endpoint:** `GET /admin/dropdowns/item-categories`
- **Method:** GET
- **Request Args:** none
- **Response:** `item_category.*`
- **Backend Logic:** `item_category WHERE is_active = true`.

### Managers

- **Endpoint:** `GET /admin/dropdowns/managers`
- **Method:** GET
- **Request Args:** none
- **Response:** `user.*`
- **Backend Logic:** `user WHERE role = 'manager' AND is_active = true`. Used by escalate-to-manager (§3).

### Employees

- **Endpoint:** `GET /admin/dropdowns/employees`
- **Method:** GET
- **Request Args:** none
- **Response:** `user.*`
- **Backend Logic:** `user WHERE role = 'employee' AND is_active = true`. Used by direct client assignment (§5).

---

## Gaps

1. **`is_wfh` at assignment (§4):** Wireframe shows an `is_wfh` toggle on the assign form implying IT can override the employee's flag. `WORKFLOWS.md` only describes it as employee-set at creation. Implemented as editable; confirm before building.
2. **Swap: old device next status (§8):** Wireframe Resolve Panel doesn't capture what happens to the old damaged device. `old_item_next_status` added as a required param — without it the old device is left in an undefined state.
3. **`marked_lost` request completion timing (§8):** Lost devices are never physically received, so the tied request completes immediately with `completed_next_status = NULL`. Device's next status is decided later via §6 Change Device Status. `WORKFLOWS.md` doesn't state this timing explicitly; confirm before building.
4. **Deactivating a user with active devices (§13):** No cascade defined in `WORKFLOWS.md` or schema. Requires a manual IT return — needs an explicit rule before building.
