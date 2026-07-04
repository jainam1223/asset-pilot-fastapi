---
description: Run a 3-way code audit (code review, security review, lint) for one module from specs/, using parallel agents.
---

Argument given: `$ARGUMENTS`

Resolve it to exactly one file in `specs/`, same rule as `/run-spec` and `/test-spec`:
- If `$ARGUMENTS` already names an existing file in `specs/`, use it directly.
- Otherwise treat it as a module id/number (e.g. `M1`, `M01`, `1`) and find the matching `specs/M<NN>_*.md` file (zero-padded, e.g. `M1` → `M01_*.md`).
- If nothing matches, or more than one file matches, list the available spec files in `specs/` and ask which one was meant — do not guess.

## Determine the audit scope

Before launching any agent, figure out which files this audit covers:
- If there are uncommitted changes (`git status` / `git diff`), scope the audit to those changed files.
- Otherwise, derive the file set from the resolved module spec's **Scope checklist** (its models/schemas/repositories/services/routers) and locate the actual implemented files under `app/` for that module.
- Pass this concrete file list (or diff) to every agent below — none of them should have to re-derive it.

## Launch all three agents in parallel

Launch these as `general-purpose` agents in a **single message with three Agent tool calls** (they are independent — no need to run sequentially). Each is a fresh agent with no shared memory, so brief each one fully.

### Agent 1 — Code review

Brief it to:
- Read the resolved module spec file and `specs/00_CONTEXT.md` / `CLAUDE.md` for the conventions this code must follow (layering, response envelope, exceptions, DI, device_log discipline, naming).
- Review the scoped file list for: correctness bugs (logic errors, wrong status transitions, missed edge cases relative to the spec's Acceptance criteria), violations of the layering rules (router touching ORM, service committing, etc.), and reuse/simplification/efficiency issues (duplicated logic, unnecessary abstraction, N+1 queries).
- Report findings as a ranked list (most severe first): `file:line — one-line defect summary — concrete failure scenario`. Do not modify any code — this is a review only.

### Agent 2 — Security review

Brief it to:
- Read the scoped file list plus `app/core/security.py` and `app/core/exceptions.py` for the auth/error primitives already in place.
- Check specifically for: SQL/NoSQL injection (raw query construction instead of ORM/parameterized queries), missing or bypassable `require_it_admin`/auth checks on new endpoints, broken object-level authorization (e.g. an IT-admin-only ID lookup that doesn't scope by tenant/owner where the spec requires it), secrets or credentials hard-coded or logged, unsafe deserialization, mass-assignment (accepting more fields from the request body than the schema should allow), and any input that reaches a shell/`eval`/dynamic import.
- Report findings as a ranked list (most severe first): `file:line — vulnerability class — concrete exploit scenario`. Do not modify any code — this is a review only.

### Agent 3 — Lint

Brief it to:
- Run `make lint` (ruff check + `mypy app tests` strict) scoped to the audited files where possible.
- It MAY run `make format` (ruff format + `--fix`) to auto-resolve pure formatting/import-order issues, then re-run `make lint` to confirm — this is mechanical and safe.
- It must NOT alter logic to satisfy mypy/ruff (e.g. adding `# type: ignore` to silence a real type error, or loosening a signature) — instead report the remaining errors verbatim with file:line.
- Report: what was auto-fixed, and the final list of unresolved lint/type errors (if any).

## After all three finish

Combine the three reports into one summary for the user, grouped as **Code Review / Security Review / Lint**, most-severe findings first within each group. Call out any finding that shows up in more than one report. End with a short overall verdict (e.g. "clean", "N issues — none blocking", "M blocking issues, listed above") — do not apply any of the reviewers' suggested fixes yourself unless the user asks you to.
