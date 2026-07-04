---
description: Implement one module from specs/ given just its name or number (e.g. "M01" or "M05_inventory_device_detail_dropdowns.md")
---

Argument given: `$ARGUMENTS`

Resolve it to exactly one file in `specs/`:
- If `$ARGUMENTS` already names an existing file in `specs/`, use it directly.
- Otherwise treat it as a module id/number (e.g. `M1`, `M01`, `1`) and find the matching `specs/M<NN>_*.md` file (zero-padded, e.g. `M1` → `M01_*.md`).
- If nothing matches, or more than one file matches, list the available spec files in `specs/` and ask which one was meant — do not guess.

Once resolved:

1. Read `specs/00_CONTEXT.md`, `CLAUDE.md`, and the resolved module spec file in full.
2. Verify the module's **Preconditions** section actually hold in the current codebase (e.g. models/tables/services it depends on exist) before writing any code. If a precondition is unmet, stop and report which one instead of proceeding.
3. Implement strictly per that module's **Scope checklist**, respecting its **Out of scope** section — do not touch other modules' code.
4. Follow all conventions in `specs/00_CONTEXT.md` / `CLAUDE.md` (layering, response envelope, exceptions, DI, device_log discipline, etc.).
5. Run `make lint` and `make test` (and any module-specific checks) and verify every item in the module's **Acceptance criteria**.
6. When everything passes, update the module's `Status:` line in its `specs/M<NN>_*.md` file to `Done`, and update the same module's row in `_docs/IMPLEMENTATION_PLAN.md`'s Module Index to `Done`.
7. Report a short summary: what was built, test/lint results, and confirmation of each acceptance criterion.
