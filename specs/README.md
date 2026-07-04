# Module Specs

One self-contained spec per module from `_docs/IMPLEMENTATION_PLAN.md`, split out so each can be run as its own Claude Code session.

## How to use

1. Do modules **in dependency order** — see the table below.
2. For each module, start a fresh session in this repo and give it the prompt:
   > Read `specs/M<N>_<name>.md` and `CLAUDE.md`, then implement the module.
3. When the session finishes, verify its **Acceptance Criteria**, then mark the module `Done` in:
   - `specs/M<N>_<name>.md` (top `Status:` line)
   - `_docs/IMPLEMENTATION_PLAN.md` (Module Index table)
4. Every module spec assumes you've also read `00_CONTEXT.md` (shared conventions, enums, cross-cutting rules) — it is not repeated in full in each file.

## Module order & dependencies

| # | Module | Depends On | Complexity |
|---|--------|-----------|-----------|
| M1 | Domain Models & Migration | — | L |
| M2 | Auth & RBAC | M1 | M |
| M3 | Seed Data | M1, M2 | L |
| M4 | Device Audit Log | M1 | M |
| M5 | Inventory, Device Detail & Dropdowns | M1, M2, M4 | L |
| M6 | User Management | M1, M2 | M |
| M7 | Request Management & IT Approval Queue | M1, M2, M4 | M |
| M8 | Device Assignment & Client Direct Assign | M4, M5, M7 | L |
| M9 | WFH Shipping & Returns | M4, M8 | M |
| M10 | Support Requests | M4, M5, M8 | L |
| M11 | Extension Requests | M4, M8 | M |
| M12 | Handovers (read-only audit) | M1, M4 | S |
| M13 | Admin Dashboard | M5, M7, M9, M10, M11 | M |

**Parallelism:** M1→M2 sequential. After M2: M3, M4, M6 can run in parallel. M5 needs M4. M7 needs M4. M8 needs M5+M7. M9/M10/M11 need M8. M12 needs only M1+M4. M13 is last.

Source of truth for the full plan (findings, assumptions, rationale) remains `_docs/IMPLEMENTATION_PLAN.md` — these spec files are an extraction for convenience, not a replacement.
