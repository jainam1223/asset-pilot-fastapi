---
description: Write tests for one module from specs/ (given its name or number), then run and verify them — using two separate sequential agents.
---

Argument given: `$ARGUMENTS`

Resolve it to exactly one file in `specs/`, same rule as `/run-spec`:
- If `$ARGUMENTS` already names an existing file in `specs/`, use it directly.
- Otherwise treat it as a module id/number (e.g. `M1`, `M01`, `1`) and find the matching `specs/M<NN>_*.md` file (zero-padded, e.g. `M1` → `M01_*.md`).
- If nothing matches, or more than one file matches, list the available spec files in `specs/` and ask which one was meant — do not guess.

Once resolved, run the following two agents **sequentially** (do not parallelize — the second depends on the first's output). Use the `general-purpose` agent type for both; each is a fresh agent with no shared memory, so brief each one fully per the notes below.

## Step 1 — Write-tests agent

Launch one `general-purpose` agent with a self-contained prompt that tells it to:
- Read `specs/00_CONTEXT.md`, `CLAUDE.md`, and the resolved module spec file (`specs/M<NN>_*.md`) in full.
- Read `tests/conftest.py` and at least one existing test file (if any exist) to match this repo's test conventions (pytest + pytest-asyncio, `asyncio_mode=auto`, async httpx ASGI client fixture, `tests/unit` vs `tests/integration` split, markers used by `make test-unit`/`make test-integration`).
- Inspect the actual implemented code for this module (models/services/repositories/routers it touches) — do not invent behavior; test what's really there.
- Write tests that cover every item in the module spec's **Acceptance criteria** section, plus the tricky service-layer logic called out in its **Scope checklist** (status guards, invariant checks, overlap/cascade logic, etc. — whatever applies to this module).
- Place unit tests in `tests/unit/` and integration (endpoint→DB) tests in `tests/integration/`, following existing naming patterns.
- **Only write test code. Do not run the test suite and do not modify non-test application code.**
- Return a concise report: which test files were created/modified, and a one-line description of each test case added, so the next agent knows exactly what to run and verify.

Capture this agent's report — you'll pass it into Step 2's prompt verbatim.

## Step 2 — Run-and-verify agent

Launch a second `general-purpose` agent (fresh, no shared context) with a self-contained prompt that:
- Includes the resolved module spec file path and its **Acceptance criteria** section text, plus the full report from Step 1 (list of test files and test cases).
- Instructs it to run the new tests (targeted `pytest`/`make test-unit`/`make test-integration` as appropriate), then the full `make test` and `make lint` to check for regressions.
- For each acceptance criterion in the module spec, explicitly confirm whether a passing test exercises it — flag any criterion with no corresponding test.
- If a test fails because the **test itself** is wrong (bad fixture, wrong assertion, mismatched setup), it may fix the test and re-run.
- If a test fails because it exposes a **real defect in application code**, it must NOT silently patch application code — instead report the failure, the suspected root cause, and the file/line, and leave it for the user to decide.
- Return a final pass/fail summary: total tests run, failures (with cause classification: test-bug fixed / product-bug found), and a checklist mapping each acceptance criterion to a test result.

## After both agents finish

Report to the user, combining both agents' outputs:
- Test files written (from Step 1).
- Final test run results and lint status (from Step 2).
- Acceptance-criteria coverage checklist.
- Any product-code defects surfaced, called out clearly and separately from test results, without having modified product code yourself.
