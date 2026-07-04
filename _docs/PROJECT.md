# PROJECT.md — IT Asset Management (ITAM) System

> **Read this file first.** It gives any developer or AI enough context to
> orient on this project in a few minutes — what we're building, why, the
> scope, the rules, and where to look for more depth. This file is
> intentionally high-level. For detail, see the [Document Map](#document-map)
> at the bottom.

---

## What We're Building

An internal platform for a company to manage physical IT assets across their
full lifecycle — inventory → employee request → assignment → optional WFH
shipping → support/repair → temporary peer-to-peer handover → return →
retirement — with a **complete, permanent, append-only audit trail per
device**.

This is a **hackathon-scoped MVP**. Cuts to scope are deliberate, not
oversights — see [Section 6](#key-business-rules).

**In scope:** laptops, phones, tablets, monitors, and small peripherals —
discrete devices assignable to exactly one person at a time.

**Out of scope:** delivery/courier logistics, vendor management, procurement,
software licenses, in-app real-time notifications, multi-level approvals,
bulk import.

---

## Why

Distributed/hybrid teams need one place to know who has what device, since
when, in what condition, and with what history — replacing spreadsheets and
Slack threads with enforced approval policy and a queryable audit trail.

---

## User Roles

| Role | Responsibility |
|---|---|
| **Employee** | Request devices, view assigned device(s), file support tickets, initiate/accept handovers, track status |
| **Manager** | Approve/reject requests requiring sign-off, for direct reports only |
| **IT Admin** | Manage inventory, approve/assign requests, handle support, process shipping and returns, full audit access |

A user's manager is set via self-service profile edit — no separate admin
workflow.

---

## Core Terminology

| Term | Meaning |
|---|---|
| **Item** | A single physical, serialized device — the unit of assignment |
| **Item Category** | A device type (e.g. "iPhone 16 Pro"). Approval policy lives here, not on individual units |
| **Request** | An employee's ask for a device from a category, over a date range; goes through approval → assignment |
| **Extension Request** | A separate ask to push an *existing* assignment's end date out |
| **Support Request** | A ticket against an assigned device: `update`, `damage`, or `lost` |
| **Handover Request** | A peer-to-peer, IT-uninvolved temporary loan of an assigned device, initiated by QR scan — a full tracked workflow (requested → accepted → completed, or rejected/cancelled) |
| **WFH Shipping** | Optional courier leg (outbound or return) for non-co-located employees, carrying a tracking link |
| **Client Device** | Client-owned, tracked in inventory, assigned directly by IT with no request lifecycle |
| **Device Timeline** | The permanent, chronological history of everything that happened to one device |

---

## Major Features

- Inventory management with per-device audit history
- Date-range device requests with type-level manager approval and an
  IT suggestion window that checks real availability against existing bookings
- Conditional WFH shipping (outbound and return legs)
- Support ticketing (update / damage / lost) with repair-in-place, swap, or
  loss outcomes
- Assignment extension as its own approval workflow
- Peer-to-peer temporary handover as its own tracked workflow
- Append-only, per-device audit log with a milestone/full view split
- Email-only notifications on every meaningful status change

---

## Key Business Rules

1. **One device, one active claim.** A device can never be the target of two
   simultaneously active (non-terminal) requests. This is a hard constraint,
   not a UI convention — it's what prevents nearly every double-allocation
   scenario across shipping, repair, and swap flows.
2. **Nothing is deleted.** Requests, extension requests, and handover
   requests are permanent records. A successful request always ends in
   `completed` status — it is never soft-deleted or removed. This preserves
   full history for audit and future analytics.
3. **IT holds sole authority over returns and post-incident status.**
   Neither employees nor managers can force a device back into the pool.
   Return-initiation can come from either side (on-site vs. WFH), but only
   IT decides the device's next status, and only at physical receipt.
4. **Approval states are never a single boolean.** "Not required,"
   "pending," "approved," "rejected" are always modeled as explicit distinct
   states.
5. **Automatic (system-triggered) state changes are avoided by default.**
   The only one in the system is auto-closing support tickets when their
   request completes. Notably, marking a device **Lost** does **not**
   automatically retire it — IT must manually decide its next status, like
   any other status change.
6. **Ownership persists through recoverable interruptions.** Repair-in-place
   and device swaps keep the original request/owner intact; ownership only
   clears at final completion.
7. **A handover never changes device status or ownership**, at any stage of
   its own lifecycle.
8. **Type-level flags drive initial approval routing; device-level flags
   only drive later IT escalation**, since no specific unit is known at
   request creation.
9. **Anything not enforced is honestly labeled as informational** (e.g.
   handover duration, requested vs. assigned date ranges) — no UI or logic
   should imply enforcement that doesn't exist.

---

## Architecture Overview

A single monolithic backend service (easy to split later) fronting:

- **Web app** — full platform access for all three roles
- **Mobile app** — QR scanning, handover, device view
- **Core API** — inventory, requests, support, handover, shipping, users
- **Notification service** — email dispatch on domain events
- **Auth service** — role-based access, enforced at the gateway and
  re-validated in handlers
- **PostgreSQL** — all entities and the append-only audit log

Architecture principles: append-only log tables, domain events drive
notifications, role-based access control at every layer.

---

## Assumptions & Constraints

- One manager per employee; no approval chains.
- A device is assignable to exactly one active request at a time (enforced,
  not just conventional).
- "Assigned" covers the full duration including WFH transit — a device is
  never "free" while in any shipping state.
- Requested date ranges are intent; IT's confirmed range is authoritative.
- Employees are trusted to accurately report issues and handover durations;
  no remote condition verification beyond explicit IT assessment.

---

## Document Map

This file is the **entry point**. Everything else goes deeper and must stay
consistent with the rules above — if a conflict appears, this file wins and
the other document gets corrected.

| Document | Covers |
|---|---|
| `WORKFLOWS.md` | Step-by-step business workflows, edge cases, and the reasoning behind non-obvious design decisions |
| `schema_v3.dbml` / `DATABASE.md` (future) | Entities, fields, constraints, indexes |
| `API.md` (future) | Endpoint contracts, request/response shapes |
| `FRONTEND.md` (future) | Screens per role, navigation, components |
| `DEVOPS.md` (future) | Deployment, environments, infra |
| `AI.md` (future) | Any AI-assisted features |

If a new document needs a workflow rule or rationale not captured here or in
`WORKFLOWS.md`, add it there first — don't let business logic drift into a
schema or API doc where it can silently diverge from actual behavior.
