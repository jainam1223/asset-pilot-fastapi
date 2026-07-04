I'm starting a new backend project that will eventually power **three modules**: an **IT Asset Management System**, a **Ticket Management System**, and — in a later phase — an **AI Chatbot module**. This first commit is ONLY the foundational project setup — no business/domain logic yet. Set up a clean, production-ready, scalable skeleton that I'll build features into afterward.

**Core non-negotiable principle: pluggability.** Every piece — database, cache, auth, config — must be swappable with minimal, localized changes (ideally one file), not a cascade of edits across layers. See the dedicated "Pluggability" section below for exactly what this means in practice; treat it as a constraint on every other section, not a separate nice-to-have.

### Tech Stack
- **Framework:** FastAPI (async, Python 3.12)
- **Database:** PostgreSQL (via SQLAlchemy 2.0 async ORM + Alembic for migrations)
- **Cache/Broker:** Redis (async client, e.g. `redis-py` asyncio interface)
- **Containerization:** Docker + Docker Compose
- **Dependency management:** `uv` with `pyproject.toml` (use `uv` for dependency resolution, virtualenv management, and lockfile — reflect this in the Dockerfile build steps too)
- **Logging:** `structlog`
- **Auth:** JWT only (access + refresh token pattern) — no OAuth2 third-party/social login, no session-based auth

### Architecture — strict 3-layer separation
Enforce this layering with NO shortcuts (e.g., API layer must never touch the DB session or ORM models directly):

```
API Layer (routers/controllers)
   -> receives HTTP request, validates input via Pydantic schemas, calls Service layer
   -> returns HTTP response

Service Layer (business logic)
   -> orchestrates business rules, calls one or more Repositories
   -> knows nothing about HTTP (no Request/Response objects, no status codes)

Repository Layer (data access)
   -> only layer that talks to the DB (via SQLAlchemy) or Redis
   -> exposes clean methods like get_by_id(), create(), list(), update(), delete()
```

### Required Folder Structure
Propose a structure along these lines (adjust naming as best-practice dictates, but keep the layering explicit and modules separated by domain so `assets`, `tickets`, and later `ai_chatbot` can be added without restructuring):

```
app/
  api/
    v1/
      routers/
      dependencies.py
  core/
    config.py          # Pydantic Settings, reads from env
    security.py         # JWT auth scaffold — token creation/verification, access+refresh, no login endpoint yet
    logging.py
    exceptions.py        # custom exception classes + global handlers
  utils/
    response.py          # shared success/error response envelope builders (success_response(), error_response())
    pagination.py         # shared pagination helper/schema used across list endpoints
    request_context.py    # request_id generation/propagation, structlog context binding helper
  db/
    base.py
    session.py           # async engine/session factory
    redis.py             # redis connection pool
  models/                # SQLAlchemy models
  schemas/                # Pydantic request/response DTOs
  services/
  repositories/
  main.py
alembic/
tests/
  unit/
  integration/
scripts/
docker/
```

### Environment Configuration
- Exactly two environments (`development`, `production`) and exactly one env file: `.env`, used for local development only, gitignored, no checked-in template. Production has no env file at all — real environment variables (including Azure Key Vault references) are injected directly by the platform.
- Centralize config via a Pydantic `BaseSettings` class (`core/config.py`) with typed fields, validation, and an `ENVIRONMENT` switch.
- `.env` must be gitignored.

### Target Deployment Environment: Azure
This setup will eventually deploy to **Azure**, so keep these in mind now (even though actual CI/CD and IaC are out of scope for this commit):

- **Container registry:** Images will be pushed to **Azure Container Registry (ACR)** — keep the `Dockerfile` generic/standard (no assumptions baked in about a specific registry), just ensure it builds cleanly and tags sensibly (`<name>:<version>`/`<name>:latest`).
- **Compute target:** Assume **Azure Container Apps** or **App Service (Web App for Containers)** as the likely runtime (mention in the README which one you're leaning toward, or note both as viable, since either just needs a container image + env vars — don't hardcode assumptions specific to AKS unless that's confirmed later).
- **Managed database/cache:** In production, Postgres and Redis will likely be **Azure Database for PostgreSQL (Flexible Server)** and **Azure Cache for Redis**, not the Dockerized ones used locally. This reinforces the pluggability requirement above — moving from local Docker Postgres/Redis to these managed services must be a pure env var change (`DATABASE_URL`, `REDIS_URL`, plus SSL mode settings — Azure Postgres typically requires `sslmode=require`), with zero code changes. Make sure the SQLAlchemy/Redis connection setup already supports SSL params via config, not just local unencrypted connections.
- **Secrets:** Don't assume `.env` files exist in production — production config should be resolvable purely from environment variables, which Azure injects via App Service/Container Apps settings, including **Azure Key Vault** references (`@Microsoft.KeyVault(...)`) that Azure resolves into plain env vars before the container starts. Pydantic `Settings` reading from `os.environ` already satisfies this; just don't introduce any local-file-only assumptions into `core/config.py`.
- **Logging:** structlog's JSON output in production is intentional here — Azure Monitor/Log Analytics ingests JSON logs from stdout/stderr well, so make sure production logging writes structured JSON to stdout (not to a file), since Azure captures container stdout/stderr directly.
- **Health checks:** the `/health/live` and `/health/ready` endpoints defined earlier map directly to Azure Container Apps/App Service health probe configuration — no changes needed there, just keep them as-is.
- Do not build actual Bicep/Terraform/GitHub Actions/Azure DevOps pipeline files in this commit unless you want to fold that into this same request — flag it separately if so, since it's a reasonably distinct chunk of work from the app scaffolding itself.


- Use the **latest stable versions** of every package as of setup time (FastAPI, SQLAlchemy, Pydantic v2, Alembic, structlog, asyncpg, redis-py, etc.) — do not default to old/cached training-data versions. Verify compatibility between them before finalizing (e.g. SQLAlchemy 2.x async patterns, Pydantic v2 syntax throughout, no v1-style code mixed in).
- Pin exact versions in `pyproject.toml` (via `uv add`) so the `uv.lock` file guarantees reproducible installs — no loose `>=` ranges for core dependencies.
- **Also generate a `requirements.txt`** (exported from the `uv` lockfile, e.g. `uv export --format requirements-txt > requirements.txt`) for compatibility with tools/environments that expect it (CI runners, certain cloud deploy targets, IDE tooling) — keep it in sync with `pyproject.toml`/`uv.lock` as the source of truth, and note in the README that `requirements.txt` is a generated artifact, not hand-edited.
- Double-check known compatibility pitfalls before locking versions — e.g. SQLAlchemy async driver (`asyncpg`) version vs SQLAlchemy version, Pydantic v2 vs `pydantic-settings` version, FastAPI version vs Starlette/Pydantic version it depends on — and call out in the README if any package was pinned slightly below "absolute latest" specifically to avoid a known incompatibility.
- Same standard applies to dev dependencies (`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pre-commit`, etc.) — latest stable, mutually compatible, listed separately as dev deps (not shipped in the production image).


- Multi-stage `Dockerfile` (builder + slim runtime image), non-root user, only production deps in final image.
- `docker-compose.yml` for local dev with services: `api`, `postgres`, `redis`, and optionally `pgadmin`/`redis-commander` for local debugging.
- Single `docker-compose.yml` only, local dev use — no separate prod compose override; actual production runs on Azure Container Apps/App Service directly from the `runtime` image, not via docker-compose.
- Healthchecks for postgres, redis, and the api service.
- Named volumes for Postgres data persistence.

### Pluggability — swap-friendly architecture
Design everything so a future change touches the **minimum number of files possible** — no change should ripple across layers. Concretely:

- **Interfaces over concrete classes for Repositories:** Define an abstract base (e.g. `BaseRepository` using Python's `abc`/`Protocol`) that Services depend on, not the concrete SQLAlchemy implementation directly. If the DB layer ever changes, only the repository implementation changes — Services and API layer stay untouched.
- **Dependency Injection everywhere, resolved in one place:** DB session, Redis client, repositories, and services should all be provided via FastAPI's `Depends`, wired centrally in `api/v1/dependencies.py` (or a small `core/dependencies.py`). Swapping an implementation means changing the provider function in ONE file, not every route that uses it.
- **Config-driven, not hardcoded:** Anything that could plausibly change per-environment or get swapped later (DB URL, Redis URL, JWT secret/algorithm/expiry, CORS origins, log level, pagination defaults, rate-limit thresholds) must live in `core/config.py` via Pydantic `Settings`, never hardcoded inline in business logic.
- **Cache abstraction, not direct Redis calls scattered around:** Put a thin `CacheRepository`/`CacheService` wrapper around Redis (get/set/delete/expire) so Services never call the Redis client directly. If Redis is ever swapped for another cache backend, only that wrapper changes.
- **Schema/DTO boundary at every layer crossing:** API layer only ever sees Pydantic schemas, never ORM models directly, and vice versa — Services translate between them. This means the DB models can evolve without breaking the API contract, and the API contract can evolve without touching persistence.
- **Domain modules stay isolated:** `assets` and `tickets` (once added) should not import each other's repositories/services directly — any needed interaction goes through a defined interface or shared service, so changing one module doesn't force changes in the other.
- **Environment/infrastructure swaps should be config-only:** Switching from local Docker Postgres to a managed cloud Postgres, or local Redis to a managed Redis (e.g. ElastiCache), should require ONLY env var changes — zero code changes. Verify this is actually true by keeping all connection logic centralized in `db/session.py` and `db/redis.py`.
- **Prove it, don't just claim it:** as a sanity check for this commit, briefly note in the README what would need to change (and confirm it's minimal — ideally 1 file) if someone wanted to: (a) swap Postgres for MySQL, (b) swap the JWT lib, (c) add a new external cache. This keeps the "pluggable" claim honest rather than aspirational.


### Standard API Response Structure
Define ONE consistent response envelope used across **every** endpoint (success and error) — no endpoint should invent its own shape. Implement this in a shared **`app/utils/response.py`** module (not repeated per-router, not scattered inline) — e.g. `success_response(data, status_code=200, message=None, meta=None)` and `error_response(status_code, code, message, details=None)` helper functions (or Pydantic response models) that every router/exception handler calls into. Related shared helpers (pagination math, request-ID generation, structlog context binding) also live under `app/utils/` for the same reason — one place to change, everywhere picks it up.

**Success response:**
```json
{
  "status_code": 200,
  "data": { },
  "message": "Request completed successfully",
  "meta": {
    "timestamp": "2026-07-04T12:00:00Z",
    "request_id": "b3f1c2..."
  },
  "success": true
}
```
- `status_code` mirrors the actual HTTP status code returned (200, 201, etc.) — included in the body as well as the real HTTP response status, so clients can branch on the body alone without inspecting HTTP-level status if they prefer.
- `data` holds the actual payload — an object for single-resource responses, an array for list responses.
- For paginated list endpoints, extend `meta` with `pagination`: `{ "page": 1, "page_size": 20, "total_items": 134, "total_pages": 7 }`.
- `message` is optional/human-readable, can be omitted or null for pure data fetches.

**Error response:**
```json
{
  "status_code": 400,
  "message": "Ticket with id 123 was not found",
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Ticket with id 123 was not found",
    "details": [
      { "field": "ticket_id", "issue": "does not exist" }
    ]
  },
  "meta": {
    "timestamp": "2026-07-04T12:00:00Z",
    "request_id": "b3f1c2..."
  },
  "success": false
}
```
- `status_code` matches the real HTTP response status (400, 401, 403, 404, 409, 422, 429, 500, 503, etc.).
- Top-level `message` is a short human-readable summary (same as `error.message` in the simple case) — kept at the top level for clients that just want a quick display string without reaching into `error`.
- `error.code` is a stable, machine-readable string (SCREAMING_SNAKE_CASE) — not just the HTTP status text — so frontend/API consumers can branch on it reliably.
- `error.details` is optional; used for validation errors (map FastAPI/Pydantic `422` validation errors into this same array shape instead of the default FastAPI error format) or multi-field business rule failures. Omit or use `null`/`[]` when not applicable.
- Never leak stack traces, raw exception messages, or internal file paths in `error.message`/`details` — log the full detail server-side (via structlog) but return a safe message to the client.
- Field order in the examples above (`status_code`, then payload/message, then `error`/`meta`, `success` last) is just for readability here — implement as a Pydantic model, where key order in the model definition is fine to follow this same sequence for consistency across the codebase.

**Requirements:**
- Define a small taxonomy of error codes + matching HTTP status codes up front, e.g.:
  - `VALIDATION_ERROR` → 422
  - `UNAUTHORIZED` → 401
  - `FORBIDDEN` → 403
  - `RESOURCE_NOT_FOUND` → 404
  - `CONFLICT` → 409
  - `RATE_LIMITED` → 429
  - `INTERNAL_SERVER_ERROR` → 500
  - `SERVICE_UNAVAILABLE` → 503 (e.g. for `/health/ready` failures, DB/Redis down)
- Implement this via global FastAPI exception handlers (`@app.exception_handler(...)`) for: custom domain exceptions (defined in `core/exceptions.py`), `RequestValidationError`, `HTTPException`, and a catch-all `Exception` handler — each handler builds its JSON body by calling `error_response(...)` from `app/utils/response.py`, so every possible failure path funnels into the same envelope via the same function, not just the ones raised deliberately.
- Custom domain exceptions (e.g. `NotFoundException`, `ConflictException`, `UnauthorizedException`) should live in `core/exceptions.py` and carry `code`, `message`, `status_code`, and optional `details`, so raising them from the Service layer (never from Repository or API layer directly) automatically produces the correct envelope, with `status_code` set consistently both as the real HTTP response status AND the `status_code` field in the JSON body — never let these two drift apart.
- Include `request_id` (generated per-request via middleware, also used in structlog context) in every response so a client-reported error can be traced back to server logs.
- Wrap this once so it doesn't leak `None`/undefined behavior for endpoints that return `204 No Content` — document how those are handled (typically no body, so the envelope doesn't apply).
- Add a couple of sample tests asserting the envelope shape for a success case, a 404 case, and a validation-error case.


- Async SQLAlchemy engine with proper connection pooling settings.
- Alembic configured and working with async engine (initial empty migration).
- Global exception handlers returning consistent JSON error shape.
- JWT auth scaffold (no real login/user domain logic yet, since that belongs to a future feature commit):
  - `core/security.py` with: password hashing helper (e.g. via `passlib`/`bcrypt`), access token creation, refresh token creation, and token decode/verify functions.
  - Config-driven secret key, algorithm (e.g. `HS256`), and expiry durations (access vs refresh) via `core/config.py` — never hardcoded.
  - A reusable FastAPI dependency (e.g. `get_current_user`) that extracts and verifies the JWT from the `Authorization: Bearer <token>` header, ready to be wired onto protected routers later.
  - Return `UNAUTHORIZED`/`FORBIDDEN` errors (per the standard error envelope above) for missing/invalid/expired tokens — not FastAPI's default error format.
  - Do not build the actual `/auth/login` or `/auth/register` endpoints or a `User` model/table in this commit — just the reusable JWT plumbing so real auth endpoints can be added in a follow-up commit without restructuring.
- Structured logging using **structlog** — JSON-rendered logs in production/staging, human-readable console rendering in development, with request IDs bound to each request's log context (e.g. via middleware using `structlog.contextvars`).
- CORS, GZip, and trusted-host middleware configured via settings.
- Health check endpoints, fully implemented (not stubs):
  - `GET /health/live` — liveness probe. Just confirms the process is up and responding; no external dependency checks. Always returns `200` with `{"status": "ok"}` unless the app itself is broken.
  - `GET /health/ready` — readiness probe. Actively checks:
    - Postgres: run a lightweight query (e.g. `SELECT 1`) via the repository/db layer, with a short timeout.
    - Redis: `PING` via the redis client, with a short timeout.
  - Response shape (both success and failure) should be consistent, e.g.:
    ```json
    {
      "status": "ok" | "degraded",
      "timestamp": "2026-07-04T12:00:00Z",
      "checks": {
        "database": { "status": "ok" | "error", "latency_ms": 4.2, "error": null },
        "redis":    { "status": "ok" | "error", "latency_ms": 1.1, "error": null }
      }
    }
    ```
  - Return `200` when all checks pass, `503` when any dependency check fails (so it plays correctly with Docker/K8s/load-balancer health checks).
  - Do not leak internal exception details/stack traces in the error field — just a short safe message.
  - Wire these into `docker-compose.yml` healthcheck directives (`curl`/`wget` against `/health/ready` for the `api` service) and mention them in the README.
  - Keep both endpoints outside `/api/v1` (e.g. top-level `/health/...`) since they're infra-facing, not part of the versioned public API.
- API versioning via `/api/v1` prefix.
- Dependency injection for DB session and Redis client (FastAPI `Depends`).
- Pagination, filtering, and sorting conventions defined at a base/shared level (so Assets and Tickets modules can reuse them).
- Basic rate-limiting or caching pattern demonstrated using Redis (just the plumbing, not full logic).
- `pytest` + `pytest-asyncio` configured with a test DB/Redis setup (docker-compose test override or testcontainers) and one sample test per layer.
- Code quality tooling: `ruff` (lint+format) or `black`+`isort`, `mypy`, and `pre-commit` config.
- `Makefile` with a full set of shortcuts so no command needs to be typed out manually. At minimum include:
  - **Setup:** `make install` (sync deps via `uv`), `make env` (verify `.env` exists; no template file is checked in)
  - **Docker lifecycle:** `make up` (start all services, detached), `make down` (stop + remove containers), `make down-v` (also remove volumes — clean slate), `make restart`, `make build` (rebuild images), `make rebuild` (build + up, no cache)
  - **Logs:** `make logs` (tail all services), `make logs-api`, `make logs-db`, `make logs-redis` (tail individual service logs)
  - **Shell access:** `make shell-api` (exec into the running api container's shell), `make shell-db` (psql into postgres container), `make shell-redis` (redis-cli into redis container)
  - **Database/migrations:** `make migrate` (`alembic upgrade head`), `make makemigrations message="..."` (`alembic revision --autogenerate`), `make migrate-down` (rollback one revision), `make db-reset` (drop + recreate + re-migrate, for local dev only)
  - **Testing:** `make test` (run full pytest suite in a test container/db), `make test-unit`, `make test-integration`, `make coverage` (pytest with coverage report)
  - **Code quality:** `make lint` (ruff/mypy check), `make format` (auto-format), `make pre-commit` (run all pre-commit hooks)
  - **Health/status:** `make ps` (docker compose ps — see what's running/healthy), `make health` (curl `/health/ready` and pretty-print the JSON)
  - Use `.PHONY` for all targets, add a `make help` target that self-documents every command (parse target + inline `##` comments), and make it the default target so running bare `make` prints usage instead of doing nothing.
  - Document all `make` commands in the README with a short table (command → what it does).
- `README.md` covering setup, running locally, running migrations, and environment variables.
- `.gitignore` and `.dockerignore` properly configured.

### Forward Compatibility: Future AI Chatbot Module
Do NOT build the chatbot module now — but make sure nothing in this initial setup blocks it later:

- **Domain isolation still applies:** when added, `ai_chatbot` should be its own module under `app/` (routers/services/repositories), following the same 3-layer pattern and not reaching into `assets`/`tickets` internals directly — same rule as the isolation principle in the Pluggability section.
- **Don't box out streaming:** the chatbot will likely need streaming responses (SSE) or WebSockets for real-time chat. Nothing in this commit should assume every endpoint is a simple request/response JSON call — keep `main.py`/app factory structured so adding a WebSocket route or a `StreamingResponse` endpoint later is a normal addition, not a rework (FastAPI supports both natively, so this is mostly "don't do anything unusual that would conflict," not extra work now).
- **Response envelope caveat:** note in the README that the standard success/error envelope defined above applies to normal request/response JSON endpoints; streaming/WebSocket endpoints (for the future chatbot) will need their own event-shaped convention, decided when that module is actually built — flag this as a known, deliberate exception rather than an oversight.
- **LLM provider config placeholder:** no need to add actual AI/LLM SDKs now, but keep `core/config.py` structured so provider-specific settings (API keys, model names, timeouts) can be added as a new settings group later without restructuring the config class.
- **Redis reuse:** the existing Redis setup (via the cache abstraction from the Pluggability section) will likely double as chat session/context storage later — nothing extra needed now, just confirms the cache wrapper approach was the right call.


1. Full folder/file scaffold as above.
2. Working `docker-compose up` that boots API + Postgres + Redis with healthchecks passing.
3. One trivial end-to-end vertical slice proving the 3 layers work together — e.g. a `/health` or a placeholder `/ping` route that goes API → Service → Repository → Redis (increment a counter) to prove wiring, **not** a real domain feature. This slice must return responses using the standard success/error envelope defined above.
4. Alembic initialized and able to run `alembic upgrade head` against the Dockerized Postgres.
5. Short `README.md` explaining how to run it.

Do not implement the Asset Management, Ticket Management, or AI Chatbot domain logic yet — this commit is infrastructure/scaffolding only. Ask me clarifying questions if anything about deployment target (e.g., cloud provider, CI/CD) would change the setup, otherwise proceed with sensible defaults and explain key decisions briefly as you go.
