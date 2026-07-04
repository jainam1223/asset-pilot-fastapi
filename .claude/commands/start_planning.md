# Claude Code Prompt: Requirements Analysis → Module Plan → CLAUDE.md

Use this in two passes inside your project root (where `_docs/` lives). Run Phase 1 first, review/edit the output, THEN run Phase 2 in a fresh session so CLAUDE.md reflects the approved plan.

---

## PHASE 1 — Analysis + Module-wise Execution Plan

```
You are analyzing a project's requirements to produce an execution plan I will run
module-by-module across SEPARATE Claude Code sessions. Because each module will be
executed independently later (with no memory of this conversation), the plan itself
must carry all context — treat it as the only thing a future session will have.

STEP 1 — Read everything first, don't start planning yet
Read every file inside ./_docs/ including (but not limited to):
- Database schema file(s)
- DB seed file(s)
- API specification / API info docs
- Design docs / wireframes / UX specs
- Any README, notes, or misc files in that folder

Also inspect the CURRENT project structure:
- Run a directory listing (respecting .gitignore) to see what already exists
- Identify the tech stack already in use (check package.json, requirements.txt,
  pyproject.toml, composer.json, go.mod, etc. — whatever is present)
- Identify existing folder conventions (e.g. feature-based vs layer-based,
  existing models/routes/services already built)
- Note any partial/in-progress modules already implemented so the plan doesn't
  duplicate or conflict with existing code

Do not assume a stack or architecture — infer it strictly from what's on disk.
If _docs/ conflicts with what's already implemented in the codebase, flag the
conflict explicitly rather than silently picking one.

STEP 2 — Cross-reference for gaps and conflicts
Before writing the plan, produce a short "Findings" section covering:
- Entities in the DB schema that have NO corresponding API endpoint
- API endpoints that reference tables/fields NOT in the schema
- Seed data that doesn't match the schema (missing tables, extra columns, type mismatches)
- Design/UX flows that imply functionality not covered by the API docs
- Any ambiguous or missing requirement you had to assume — list the assumption explicitly

STEP 3 — Break the project into MODULES
Group the work into logical, independently-shippable modules (e.g. Auth, User
Management, [Domain Entity A], [Domain Entity B], Notifications, Admin Panel,
Reporting, etc.) based on the actual schema/API domains found — not a generic
template. For each module, determine:
- What it depends on (which other modules must exist first)
- What can be built in parallel vs. must be sequential

Order modules by dependency (foundation/auth/DB setup first, dependent
features later).

STEP 4 — Write the plan to a file: ./_docs/IMPLEMENTATION_PLAN.md

The file must have:

1. **Project Snapshot** — stack detected, existing structure summary, key
   conventions to follow (naming, folder layout, error handling patterns, etc.)

2. **Findings & Assumptions** — from Step 2, so future sessions know the
   known gaps/decisions up front instead of re-discovering them.

3. **Module Index** — ordered table: Module # | Name | Depends On | Est. Complexity (S/M/L)

4. **One detailed section PER MODULE**, each fully self-contained, containing:
   - **Goal** — one paragraph, what this module delivers and why
   - **Context recap** — the specific tables/fields, API endpoints, and design
     screens relevant to ONLY this module (copy the relevant snippets/specs in,
     don't just reference _docs — a future session shouldn't need to re-read
     the whole _docs folder to start)
   - **Preconditions** — which prior modules/files must already exist, and how
     to verify that (e.g. "check that `models/user.py` exists and exports `User`")
   - **Scope checklist** — concrete, checkable tasks (DB models/migrations,
     endpoints, services, validation, tests, seed data wiring, etc.)
   - **Out of scope** — explicitly what NOT to build in this module (prevents
     scope creep/duplication across sessions)
   - **Acceptance criteria** — how to know the module is done (specific,
     testable: "POST /api/x returns 201 with fields Y, Z"; "seed script inserts
     N rows without FK errors"; etc.)
   - **Suggested session prompt** — a ready-to-paste prompt for kicking off
     THAT module in a new session, referencing this plan file by path and
     module number so the future session can self-orient in one read.

5. **Cross-cutting concerns** section — auth, error handling, logging,
   validation, testing strategy — anything that applies across all modules,
   stated once so it isn't repeated/contradicted per-module.

Constraints:
- Do not write implementation code in this phase — plan only.
- Keep each module scoped to roughly what's completable in one focused session
  (if a domain is huge, split it into multiple modules rather than one giant one).
- Use the actual names/fields from the schema and API docs, not placeholders.
- Flag any module that seems too large or too vague to execute confidently.

When done, give me a brief summary of the module list and any Findings that
need my decision before execution begins.
```

---

## PHASE 2 — Generate CLAUDE.md (run after you've reviewed/approved the plan)

```
Using ./_docs/IMPLEMENTATION_PLAN.md (already approved) and the actual current
project structure, generate a CLAUDE.md file at the project root to guide all
future Claude Code sessions working on this codebase module-by-module.

Read first:
- ./_docs/IMPLEMENTATION_PLAN.md
- Current repo structure, package/dependency files, existing config
  (linting, formatting, test runner config, env files structure — not values)
- Any existing CLAUDE.md, README.md, or CONTRIBUTING.md if present (merge
  useful content rather than discarding it)

CLAUDE.md must include:

1. **Project overview** — what this project is, in 2-4 sentences, derived from
   _docs, not generic boilerplate.

2. **Tech stack** — exact languages/frameworks/versions found in the project
   (from lockfiles/config), plus DB engine and key libraries actually in use.

3. **Architecture & folder conventions** — the real folder structure (paste an
   actual tree, trimmed to relevant depth), and the convention for where new
   models/routes/services/tests/migrations go, based on what already exists.

4. **How to run things** — dev server start command, test command, migration
   command, seed command — pulled from actual scripts (package.json scripts,
   Makefile, manage.py commands, etc.), not assumed.

5. **Coding conventions** — naming patterns, error handling style, response
   shape conventions for APIs, validation approach — inferred from existing
   code samples in the repo (cite 1-2 real examples from the codebase).

6. **Module execution workflow** — explicitly instruct future sessions:
   - Always read ./_docs/IMPLEMENTATION_PLAN.md and identify current module status
   - Work on ONE module per session unless told otherwise
   - Before starting, verify preconditions listed for that module
   - After finishing a module, update its status in IMPLEMENTATION_PLAN.md
     (add a "Status" column/marker: Not Started / In Progress / Done) so
     the plan file itself tracks progress across sessions
   - Do not modify code belonging to a different module without flagging it

7. **Known gaps/assumptions** — pull directly from the plan's Findings section
   so every session sees them.

8. **Things NOT to do** — anything project-specific to avoid (e.g. "don't
   regenerate migrations manually," "don't touch /legacy," "always use the
   repository pattern for DB access," etc.) inferred from the codebase or
   stated by me.

Keep it dense and skimmable — this file gets read at the start of every
session, so prioritize information density over prose. Use headers and
short bullets, not long paragraphs.

Save it as ./CLAUDE.md. If one already exists, show me a diff-style summary
of what you're adding/changing before overwriting.
```

---

### How to use this across sessions

1. Run **Phase 1** once. Review `IMPLEMENTATION_PLAN.md`, resolve any flagged Findings/assumptions yourself (edit the file directly if needed).
2. Run **Phase 2** once (fresh session is fine — it just reads the plan + repo).
3. For each module, start a **new session** and paste that module's "Suggested session prompt" from the plan. Claude Code will read `CLAUDE.md` + the relevant module section and pick up from there.
4. After each module, remind Claude Code to mark it `Done` in the plan file before you close the session — that's what keeps sessions in sync without shared memory.