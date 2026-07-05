# asset-pilot-fastapi

**AssetPilot** — an internal IT Asset Management (ITAM) platform backend. Manages the complete device lifecycle from inventory → request → approval → assignment → optional WFH shipping → support/repair → peer handover → return → retirement, with a permanent append-only per-device audit trail.

**Current Status:** Infrastructure complete, domain code in progress. Only the **IT-Admin API** (`_docs/IT_ADMIN_API_FLOW.md`) is being built right now. Employee/Manager flows exist as seed data only, not endpoints.

**Three modules (planned):**
- **IT Asset Management System** (ITAM) — under active development
- **Ticket Management System** — planned
- **AI Chatbot** — future phase

See `_docs/IMPLEMENTATION_PLAN.md` for the module development roadmap and current progress.

## Tech stack (pinned in `pyproject.toml`)

| Concern | Choice |
|---|---|
| Language & Framework | **Python ≥3.12**, **FastAPI 0.139.0**, Starlette 1.3.1, uvicorn 0.50.0 (gunicorn in prod) |
| Database | **PostgreSQL 17** via **SQLAlchemy[asyncio] 2.0.51** + **asyncpg 0.31.0**; **Alembic 1.18.5** (async) |
| Validation & Serialization | **Pydantic 2.13.4** + **pydantic-settings 2.14.2** |
| Authentication | **PyJWT 2.13.0** (HS256, access+refresh) + **bcrypt 5.0.0** (not python-jose/passlib) |
| Logging | **structlog 26.1.0** (JSON in prod, console in dev) |
| Code Quality | **ruff** (lint/format), **mypy strict** (type checking) |
| Testing | **pytest** + **pytest-asyncio** (`asyncio_mode=auto`) |
| Dependency Management | **uv** (`uv.lock` for reproducibility; `requirements.txt` is a generated export) |
| Containerization | **Docker** (multi-stage: dev + runtime) + **Docker Compose** |

## Architecture: strict 3-layer separation

```
API layer (app/api)         -> HTTP in/out, Pydantic schemas only, no DB session, no ORM models
Service layer (app/services) -> business logic, orchestrates repositories, no HTTP awareness
Repository layer (app/repositories) -> the ONLY layer touching SQLAlchemy directly
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
      routers/            # versioned routers
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
  models/                      # SQLAlchemy models (empty until a domain module lands)
  schemas/                      # Pydantic DTOs
  services/                      # business logic (health — trivial slice only)
  repositories/                   # data access (base repo interface, health repo)
  main.py                          # app factory, middleware, global exception handlers
alembic/                            # migrations (async engine configured)
tests/
  unit/                              # no external deps required
  integration/                        # requires the docker-compose stack up
scripts/
docker/
```

## Quick Start (Local Development)

### Prerequisites

- **Docker** and **Docker Compose**
- **`uv`** (Python package manager — [install here](https://docs.astral.sh/uv/getting-started/installation/))
- **PostgreSQL 17** running and accessible (either local/system or remote; see "External Postgres" below)
- **Python 3.12+** (checked by `uv`)

### Setup Steps

1. **Clone and install dependencies:**
   ```bash
   git clone <repo-url>
   cd asset-pilot-fastapi
   make install    # uv sync — install all deps (dev + runtime)
   ```

2. **Create `.env` file** (see "Environment configuration" below for all keys):
   ```bash
   touch .env
   # Then edit .env with your values (copy the template from "Environment configuration")
   make env        # verifies .env exists
   ```

3. **Create and migrate the database:**
   ```bash
   make create-db  # creates the DB if missing (native, via uv + psql)
   make migrate    # alembic upgrade head (native, via uv)
   ```

4. **Start the API (development mode with hot reload):**
   ```bash
   make up         # build + start the api container (detached)
   ```

5. **Verify it's running:**
   ```bash
   make health     # curl /health/ready and pretty-print
   curl http://localhost:8000/health/live
   ```

The API is now at `http://localhost:8000/api/v1`.

### Test the Production Build Locally

To test the production-shaped image (gunicorn + uvicorn workers, non-root, prod deps only) before deployment:

```bash
BUILD_TARGET=runtime docker compose up -d --build
# Test it, then switch back:
make down
make up
```

## Make Commands

Run `make help` for a complete list. Common commands:

### Setup & Dependencies
| Command | What it does |
|---|---|
| `make install` | `uv sync` — install all dependencies (dev + runtime) |
| `make env` | Verify `.env` exists (create it manually; see "Environment configuration") |

### Docker & Local Development
| Command | What it does |
|---|---|
| `make up` | Build and start the API container (detached, with hot reload) |
| `make down` | Stop and remove containers |
| `make down-v` | Stop, remove containers + volumes (clean slate) |
| `make rebuild` | Rebuild images from scratch, then start |
| `make logs` / `make logs-api` | Tail container logs (live) |
| `make shell-api` | Open a shell inside the running `api` container |
| `make ps` | Show running containers (`docker compose ps`) |

### Database Management (Native, Host-side)
All DB commands run **on the host** via `uv run` (not in the container), so they work even if Docker isn't running:

| Command | What it does |
|---|---|
| `make create-db` | Create the target database if missing |
| `make migrate` | Run pending migrations (`alembic upgrade head`) |
| `make makemigrations message="..."` | Generate a new migration (`alembic revision --autogenerate -m "..."`) |
| `make migrate-down` | Roll back one migration |
| `make db-reset` | Drop + recreate + re-migrate the local DB (⚠️ **destructive, local only**) |
| `make shell-db` | Open `psql` connected to the local/system Postgres |

### Testing & Code Quality
| Command | What it does |
|---|---|
| `make test` | Run full pytest suite (inside the container) |
| `make test-unit` | Unit tests only (no external deps; runs on host via `uv run`) |
| `make test-integration` | Integration tests (inside container; requires `make up`) |
| `make coverage` | Run pytest with coverage report |
| `make lint` | `ruff check` + `mypy --strict` |
| `make format` | `ruff format` + `ruff check --fix` |
| `make pre-commit` | Run pre-commit hooks on all files |

### Cleanup & Troubleshooting
| Command | What it does |
|---|---|
| `make clean` | Remove cache artifacts (`.mypy_cache`, `.pytest_cache`, `__pycache__`, etc.) — safe, doesn't touch Docker/volumes |
| `make health` | Curl `/health/ready` and pretty-print the response |
| `make help` | Show the full list of Makefile targets |

## Environment Configuration

Configuration is centralized in `app/core/config.py` via Pydantic `Settings` — no hardcoded values, everything comes from environment variables. There are exactly **two environments** and exactly **one env file**:

- **Local development:** A single `.env` file in the repo root (gitignored, never committed). Create it manually with the keys below.
- **Production (Azure):** No `.env` file. Azure App Service / Container Apps injects environment variables directly, including secrets from **Azure Key Vault** via "Key Vault reference" app settings (`@Microsoft.KeyVault(...)`). Azure resolves these to plain env vars before the container starts — the app just reads `os.environ` like it does locally.

### Environment Variables Template

Copy and edit this for your `.env` file (local development):

```bash
# App identification
ENVIRONMENT=development            # development | production
APP_NAME=asset-pilot-fastapi
APP_VERSION=0.1.0
DEBUG=true

# API configuration
API_V1_PREFIX=/api/v1
HOST=0.0.0.0
PORT=8000

# CORS & security headers
CORS_ALLOW_ORIGINS=["*"]           # Use ["http://localhost:3000"] in production
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=["*"]
CORS_ALLOW_HEADERS=["*"]
TRUSTED_HOSTS=["*"]                # Restrict to actual domain in production
GZIP_MIN_SIZE=500

# Database (PostgreSQL 17)
# ⚠️  No Postgres container — point this at your external/managed Postgres
# For Azure Postgres Flexible Server, add ?ssl=require to the URL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/asset_pilot_db
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800
DATABASE_ECHO=false                # Set true only for SQL debugging

# JWT (access + refresh tokens)
JWT_SECRET_KEY=your-long-random-secret-change-this
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_MINUTES=10080  # 7 days
JWT_ISSUER=asset-pilot-fastapi

# Logging
LOG_LEVEL=INFO                      # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_JSON=false                      # Forced true in production; false = colored console

# Pagination defaults
DEFAULT_PAGE_SIZE=20
MAX_PAGE_SIZE=100

# Monitoring & health checks
HEALTH_CHECK_TIMEOUT_SECONDS=2.0

# Rate limiting (optional)
RATE_LIMIT_ENABLED=false
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# Future: AI chatbot module (unused, left for future modules)
LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL_NAME=
LLM_REQUEST_TIMEOUT_SECONDS=30.0
```

### Key Notes

- **Local development:** Use `DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/asset_pilot_db` (or your system Postgres).
- **Azure Database for PostgreSQL:** Add `?ssl=require` to the connection string.
- **Secrets in production:** Store `JWT_SECRET_KEY` and `DATABASE_URL` in Azure Key Vault, reference them as `@Microsoft.KeyVault(SecretUri=https://vault.azure.net/secrets/...)` in App Service settings.
- **Docker healthcheck:** Uses `/health/live` and `/health/ready` probes; don't restrict `TRUSTED_HOSTS` too much or the container will fail its own healthcheck.

## Database: External Postgres (Not a Container)

**Important:** `docker-compose.yml` does **not** run a Postgres container. Instead, it expects `DATABASE_URL` in `.env` to point at an external/managed Postgres instance reachable by hostname from both the host and the Docker API container.

### Why This Approach?

- **Simplicity:** One less container to manage locally.
- **Parity with production:** Production uses Azure Database for PostgreSQL (managed service), not a container.
- **DB operations work outside Docker:** You can run migrations and manage the DB even if Docker isn't running.

### Setup

1. **Ensure Postgres is accessible:**
   - **Local:** Run `brew install postgresql` (macOS) or `apt install postgresql` (Ubuntu), then `postgres -D /usr/local/var/postgres` (macOS) or equivalent.
   - **Remote:** Point `DATABASE_URL` at your managed instance (Azure Postgres Flexible Server, AWS RDS, etc.).

2. **DB commands run natively on the host:**
   ```bash
   make create-db          # Host: uv run + creates DB
   make migrate            # Host: uv run + alembic upgrade
   make shell-db           # Host: psql command
   ```
   These work **independent of Docker**; they read `DATABASE_URL` from `.env`.

3. **The API container and integration tests connect to the same database:**
   ```bash
   make up                 # Container runs; connects to DATABASE_URL
   make test-integration   # Execs into container; same DATABASE_URL
   ```
   No extra networking config needed — Docker can reach `localhost` or your external Postgres hostname.

### Troubleshooting: "Connection refused"

- **Local Postgres:** Verify it's running: `psql -U postgres -d postgres -c "SELECT 1"`
- **Remote Postgres:** Check `DATABASE_URL` includes the correct hostname, port, and `?ssl=require` (for Azure).
- **From Docker:** The container uses the same `DATABASE_URL` as the host — if the host can reach it, so can Docker.

## Response Envelope & Error Handling

Every endpoint under `/api/v1` returns a consistent JSON shape (success or error) via `success_response()` / `error_response()` in `app/utils/response.py`. Global exception handlers in `app/main.py` funnel all failures — custom domain exceptions, validation errors, `HTTPException`, and unhandled exceptions — through a single error envelope, so nothing invents its own shape.

### Success Response
```json
{
  "status_code": 200,
  "data": { "id": "...", "name": "..." },
  "message": "Device retrieved successfully",
  "meta": {
    "timestamp": "2026-07-05T12:34:56.789Z",
    "request_id": "req_abc123..."
  },
  "success": true
}
```

For paginated lists:
```json
{
  "status_code": 200,
  "data": [ { "id": "...", "name": "..." }, ... ],
  "message": "Devices retrieved successfully",
  "meta": {
    "timestamp": "2026-07-05T12:34:56.789Z",
    "request_id": "req_abc123...",
    "pagination": {
      "total": 42,
      "page": 1,
      "per_page": 20,
      "pages": 3
    }
  },
  "success": true
}
```

### Error Response
```json
{
  "status_code": 404,
  "message": "Device with id 550e8400 was not found",
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Device not found",
    "details": null
  },
  "meta": {
    "timestamp": "2026-07-05T12:34:56.789Z",
    "request_id": "req_abc123..."
  },
  "success": false
}
```

### Exception Codes

Defined in `app/core/exceptions.py`:
- **`VALIDATION_ERROR`** (422) — malformed request data
- **`UNAUTHORIZED`** (401) — missing or invalid auth token
- **`FORBIDDEN`** (403) — authenticated but not allowed
- **`RESOURCE_NOT_FOUND`** (404) — entity doesn't exist
- **`CONFLICT`** (409) — state violation (e.g., duplicate email, wrong entity state)
- **`RATE_LIMITED`** (429) — rate limit exceeded
- **`INTERNAL_SERVER_ERROR`** (500) — unhandled exception
- **`SERVICE_UNAVAILABLE`** (503) — DB unreachable, etc.

### Exceptions to the Envelope
- **`/health/live` and `/health/ready`** — infra probes with their own shape (see below).
- **`204 No Content`** — no body by definition.
- **Future streaming/WebSocket** — will use event-shaped convention when added.

## Health Checks

Two probes for container orchestration (Docker, Kubernetes, Azure Container Apps):

### Liveness Probe
**`GET /health/live`** — Is the process alive?
- No dependency checks; always returns `200` unless the process itself is broken.
- Used by Docker `HEALTHCHECK` and orchestrators to detect dead processes.

Response:
```json
{
  "status": "alive",
  "timestamp": "2026-07-05T12:34:56.789Z"
}
```

### Readiness Probe
**`GET /health/ready`** — Can the service handle requests?
- Runs `SELECT 1` against Postgres (with a short timeout).
- Returns `200` if database is reachable, `503` if not.
- Used by orchestrators to determine if the pod should receive traffic.

Response (success):
```json
{
  "status": "ok",
  "timestamp": "2026-07-05T12:34:56.789Z",
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 4.2,
      "error": null
    }
  }
}
```

Response (failure):
```json
{
  "status": "unhealthy",
  "timestamp": "2026-07-05T12:34:56.789Z",
  "checks": {
    "database": {
      "status": "error",
      "latency_ms": 2004.5,
      "error": "Connection timeout"
    }
  }
}
```

### Configuration
- Both probes live **outside `/api/v1`** since they're infra-facing.
- **Docker Compose:** Configured in `docker-compose.yml`'s `healthcheck` directive.
- **Azure Container Apps:** Map `/health/live` to startup probe, `/health/ready` to readiness probe.
- **App Service:** Set "Health check path" to `/health/ready`.

### Testing Locally
```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready    # Returns 503 if DB is down
```

## Pluggability: Swappable Components

Every swappable component resolves through exactly one seam. The architecture is designed for easy replacement of major dependencies without cascading changes.

### Common Swaps

| Scenario | What Changes | What Doesn't |
|---|---|---|
| **Postgres → MySQL** | `app/db/session.py` (driver/engine construction) + swap `asyncpg` for async MySQL driver in `pyproject.toml`. SQLAlchemy Core/ORM is dialect-agnostic. | `app/services/*`, `app/api/*`, repository business methods, models |
| **JWT → python-jose** | `app/core/security.py` only (encapsulates all JWT/crypto). Swap PyJWT + bcrypt for python-jose + passlib. | All DI/router code; still depends on abstract `TokenPayload` and `get_current_user` |
| **Local Postgres → Azure Postgres** | Env vars only: `DATABASE_URL` with `?ssl=require` for Azure Flexible Server. | Zero code changes; `app/db/session.py` already supports SSL and connection pooling. |
| **Local console logs → Cloud logging** | Update `app/core/logging.py` to route structlog to JSON sink (Cloud Logging, Datadog, etc.). | Everything else; structlog already emits JSON in production. |
| **Sync DB → Async DB** | `app/db/session.py` (swap asyncpg for another async driver). SQLAlchemy async ORM is already in place. | All repository code; already uses `async`/`await`. |

### Built-in Pluggability Patterns

**Repository abstraction:**
- `AbstractRepository` interface in `app/repositories/base.py`.
- Services depend on the abstract interface, not concrete `SQLAlchemyRepository`.
- Easy to mock for testing; easy to swap implementations.

**Centralized DI:**
- All dependency wiring in `app/api/v1/dependencies.py` — one file.
- Routers import DI aliases only; never construct services directly.
- Change a provider once; affects all routers automatically.

**Configuration seam:**
- `app/core/config.py` is the only module reading `os.environ`.
- Settings is a dataclass; easy to mock or override for testing.
- No hardcoded values anywhere else in the codebase.

**Logging abstraction:**
- structlog configured in `app/core/logging.py`.
- All code uses `structlog.get_logger()`.
- Swap the sink without touching application code.

## Deployment

### Build the Production Image

The `Dockerfile` is multi-stage:
- **`dev`** (default in `docker-compose.yml`) — full deps, hot reload, for local development.
- **`runtime`** (shipped to ACR) — production deps only, `gunicorn` + `uvicorn.workers.UvicornWorker`, non-root user.

**Build the runtime (production) image:**

```bash
# Build locally to test
docker build --target runtime -t asset-pilot-fastapi:latest .

# Or via docker-compose with BUILD_TARGET
BUILD_TARGET=runtime docker compose build

# Tag and push to your container registry
docker tag asset-pilot-fastapi:latest myregistry.azurecr.io/asset-pilot-fastapi:latest
docker push myregistry.azurecr.io/asset-pilot-fastapi:latest
```

### Azure Deployment (Container Apps / App Service)

#### Prerequisites
- **Azure Container Registry (ACR)** — for storing the built image.
- **Azure Database for PostgreSQL (Flexible Server)** — production database.
- **Azure Key Vault** — for secrets (JWT_SECRET_KEY, DATABASE_URL).
- **Azure Container Apps** or **App Service (Web App for Containers)** — compute target.

#### Step-by-Step

1. **Build and push the image to ACR:**
   ```bash
   az acr build --registry myregistry --image asset-pilot-fastapi:latest .
   ```

2. **Create secrets in Azure Key Vault:**
   ```bash
   az keyvault secret set --vault-name mykeyvault --name jwt-secret-key --value "your-long-random-secret"
   az keyvault secret set --vault-name mykeyvault --name database-url --value "postgresql+asyncpg://user:password@server.postgres.database.azure.com:5432/asset_pilot_db?ssl=require"
   ```

3. **Deploy to Azure Container Apps or App Service:**

   **Option A: Container Apps**
   ```bash
   az containerapp create \
     --name asset-pilot-api \
     --resource-group myresourcegroup \
     --image myregistry.azurecr.io/asset-pilot-fastapi:latest \
     --target-port 8000 \
     --env-vars \
       ENVIRONMENT=production \
       APP_NAME=asset-pilot-fastapi \
       APP_VERSION=0.1.0 \
       DEBUG=false \
       API_V1_PREFIX=/api/v1 \
       HOST=0.0.0.0 \
       PORT=8000 \
       CORS_ALLOW_ORIGINS='["https://yourfrontend.com"]' \
       CORS_ALLOW_CREDENTIALS=true \
       CORS_ALLOW_METHODS='["GET","POST","PUT","DELETE","PATCH"]' \
       CORS_ALLOW_HEADERS='["*"]' \
       TRUSTED_HOSTS='["*.azurecontainerapps.io", "yourdomain.com"]' \
       LOG_LEVEL=INFO \
       LOG_JSON=true \
       DEFAULT_PAGE_SIZE=20 \
       MAX_PAGE_SIZE=100 \
       HEALTH_CHECK_TIMEOUT_SECONDS=2.0 \
     --secrets \
       jwt-secret-key=keyvault_reference:jwt-secret-key \
       database-url=keyvault_reference:database-url \
     --secrets-json '{"JWT_SECRET_KEY":"@jwt-secret-key","DATABASE_URL":"@database-url"}' \
     --ingress external \
     --query properties.configuration.ingress.fqdn
   ```

   **Option B: App Service**
   ```bash
   az appservice plan create --name myplan --resource-group myresourcegroup --sku B1 --is-linux
   az webapp create --name asset-pilot-api --resource-group myresourcegroup --plan myplan --deployment-container-image-name myregistry.azurecr.io/asset-pilot-fastapi:latest
   
   # Configure app settings
   az webapp config appsettings set --resource-group myresourcegroup --name asset-pilot-api \
     --settings ENVIRONMENT=production DEBUG=false \
     WEBSITES_PORT=8000 \
     DOCKER_REGISTRY_SERVER_URL=https://myregistry.azurecr.io \
     DOCKER_REGISTRY_SERVER_USERNAME=$(az acr credential show --name myregistry --query username -o tsv) \
     DOCKER_REGISTRY_SERVER_PASSWORD=$(az acr credential show --name myregistry --query passwords[0].value -o tsv)
   
   # Set secrets via Key Vault references
   az webapp config appsettings set --resource-group myresourcegroup --name asset-pilot-api \
     --settings JWT_SECRET_KEY="@Microsoft.KeyVault(SecretUri=https://mykeyvault.vault.azure.net/secrets/jwt-secret-key/)" \
     DATABASE_URL="@Microsoft.KeyVault(SecretUri=https://mykeyvault.vault.azure.net/secrets/database-url/)"
   ```

4. **Verify deployment:**
   ```bash
   # Get the app URL
   az containerapp show --name asset-pilot-api --resource-group myresourcegroup --query properties.configuration.ingress.fqdn -o tsv
   
   # Test health check
   curl https://<app-url>/health/ready
   ```

#### Important Notes

- **No `.env` file in production** — all config comes from App Service/Container Apps environment variables.
- **Key Vault references** — use `@Microsoft.KeyVault(SecretUri=...)` syntax; Azure resolves these before the container starts.
- **Database SSL** — Azure Postgres Flexible Server requires `?ssl=require` in the connection string.
- **Health probes:**
  - Container Apps: Configure `Ingress` → `Health probe` → `/health/ready`.
  - App Service: Configure under `Settings` → `Health check path` → `/health/ready`.
- **`TRUSTED_HOSTS`** — must include the Container Apps/App Service hostname (and your custom domain if used); keep as broad as needed to avoid healthcheck failures.
- **Logging** — structlog automatically emits JSON to stdout in production; Azure Monitor/Log Analytics ingests this directly.

#### CI/CD Integration (GitHub Actions Example)

```yaml
name: Deploy to Azure

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build and push to ACR
        run: |
          az acr build --registry ${{ secrets.ACR_NAME }} \
            --image asset-pilot-fastapi:${{ github.sha }} \
            --image asset-pilot-fastapi:latest .
      
      - name: Deploy to Container Apps
        run: |
          az containerapp update --name asset-pilot-api \
            --resource-group ${{ secrets.RESOURCE_GROUP }} \
            --image ${{ secrets.ACR_LOGIN_SERVER }}/asset-pilot-fastapi:${{ github.sha }}
```

### Rollback

To revert to a previous version:

```bash
# Container Apps
az containerapp revision list --name asset-pilot-api --resource-group myresourcegroup
az containerapp revision activate --name asset-pilot-api --resource-group myresourcegroup --revision <previous-revision-id>

# App Service
az webapp deployment slot swap --resource-group myresourcegroup --name asset-pilot-api --slot staging
```

## API Documentation

### OpenAPI / Swagger

FastAPI auto-generates OpenAPI/Swagger docs from your routers and Pydantic models:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

These are **automatically generated** from:
- Router docstrings (become operation descriptions)
- Pydantic model field descriptions
- Type hints (query params, request body, response types)
- HTTP status codes in routers

**Example router docstring:**
```python
@router.get("/{device_id}", response_model=DeviceResponseSchema, status_code=200)
async def get_device(device_id: UUID):
    """Get a device by ID.
    
    Returns the full device record including audit trail links.
    """
    ...
```

### API Reference

See `_docs/IT_ADMIN_API_FLOW.md` for the full IT-Admin API specification, including:
- Endpoint paths and methods
- Request/response schemas
- Status codes
- Workflow diagrams
- Error scenarios

## Design & Extensibility

### Future Modules

When adding new modules (e.g., Ticket Management, AI Chatbot):

1. **Module isolation:** Each module is self-contained (models/services/repositories/routers). No cross-module imports; instead, query via that module's repository.
2. **Same 3-layer pattern:** Router → Service → Repository.
3. **No assumptions about protocol:** The scaffold is HTTP-first, but adding WebSocket/SSE routes later is straightforward (regular FastAPI).
4. **Streaming/WebSocket:** These need their own event-shaped convention (not the standard JSON envelope); decide when building that module.

### Config for Future Modules

`app/core/config.py` already has placeholders for the **AI Chatbot module**:
```python
LLM_PROVIDER: str = ""          # openai, anthropic, azure, etc.
LLM_API_KEY: str = ""
LLM_MODEL_NAME: str = ""
LLM_REQUEST_TIMEOUT_SECONDS: float = 30.0
```

Set these in production for the chatbot module without restructuring settings; they're ignored until the module needs them.

## Testing

The test suite is split into unit and integration tests:

### Unit Tests
Located in `tests/unit/` — no external dependencies; run anywhere:

```bash
make test-unit                      # Run on host via uv
uv run pytest tests/unit -v         # Or directly
```

### Integration Tests
Located in `tests/integration/` — requires the API container and Postgres to be running:

```bash
make up                             # Start the API container first
make test-integration               # Run inside the container
make test                           # Run full suite (unit + integration)
make coverage                       # Run with coverage report
```

### Test Configuration

- **Event loop:** pytest-asyncio is configured with **session-scoped** event loops (not per-test) because the app's DB engine is a module-level singleton. Per-test loops would break it after the first test.
- **Async fixtures:** Use `conftest.py` in each test directory; the setup provides an `AsyncHTTPClient` ASGI client for testing routes.
- **DB isolation:** Integration tests create tables in the test database; they don't interfere with local dev data (different `DATABASE_URL` or test suffix).

### Running Tests in CI

```bash
make lint                           # Ruff check + mypy strict
make test                           # Full suite
```

## Module Development Workflow

Each feature module (e.g., IT Asset Management, Ticket Management) follows a structured workflow. **See `_docs/IMPLEMENTATION_PLAN.md` for the full module roadmap and current progress.**

### Module Checklist

1. **Read the module spec** in `_docs/IMPLEMENTATION_PLAN.md` — understand scope, preconditions, acceptance criteria.
2. **Verify preconditions** — e.g., `from app.models import User` should resolve.
3. **One module per session** — don't mix modules unless explicitly told.
4. **Follow the 3-layer pattern:**
   - **Models** (`app/models/<domain>.py`) — SQLAlchemy models with `UUIDPrimaryKeyMixin` + `TimestampMixin`.
   - **Repositories** (`app/repositories/<domain>_repository.py`) — subclass `SQLAlchemyRepository[Model]`.
   - **Services** (`app/services/<domain>_service.py`) — business logic, raises `AppException` subclasses, returns dataclasses.
   - **Routers** (`app/api/v1/routers/<domain>.py`) — HTTP only, depends on DI aliases.
5. **Create migrations:**
   ```bash
   make makemigrations message="Add <entity> model"
   make migrate
   ```
6. **Write tests** — unit tests in `tests/unit/`, integration tests in `tests/integration/`.
7. **Code quality:**
   ```bash
   make lint                          # Ruff + mypy strict
   make format                        # Auto-fix style
   make test                          # Full suite
   ```
8. **Update `_docs/IMPLEMENTATION_PLAN.md`** — mark the module's Status as `Done`.

### Recommended Module Order

See `_docs/IMPLEMENTATION_PLAN.md` §3 for the full roadmap:
1. **M1** — Models & Migration
2. **M2** — Auth endpoints
3. **M3** / **M4** / **M6** — Seed data / Audit log / Users (can be parallel)
4. **M5** — Inventory
5. **M7** — Requests
6. ... (rest of the workflow)

### Example: Adding the User Module (M6)

```bash
# 1. Create the model
cat > app/models/user.py << 'EOF'
from sqlalchemy import Column, String, Boolean
from app.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
EOF

# 2. Create the repository
cat > app/repositories/user_repository.py << 'EOF'
from sqlalchemy import select
from app.models import User
from app.repositories.base import SQLAlchemyRepository

class UserRepository(SQLAlchemyRepository[User]):
    model = User
    
    async def get_by_email(self, email: str):
        stmt = select(self.model).where(self.model.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
EOF

# 3. Create the service
cat > app/services/user_service.py << 'EOF'
from dataclasses import dataclass
from app.repositories.user_repository import UserRepository
from app.core.exceptions import ConflictException

@dataclass
class UserResult:
    id: str
    name: str
    email: str

class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo
    
    async def create_user(self, name: str, email: str, password: str) -> UserResult:
        existing = await self.repo.get_by_email(email)
        if existing:
            raise ConflictException("User with this email already exists")
        # ... create user logic
EOF

# 4. Wire DI
# Edit app/api/v1/dependencies.py, add:
# def get_user_service(db: DbSession) -> UserService:
#     return UserService(UserRepository(db))
# UserServiceDep = Annotated[UserService, Depends(get_user_service)]

# 5. Create the router
cat > app/api/v1/routers/user.py << 'EOF'
from fastapi import APIRouter
from app.api.v1.dependencies import UserServiceDep
from app.utils.response import success_response

router = APIRouter(prefix="/admin/users", tags=["users"])

@router.get("")
async def list_users(user_service: UserServiceDep):
    users = await user_service.list_all()
    return success_response(data=[u.__dict__ for u in users])
EOF

# 6. Register the router
# Edit app/api/v1/routers/__init__.py, add:
# from . import user
# api_v1_router.include_router(user.router)

# 7. Create migration
make makemigrations message="Add User model"
make migrate

# 8. Test and verify
make lint
make test
```

## Dependency Management

### Using `uv` (Package Manager)

Dependencies are pinned to exact versions in `pyproject.toml` and locked in `uv.lock` — no loose version ranges, so installs are reproducible.

**Install dependencies:**
```bash
make install                        # uv sync
```

**Add a new dependency:**
```bash
uv add fastapi-cors                 # Adds to pyproject.toml and updates uv.lock
make format                         # Ensure consistent formatting
```

**Update dependencies (carefully):**
```bash
uv update                           # Updates all deps to latest compatible
uv lock                             # Regenerate uv.lock without changes to pyproject.toml
```

### Requirements.txt

`requirements.txt` is a **generated artifact** for CI/CD tools that don't support `uv`. **Do not hand-edit it** — regenerate after dependency changes:

```bash
uv export --format requirements-txt --no-dev --no-hashes -o requirements.txt
```

### Current Pinned Versions

All core dependencies were pinned to their latest stable releases at setup time:
- **FastAPI 0.139.0**, Starlette 1.3.1, uvicorn 0.50.0
- **SQLAlchemy[asyncio] 2.0.51** (with **asyncpg 0.31.0**)
- **Pydantic 2.13.4** + pydantic-settings 2.14.2
- **Alembic 1.18.5** (async migrations)
- **PyJWT 2.13.0** + **bcrypt 5.0.0**
- **structlog 26.1.0**
- **ruff**, **mypy**, **pytest**, **pytest-asyncio**

No incompatibilities forced pins below latest; `uv lock` resolved everything in one pass.

## Docker Images

`Dockerfile` is **multi-stage** with two targets:

### Development Target (`dev`)
- **Full dependencies:** ruff, mypy, pytest, etc.
- **Hot reload:** `uvicorn --reload` picks up file changes.
- **Bind-mounted source:** Edit code, see changes instantly in the running container.
- **Default in `docker-compose.yml`** — no extra flags needed for day-to-day dev.

```bash
make up                             # Uses BUILD_TARGET=dev by default
```

### Runtime Target (`runtime`)
- **Production deps only:** no dev tools.
- **gunicorn + uvicorn workers:** production-grade ASGI server.
- **Non-root user:** runs as a non-privileged account for security.
- **Default when building the `Dockerfile` directly** — what ships to ACR.

```bash
docker build --target runtime -t myimage:latest .
# Or test it locally:
BUILD_TARGET=runtime docker compose up --build
```

### The Two-Defaults Design

- **Bare `docker build`** (no `--target`) → `runtime` (for CI/ACR builds without extra flags).
- **`docker-compose.yml`** (no `BUILD_TARGET`) → `dev` (for local dev without extra flags).

This ensures CI is production-shaped and local dev is developer-friendly, both without configuration.

## Debugging & Troubleshooting

### Container & Network Issues

**Container won't start:**
```bash
make logs                           # Check container logs
make shell-api                      # Open a shell to debug
docker compose ps                   # Check container status
```

**"Connection refused" / "Can't reach database":**
```bash
# Verify Postgres is running
psql -U postgres -d postgres -c "SELECT 1"

# Check DATABASE_URL is correct
grep DATABASE_URL .env

# Verify from inside the container
make shell-api
echo $DATABASE_URL
psql $DATABASE_URL -c "SELECT 1"
```

**Port already in use:**
```bash
# Find what's using port 8000
lsof -i :8000

# Kill it (macOS/Linux)
kill -9 <PID>

# Or use a different port
echo "PORT=8001" >> .env
make down
make up
```

### Database Issues

**"Table doesn't exist":**
```bash
make migrate                        # Run pending migrations
# If still broken, check migration status:
make shell-db
\dt                                 # List tables in Postgres
```

**"Foreign key violation":**
- Check that parent records exist before creating child records.
- E.g., can't create a `DeviceLog` without a valid `device_id`.

**"Unique constraint violation":**
- E.g., trying to create two users with the same email.
- Check the error details for which column is duplicated.

### Logging & Debugging

**See application logs:**
```bash
make logs                           # All container logs
make logs-api                       # API logs only
```

**Enable SQL query logging:**
```bash
# In .env
DATABASE_ECHO=true

# Restart the container
make down
make up
```

**Enable debug mode:**
```bash
# In .env
DEBUG=true
LOG_LEVEL=DEBUG

# Restart
make down
make up
```

**View logs from a specific time:**
```bash
docker compose logs --since 2026-07-05T12:00:00 api
```

### Code Quality Issues

**"mypy: error: Cannot find implementation...":**
- Usually means a missing import in `__init__.py` or a typo.
```bash
make lint                           # Show all type errors
# Fix the imports, then:
make test
```

**"ruff: [E] [F]" errors:**
- E = PEP 8 style violations.
- F = PyFlakes (undefined names, unused imports).
```bash
make format                         # Auto-fix most issues
make lint                           # Re-check
```

**Test failures:**
```bash
make test -v                        # Verbose output
make test -k test_my_function       # Run a specific test
make test --tb=short                # Short traceback (less noise)
```

### Deployment Issues

**"Container fails healthcheck after deployment":**
- Check `TRUSTED_HOSTS` doesn't block the orchestrator's probe Host header.
- Add the actual hostname the orchestrator uses (often an internal DNS name).

**"503 Service Unavailable":**
- `/health/ready` is failing — database is unreachable.
- Check `DATABASE_URL` and verify the database is accessible from the container.

**"Authentication fails in production":**
- Verify `JWT_SECRET_KEY` is the same value used to issue tokens.
- Verify `JWT_ALGORITHM=HS256` (no typos).

### Getting Help

1. **Check logs first:** `make logs`
2. **Run tests:** `make test` — they often catch the root cause.
3. **Check the error code:** Most errors have a code in `app/core/exceptions.py`.
4. **Read the module spec:** `_docs/IMPLEMENTATION_PLAN.md` has known gaps and assumptions.
5. **Search `CLAUDE.md`:** It documents known issues and architecture decisions.

## Summary of Key Files

| File | Purpose |
|---|---|
| `app/main.py` | App factory, middleware, global exception handlers |
| `app/core/config.py` | All environment configuration (settings) |
| `app/core/security.py` | JWT + password hashing (auth logic) |
| `app/core/exceptions.py` | Domain exception taxonomy |
| `app/db/session.py` | Postgres engine & session factory |
| `app/db/base.py` | SQLAlchemy Base + shared mixins |
| `app/api/v1/dependencies.py` | **ALL dependency injection wiring** |
| `app/utils/response.py` | Standard response envelope builder |
| `Makefile` | All common operations (test, migrate, lint, etc.) |
| `docker-compose.yml` | Local dev stack (no Postgres container) |
| `Dockerfile` | Multi-stage: dev & runtime targets |
| `_docs/IMPLEMENTATION_PLAN.md` | Module development roadmap |
| `_docs/IT_ADMIN_API_FLOW.md` | IT-Admin API specification |
| `CLAUDE.md` | Detailed architecture & coding conventions |
