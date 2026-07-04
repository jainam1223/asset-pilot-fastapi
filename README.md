# asset-pilot-fastapi

Foundational backend scaffold for **AssetPilot** — a platform that will
eventually host three modules:

- **IT Asset Management System**
- **Ticket Management System**
- **AI Chatbot** (future phase)

This repository currently ships **infrastructure/scaffolding only** — no
domain logic. It exists so the three modules above can be built on top of
a consistent, pluggable, production-ready foundation without needing to
restructure anything later.

## Tech stack

| Concern | Choice |
|---|---|
| Framework | FastAPI (async), Python 3.12 |
| Database | PostgreSQL via SQLAlchemy 2.0 async ORM + Alembic |
| Cache | Redis (`redis-py` asyncio client) |
| Auth | JWT (access + refresh), no OAuth2/social login, no sessions |
| Logging | `structlog` (JSON in staging/prod, console in dev) |
| Dependency management | `uv` + `pyproject.toml` / `uv.lock` |
| Containerization | Docker (multi-stage) + Docker Compose |

## Architecture: strict 3-layer separation

```
API layer (app/api)         -> HTTP in/out, Pydantic schemas only, no DB session, no ORM models
Service layer (app/services) -> business logic, orchestrates repositories, no HTTP awareness
Repository layer (app/repositories) -> the ONLY layer touching SQLAlchemy/Redis directly
```

Every layer crossing goes through a schema/DTO boundary — the API layer
never sees an ORM model, and the DB layer never sees a Pydantic schema.

## Project layout

```
app/
  api/
    health.py            # /health/live, /health/ready — outside /api/v1 on purpose
    v1/
      dependencies.py     # ALL dependency injection wiring lives here
      routers/            # versioned routers, e.g. ping.py
  core/
    config.py             # Pydantic Settings — the only place reading env vars
    security.py            # JWT + password hashing plumbing (no login endpoint yet)
    logging.py             # structlog configuration
    exceptions.py           # domain exception taxonomy
  utils/
    response.py             # success_response() / error_response() — the ONE envelope
    pagination.py            # shared pagination params/Page/meta
    request_context.py       # request-id generation + structlog context binding
  db/
    base.py                  # declarative Base + shared mixins
    session.py                # async engine/session factory (the ONE place that knows Postgres)
    redis.py                   # redis connection pool (the ONE place that knows Redis)
  models/                      # SQLAlchemy models (empty until a domain module lands)
  schemas/                      # Pydantic DTOs
  services/                      # business logic (health, ping — trivial slice only)
  repositories/                   # data access (base repo interface, cache repo, health repo)
  main.py                          # app factory, middleware, global exception handlers
alembic/                            # migrations (async engine configured)
tests/
  unit/                              # no external deps required
  integration/                        # requires the docker-compose stack up
scripts/
docker/
```

## Quickstart

Prerequisites: Docker, Docker Compose, and `uv` (only needed for local
tooling outside containers — linting, `uv sync`, etc.).

```bash
make env      # copy .env.example -> .env.development (only if missing)
make up       # build + start api + redis (detached) — talks to your own local/system Postgres, no postgres container
make migrate  # alembic upgrade head (runs natively via uv on the host, not the container)
make health   # curl /health/ready and pretty-print it
```

The API is now at `http://localhost:8000`. Try:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/ping   # API -> Service -> Repository -> Redis vertical slice
```

Optional local debugging tools (pgAdmin, redis-commander) are behind a
compose profile:

```bash
docker compose --profile tools up -d
# pgAdmin:          http://localhost:5050
# redis-commander:  http://localhost:8081
```

Run against the production-shaped image (gunicorn + uvicorn workers, no
bind-mounts) instead of the hot-reloading dev image:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Make commands

| Command | What it does |
|---|---|
| `make install` | Sync all deps (incl. dev) via `uv` |
| `make env` | Copy `.env.example` -> `.env.development` if missing |
| `make up` | Start all services, detached |
| `make down` | Stop and remove containers |
| `make down-v` | Stop and remove containers + volumes (clean slate) |
| `make restart` | Restart all services |
| `make build` | Build images |
| `make rebuild` | Rebuild images with no cache and start |
| `make logs` / `logs-api` / `logs-redis` | Tail logs |
| `make shell-api` | Shell into the running `api` container |
| `make shell-db` | `psql` into your local/system Postgres (native, via host `psql` — not a container) |
| `make shell-redis` | `redis-cli` into the `redis` container |
| `make create-db` | Create the target DB if missing (native, via `uv run`, not the container) |
| `make migrate` | `alembic upgrade head` (native, via `uv run`, not the container) |
| `make makemigrations message="..."` | `alembic revision --autogenerate -m "..."` (native, via `uv run`) |
| `make migrate-down` | Roll back one migration (native, via `uv run`) |
| `make db-reset` | Drop + recreate + re-migrate the local dev DB (destructive, local only, native via `uv run`) |
| `make test` | Run the full pytest suite inside the `api` container |
| `make test-unit` | Run unit tests only (no external deps) |
| `make test-integration` | Run integration tests inside the `api` container (needs redis up + local Postgres reachable from the Docker bridge — see "Local Postgres, not a container" below) |
| `make coverage` | Run pytest with a coverage report |
| `make lint` | `ruff check` + `mypy` |
| `make format` | `ruff format` + `ruff check --fix` |
| `make pre-commit` | Run all pre-commit hooks against all files |
| `make clean` | Remove local cache/build artifacts (`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, coverage files) — safe, doesn't touch containers/volumes/env files |
| `make ps` | `docker compose ps` |
| `make health` | Curl `/health/ready` and pretty-print the JSON |
| `make help` | Show this list (also the default target — bare `make` prints usage) |

## Environment configuration

Config is centralized in `app/core/config.py` via a Pydantic `Settings`
class — nothing reads `os.environ` directly outside that file. The active
env file is picked by `ENVIRONMENT` (`.env.<ENVIRONMENT>`, e.g.
`.env.development`); only ONE file is ever loaded (see "why not merge all
four env files" below). Every key is documented in `.env.example`
(committed, no secrets). `.env.development` / `.env.staging` /
`.env.production` are local-only convenience copies and are gitignored.

In containers (Docker Compose locally, Azure App Service/Container Apps
in the cloud), real environment variables are injected directly and no
`.env` file needs to exist at all — `Settings` falls back to
`os.environ` transparently either way.

**Why not merge `.env.development` + `.env.staging` + `.env.production`
together?** Early in this scaffold that's what happened (`env_file` as a
tuple of all four), and it silently broke: `.env.production`'s
`REPLACE_ME` placeholder secret overrode `.env.development`'s real local
value whenever all three files coexisted on disk, because pydantic-
settings applies later files in the tuple last. `core/config.py` now
resolves exactly one file based on `ENVIRONMENT` (or an explicit
`ENV_FILE` override).

## Local Postgres, not a container

`docker-compose.yml` does **not** run a Postgres container — `DATABASE_URL`
in `.env.development` points at your own local/system Postgres install via
`host.docker.internal` (works on Linux thanks to the `extra_hosts:
host-gateway` entry; native on Docker Desktop).

- **DB management commands** (`make create-db`, `make migrate`,
  `make makemigrations`, `make migrate-down`, `make db-reset`,
  `make shell-db`) run **natively on the host** via `uv run`/`psql`, not
  in the container — they swap `host.docker.internal` for `localhost`, so
  they work out of the box as long as `uv sync` (`make install`) has been
  run once and your local Postgres accepts connections on `localhost`.
- **The running `api` container** and **`make test-integration`** (which
  execs into that container) still need to reach Postgres over the Docker
  bridge, which requires a one-time host Postgres config change:
  ```bash
  # find your version's config dir, e.g. /etc/postgresql/14/main
  sudo sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/<ver>/main/postgresql.conf
  echo "host    all             all             172.17.0.0/16           md5" | sudo tee -a /etc/postgresql/<ver>/main/pg_hba.conf
  sudo systemctl restart postgresql@<ver>-main   # the per-version instance, NOT the `postgresql` meta-unit
  ```
  `172.17.0.0/16` is the default Docker bridge subnet (`docker0`) — adjust
  if yours differs (`ip -4 addr show docker0`).

## Standard response envelope

Every endpoint under `/api/v1` returns the same JSON shape, success or
error, built by `success_response()` / `error_response()` in
`app/utils/response.py`. Global exception handlers in `app/main.py`
funnel every failure path — custom domain exceptions, request validation
errors, `HTTPException`, and unhandled exceptions — through
`error_response()`, so nothing invents its own shape.

Success:
```json
{
  "status_code": 200,
  "data": {},
  "message": "Request completed successfully",
  "meta": { "timestamp": "...", "request_id": "..." },
  "success": true
}
```

Error:
```json
{
  "status_code": 404,
  "message": "Ticket with id 123 was not found",
  "error": { "code": "RESOURCE_NOT_FOUND", "message": "...", "details": null },
  "meta": { "timestamp": "...", "request_id": "..." },
  "success": false
}
```

Error code taxonomy (`app/core/exceptions.py`): `VALIDATION_ERROR` (422),
`UNAUTHORIZED` (401), `FORBIDDEN` (403), `RESOURCE_NOT_FOUND` (404),
`CONFLICT` (409), `RATE_LIMITED` (429), `INTERNAL_SERVER_ERROR` (500),
`SERVICE_UNAVAILABLE` (503).

**Exceptions to the envelope:**
- `/health/live` and `/health/ready` are infra-facing probes with their
  own documented shape (see below) — they intentionally do NOT use this
  envelope.
- `204 No Content` responses have no body, so the envelope doesn't apply
  by definition.
- Future chatbot streaming/WebSocket endpoints will need their own
  event-shaped convention — see "Forward compatibility" below.

## Health checks

- `GET /health/live` — liveness. No dependency checks; always `200`
  unless the process itself is broken.
- `GET /health/ready` — readiness. Runs `SELECT 1` against Postgres and
  `PING` against Redis (each with a short timeout), returns `200` if both
  pass, `503` if either fails:
  ```json
  {
    "status": "ok",
    "timestamp": "...",
    "checks": {
      "database": { "status": "ok", "latency_ms": 4.2, "error": null },
      "redis":    { "status": "ok", "latency_ms": 1.1, "error": null }
    }
  }
  ```
Both live outside `/api/v1` since they're infra-facing, and both are
wired into `docker-compose.yml`'s healthcheck directives.

## Pluggability — proof, not just a claim

Every swappable piece resolves through exactly one seam:

| Swap | What changes | What doesn't |
|---|---|---|
| **Postgres -> MySQL** | `app/db/session.py` (driver/engine construction) + swap `asyncpg` for an async MySQL driver in `pyproject.toml`. SQLAlchemy Core/ORM usage in repositories is dialect-agnostic already. | `app/services/*`, `app/api/*`, every repository's business methods |
| **JWT library swap** (e.g. PyJWT -> python-jose) | `app/core/security.py` only — it's the only module that imports `jwt`/`bcrypt` | `app/api/v1/dependencies.py` (still depends on `get_current_user`/`TokenPayload`), every router |
| **Add a new external cache** (e.g. Memcached alongside Redis) | Add a new `AbstractCacheRepository` implementation next to `RedisCacheRepository` in `app/repositories/cache_repository.py`, then change the provider in `app/api/v1/dependencies.py` | `app/services/*` — they depend on `AbstractCacheRepository`, never on `redis.asyncio` directly |
| **Local/system Postgres + Docker Redis -> Azure managed services** | Env vars only (`DATABASE_URL` with `?ssl=require` for Azure Postgres Flexible Server, `REDIS_*`/`REDIS_URL`, `REDIS_SSL=true`) | Zero code — `app/db/session.py` and `app/db/redis.py` are the only places that read those settings, and both already support SSL |

Other pluggability mechanisms baked in:
- `AbstractRepository`/`SQLAlchemyRepository` split (`app/repositories/base.py`) — Services depend on the abstract interface.
- All DI resolved centrally in `app/api/v1/dependencies.py` — routers only ever import from there.
- `core/config.py` is the only module reading `os.environ`.

## Azure deployment notes

- **Container registry:** `Dockerfile` is registry-agnostic — build and
  tag as `<name>:<version>` / `<name>:latest`, push to ACR.
- **Compute target:** Either **Azure Container Apps** or **App Service
  (Web App for Containers)** work unchanged — both just need the image +
  env vars. This scaffold doesn't assume AKS.
- **Database/cache:** production `DATABASE_*`/`REDIS_*` env vars point at
  Azure Database for PostgreSQL (Flexible Server) and Azure Cache for
  Redis. Set `DATABASE_SSL_MODE=require` and `REDIS_SSL=true`.
- **Secrets:** production config is resolvable purely from environment
  variables (App Service/Container Apps settings, or Key Vault
  references) — no `.env` file is assumed or required in containers.
- **Logging:** structlog emits JSON to stdout automatically whenever
  `ENVIRONMENT` is `staging`/`production` (or `LOG_JSON=true`) — Azure
  Monitor/Log Analytics ingests this directly from the container stream.
- **Health probes:** `/health/live` and `/health/ready` map directly onto
  Container Apps/App Service health probe configuration.
- **`TRUSTED_HOSTS` gotcha:** ships as `["*"]` even in `.env.staging`/
  `.env.production` — this was discovered the hard way while verifying
  this scaffold. Health probes (Docker's own `HEALTHCHECK`, and Azure's
  Container Apps/App Service probes) hit the container directly, often
  with a Host header that doesn't match the public hostname (localhost,
  an internal IP). Locking `TRUSTED_HOSTS` down to the public domain
  alone makes the container fail its own healthcheck and get pulled out
  of rotation. If you restrict this, also include whatever Host header
  your platform's probe actually sends.
- CI/CD pipelines and IaC (Bicep/Terraform/GitHub Actions/Azure DevOps)
  are intentionally out of scope for this commit.

## Forward compatibility: future AI chatbot module

- When added, `ai_chatbot` will be its own module (routers/services/
  repositories) following the same 3-layer pattern, and won't reach into
  `assets`/`tickets` internals directly.
- Nothing here assumes every route is simple request/response JSON —
  adding a `StreamingResponse` (SSE) or WebSocket route later is a normal
  FastAPI addition, not a rework.
- The standard success/error envelope applies to normal JSON endpoints
  only; streaming/WebSocket endpoints will need their own event-shaped
  convention, decided when that module is built.
- `core/config.py` has an `LLM_*` settings placeholder group (provider,
  API key, model name, timeout) ready for the chatbot module to use
  without restructuring `Settings`.
- The existing Redis cache abstraction is expected to double as chat
  session/context storage later.

## Testing

- `tests/unit/` — no external dependencies; safe to run anywhere
  (`uv run pytest tests/unit`).
- `tests/integration/` — requires the docker-compose stack (`make up`);
  run via `make test` / `make test-integration`, which exec into the
  running `api` container so the `redis` hostname resolves and Postgres
  is reachable via `host.docker.internal` (see "Local Postgres, not a
  container" above).
- `pytest-asyncio` is configured with a **session-scoped** event loop
  (`asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope`
  = `session`), because the app's DB engine and Redis pool are
  module-level singletons created once at import time — per-test event
  loops (the default) would break them after the first test.

## Dependency management

Dependencies are pinned to exact versions in `pyproject.toml` (via
`uv add`) and locked in `uv.lock` — no loose `>=` ranges for core deps,
so installs are reproducible.

`requirements.txt` is a **generated artifact** (`uv export --format
requirements-txt --no-dev --no-hashes -o requirements.txt`) for tools
that expect a plain requirements file (some CI runners, IDEs). Do not
hand-edit it — regenerate it from `uv.lock` whenever dependencies change.

All packages were pinned to their latest stable release as of setup time
(FastAPI 0.139.0, SQLAlchemy 2.0.51, Pydantic 2.13.4 / pydantic-settings
2.14.2, Alembic 1.18.5, asyncpg 0.31.0, structlog 26.1.0, redis-py 8.0.1,
PyJWT 2.13.0, bcrypt 5.0.0). No known incompatibilities forced a pin
below latest; `uv lock` resolved everything together in one pass.

## Docker images

`Dockerfile` is multi-stage:
- `dev` — full deps (incl. ruff/mypy/pytest), used by `docker-compose.yml` for local development with hot reload (`uvicorn --reload`) and bind-mounted source.
- `runtime` (the default build target, what ships to ACR) — production deps only, non-root user, `gunicorn` + `uvicorn.workers.UvicornWorker`.

## Local port conflicts

Redis is published to the host on `6380` by default — not `6379` — since
most dev machines already have a local Redis bound to the default port,
which used to make `make up` fail with "address already in use". If
`6380` is *also* taken, override it without editing any file:

```bash
REDIS_HOST_PORT=16379 make up
```

This only changes what's published to the host; the `api` container
still talks to `redis:6379` over the internal Docker network — unrelated
to (and unaffected by) `REDIS_PORT` in `.env.development`, which
configures that internal connection, not the host mapping. Postgres
isn't part of `docker-compose.yml` at all (see "Local Postgres, not a
container" above), so its port is whatever your local install already
uses — no publish/override mechanism needed here.
