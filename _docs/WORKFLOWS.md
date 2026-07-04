# WORKFLOWS.md — Business Workflows & Design Rationale

> Companion to `PROJECT.md`. Read that file first for high-level context,
> terminology, and roles. This document goes deep on **how each workflow
> actually runs, step by step**, plus the reasoning behind non-obvious design
> choices. Schema-level detail lives in the DBML files
> (`db_schemas.dbml` is current); this document explains _why_ the schema
> looks the way it does.

---

## 1. Device Request (Standard Path)

1. Employee selects a category, a date range (`requested_from` /
   `requested_to`), priority, and an optional note. Their manager is
   pre-filled from their profile.
2. If the category requires manager approval (a **type-level** flag,
   snapshotted onto the request at creation), it routes to the manager
   first; otherwise straight to IT. _Why type-level, not device-level:_ at
   creation time only a category is known, not a specific unit — a
   device-level flag can only matter later, when IT is escalating an
   already-in-progress request onto a specific unit.
3. Manager approves or rejects (optional comment). Rejection ends the
   request — but the request **row is never deleted**; it's retained
   permanently with `status = rejected` for history and analytics.
4. IT reviews in the **suggestion window**: available devices in the
   category, filtered to exclude any device whose confirmed
   (`assigned_from/to`) range overlaps the new request's dates, sorted by
   fewest active requests / longest-free.
5. IT selects a device and assigns it, setting `assigned_from/to` — IT's
   confirmed range, which may differ from what the employee asked for.
6. If WFH, routes through outbound shipping (Section 3) before becoming
   usable. If not, assigned directly.
7. **Every successful request ends in `status = completed`.** No soft
   delete, no row removal — the row persists forever as the audit/analytics
   record. "Completed" versus "still active" is purely a status filter on
   an always-permanent row.

## 2. Client Device (Direct Assignment)

Skips the request lifecycle entirely. IT assigns directly from inventory —
no approval flow, no request row behaving like a normal request lifecycle.
Full audit trail still exists via the device's own log.

## 3. WFH Shipping (Outbound and Return)

Conditional, not universal — only requests flagged `is_wfh`.

- **Outbound:** On approval, device → `shipping_pending`. IT adds a tracking
  link, visible to the employee. On courier confirmation, IT marks it
  delivered and the device → `assigned`.
- **Return:** Employee-initiated (unlike on-site returns, which are
  IT-initiated). Device → `return_shipping_pending`, employee supplies a
  tracking link. The device stays logically **assigned** — not returned to
  the pool — for the entire transit window, preventing double-allocation
  while in transit.
- **Receipt:** Only once IT confirms physical arrival does IT choose the
  next device status (Available / Under Repair / Retired) and the request
  completes. This decision happens **at receipt**, never at
  return-initiation — IT can't assess condition before holding the device.

On-site flows skip both shipping states — approval leads straight to
Assigned; IT-initiated return leads straight to the next-status decision
with no transit window.

## 4. Support Requests

Filed by the current assignee against their own assigned device.

| Type       | Flow                                                                                                                                                                                                                                                                                                                                            | Device Status Effect                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| **Update** | Remote-assisted fix (e.g. remote access session). Resolves without leaving Assigned.                                                                                                                                                                                                                                                            | None                                         |
| **Damage** | IT assesses: repairable in place (device cycles Assigned → Under Repair → Assigned, same owner, same request untouched) · or swap to a different unit (same request continues on the new device) · or unrecoverable (device marked Lost).                                                                                                       | Depends on outcome                           |
| **Lost**   | IT confirms the device cannot be located. Device is marked `lost`. **No automatic follow-on transition.** IT must separately, manually decide the device's next status (typically Retired, but not enforced) — logged as a normal `status_changed` event, `actor_role = it_admin`. There is deliberately no system-triggered state change here. | Lost (terminal until IT manually changes it) |

Any open support ticket **auto-closes** when its device's request completes
— a completed transaction cannot leave a dangling ticket. This _is_ a
system-triggered action (`support_auto_closed`, `actor_role = system`) — the
one legitimate automatic action left in the design, since it's a pure
cleanup with no ambiguity about outcome (see [Section 9](#9-automatic-vs-manual-state-changes)).

## 5. Date Ranges & The Suggestion Calendar

Every request carries `requested_from/to` (immutable employee intent) and,
once assigned, a separate `assigned_from/to` (IT's confirmed booking, which
may be narrower or shifted). The suggestion window uses this for real
availability checking — only devices with non-overlapping confirmed ranges
are suggested.

IT can see a device's existing bookings on a calendar and, if two requests
are close but not compatible, adjust an existing assignment's confirmed
range to make room — notifying the affected employee. This is IT-driven
negotiation support; the system surfaces conflicts, it does not resolve them
autonomously.

## 6. Extension Requests

A separate entity (`extension_request`), not a new device request. It asks
to push an existing assignment's `assigned_to` date further out, optionally
requiring the same manager+IT approval chain. On approval, the parent's
`assigned_to` moves and the extension row's `status` becomes `approved` —
**the row is retained permanently**, never deleted, same permanence rule as
the parent request. It never goes through device selection since the device
is already held by the employee. If the parent assignment completes before
the extension is decided, the extension auto-sets to `rejected` with a note
explaining the auto-cancellation — it cannot outlive the assignment it was
extending.

## 7. Temporary Handover (Peer-to-Peer)

Handover is a **full business workflow with its own lifecycle**, not merely
a log entry:

1. Borrower scans the QR code on an assigned device → creates a
   `handover_request` in `requested` status.
2. Multiple simultaneous `requested` rows against the same device are
   allowed (two people can scan and ask at once) — this is intentional, not
   a race condition.
3. Owner accepts or rejects. **Only one handover can be `accepted` (active)
   per device at a time** — first accept wins; any other pending requests
   for that device remain `requested` until the owner separately decides
   them (or they're naturally moot once one is accepted).
4. When the borrower physically returns the device, the owner marks the
   handover `completed`.
5. Duration (`requested_duration_hours`) remains informational only — not
   enforced, no auto-expiry.

**Device status and `current_owner_id` are never touched by a handover, at
any stage.** The owner of record stays the same throughout — this hasn't
changed. What changed is that the _process_ of requesting, accepting, and
completing a handover is now its own tracked entity with real states,
instead of being synthesized purely from log entries after the fact. The
device log still records every transition in this flow as it happens
(`handover_requested`, `handover_accepted`, `handover_rejected`,
`handover_cancelled`, `handover_completed`) — the log is the record of what
happened; the `handover_request` table is the source of truth for the
workflow's current state.

## 8. Returns

Two initiation paths, one completion gate:

- **On-site:** IT initiates directly.
- **WFH:** Employee initiates via return-shipping (Section 3).

Either way, only **IT** makes the final call on next device status, only
**at physical receipt** — never earlier. Single point of control by design.

## 9. Automatic vs. Manual State Changes

**Guiding rule: avoid automatic state changes unless absolutely necessary.**
As of this revision, there are exactly two system-triggered
(`actor_role = system`) actions in the entire design, and no others should
be added without strong justification:

1. `support_auto_closed` — closing an open support ticket when its parent
   request completes. Justified because leaving it open is unambiguously
   wrong (the transaction is over) and there's no judgment call involved.
2. _(Historically, Lost → Retired was automatic. This has been removed.)_
   IT now makes this decision manually, exactly like every other
   next-status decision in the system (return receipt, repair completion,
   etc.) — logged as a normal `status_changed` event with a human actor.

If a future feature proposes a new automatic transition, it should be
justified against this same bar: is the outcome truly unambiguous, or is
there a judgment call an automatic transition would be masking?

## 10. Audit Trail / Device Timeline

One continuous, append-only history per device. Two views over the same
log:

- **Default (milestone) view:** assignment start → return, support
  opened/resolved, handover accepted/completed, and any status change (Lost,
  Retired, Under Repair). The "what happened to this device" view.
- **Full view:** everything, including shipping sub-events, handover
  requested/rejected/cancelled, inventory edits — for detailed dispute
  resolution.

Never updated or deleted. Corrections are new entries, not edits to old
ones — this applies to every table in the system now, not just the log:
requests, extensions, and handovers are all permanent, append-and-transition
records rather than delete-on-completion records.

## 11. Device Status Lifecycle (Conceptual)

```
Available ──assign──> Assigned ──return (on-site)──> [IT picks next status]
                          │
                          ├──WFH ship out──> Shipping Pending ──> Assigned
                          ├──WFH return────> Return Shipping Pending ──> [IT picks next status]
                          ├──damage, repairable─> Under Repair ──> Assigned (same owner)
                          ├──damage, swap────> (this device) Under Repair/Retired, (new device) Assigned
                          └──lost, confirmed──> Lost ──> [IT manually picks next status, no automatic transition]

[IT picks next status] ──> Available | Under Repair | Retired
```

`Maintenance` and `Returned to Client` (client devices only) are manual,
IT-set statuses with no lifecycle transitions of their own.

Handover never appears in this diagram — it runs entirely underneath
"Assigned" without changing device status at any point.

## 12. Intentional Simplifications — Why

| Simplification                                                                              | Reasoning                                                                                         |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Manager approval is per-category, not per-request or globally                               | Balances flexibility against configuration complexity                                             |
| Handover is peer-to-peer, IT never involved in the decision (though now a tracked workflow) | Keeps a low-stakes exchange lightweight; IT approval would add overhead without real benefit      |
| Support types limited to Update / Damage / Lost                                             | These three map to every real device outcome                                                      |
| Client devices skip the request lifecycle                                                   | A direct IT action is cleaner than special-case flags, still fully audited                        |
| Requests, extensions, and handovers are never deleted                                       | Preserves complete history for audit and analytics — no data loss on completion                   |
| Email-only notifications                                                                    | Avoids building in-app notification infrastructure for a hackathon timeline                       |
| No delivery confirmation from the employee                                                  | Explicit assumption: employee receives the device once courier/IT confirms it moved               |
| Return only initiated by IT (on-site) or the defined WFH return flow                        | Removes back-and-forth, keeps one predictable completion gate                                     |
| Handover duration is informational, not enforced                                            | Auto-expiry needs scheduled jobs — out of scope, listed as a future improvement                   |
| No offline QR support                                                                       | High cost, low value for a hackathon demo                                                         |
| `Maintenance` / `Returned to Client` / `Lost`-next-status have no automatic lifecycle       | Rare, IT-judgment-call states; automatic transitions would mask decisions that should be explicit |

## 14. Assumptions

- Every employee has exactly one manager, set via self-service profile
  editing; no chained approval hierarchy.
- A device is assignable to exactly one active request at a time — a hard
  constraint, not just a UI convention.
- "Assigned" as a device status covers the full duration from IT's confirmed
  assignment through active use, including WFH transit windows.
- Employees are trusted to accurately report support issues and handover
  durations; the system doesn't verify condition remotely except via
  explicit IT assessment on a support ticket.
- Requested date ranges are intent, not a hard reservation — IT's confirmed
  range is authoritative and may differ.
- A device can have at most one _active_ (`accepted`) handover at a time,
  though multiple _pending_ handover requests may coexist.
