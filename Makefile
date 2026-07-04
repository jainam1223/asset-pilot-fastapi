.DEFAULT_GOAL := help

COMPOSE := docker compose
API := $(COMPOSE) exec api
RUN_API := $(COMPOSE) run --rm api

# DB/migration commands run natively on the host via `uv run` (not inside
# the api container) so they work directly against your external/system
# Postgres without depending on docker networking. We pull DATABASE_URL
# out of the env file with grep (not `source`d) because e.g.
# CORS_ALLOW_ORIGINS=["*"] gets glob-expanded by the shell if the whole
# file is sourced. There is exactly one env file, always: .env.
HOST_ENV_FILE = .env
HOST_DATABASE_URL_CMD = DATABASE_URL=$$(grep '^DATABASE_URL=' $(HOST_ENV_FILE) | cut -d= -f2-)

# ---- Setup ----

.PHONY: install
install: ## Sync all dependencies (incl. dev) via uv
	uv sync

.PHONY: env
env: ## Verify .env exists (create it yourself; see README for required keys)
	@test -f .env || (echo "Missing .env — create one in the repo root with the required keys (see README's Environment configuration section)." && exit 1)
	@echo "-> .env present"

# ---- Docker lifecycle ----

.PHONY: up
up: ## Start all services, detached
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop and remove containers
	$(COMPOSE) down

.PHONY: down-v
down-v: ## Stop and remove containers + volumes (clean slate)
	$(COMPOSE) down -v

.PHONY: restart
restart: ## Restart all services
	$(COMPOSE) restart

.PHONY: build
build: ## Build images
	$(COMPOSE) build

.PHONY: rebuild
rebuild: ## Rebuild images with no cache and start
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

# ---- Logs ----

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f

.PHONY: logs-api
logs-api: ## Tail logs for the api service
	$(COMPOSE) logs -f api

# ---- Shell access ----

.PHONY: shell-api
shell-api: ## Exec into the running api container's shell
	$(API) bash

.PHONY: shell-db
shell-db: ## psql using DATABASE_URL from .env (runs natively on the host)
	@psql "$$(grep '^DATABASE_URL=' $(HOST_ENV_FILE) | cut -d= -f2- | sed -e 's/postgresql+asyncpg/postgresql/')"

# ---- Database / migrations ----

.PHONY: create-db
create-db: ## Create the target database if it doesn't already exist (runs natively via uv, against your host Postgres)
	@$(HOST_DATABASE_URL_CMD) uv run python -m scripts.create_db

.PHONY: migrate
migrate: ## Apply all pending migrations (alembic upgrade head) (runs natively via uv)
	@$(HOST_DATABASE_URL_CMD) uv run alembic upgrade head

.PHONY: makemigrations
makemigrations: ## Autogenerate a migration: make makemigrations message="..." (runs natively via uv)
	@$(HOST_DATABASE_URL_CMD) uv run alembic revision --autogenerate -m "$(message)"

.PHONY: migrate-down
migrate-down: ## Roll back one migration (runs natively via uv)
	@$(HOST_DATABASE_URL_CMD) uv run alembic downgrade -1

.PHONY: db-reset
db-reset: ## Drop, recreate, and re-migrate the target database (destructive) (runs natively via uv)
	@$(HOST_DATABASE_URL_CMD) uv run python -m scripts.create_db --recreate
	@$(HOST_DATABASE_URL_CMD) uv run alembic upgrade head

.PHONY: seed
seed: ## Seed deterministic demo data (truncates + reloads; runs natively via uv, needs a migrated DB)
	@$(HOST_DATABASE_URL_CMD) uv run python -m scripts.seed

.PHONY: add-user
add-user: ## Add a single user (edit name/email/role/password in scripts/add_user.py first; runs natively via uv)
	@$(HOST_DATABASE_URL_CMD) uv run python -m scripts.add_user

# ---- Testing ----

.PHONY: test
test: ## Run the full pytest suite (inside the api container)
	$(API) pytest

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(API) pytest tests/unit -m unit

.PHONY: test-integration
test-integration: ## Run integration tests only (needs Postgres reachable)
	$(API) pytest tests/integration -m integration

.PHONY: coverage
coverage: ## Run pytest with a coverage report
	$(API) pytest --cov=app --cov-report=term-missing

# ---- Code quality ----

.PHONY: lint
lint: ## Run ruff + mypy checks
	uv run ruff check .
	uv run mypy app tests

.PHONY: format
format: ## Auto-format with ruff
	uv run ruff format .
	uv run ruff check . --fix

.PHONY: pre-commit
pre-commit: ## Run all pre-commit hooks against all files
	uv run pre-commit run --all-files

.PHONY: clean
clean: ## Remove local cache/build artifacts (.mypy_cache, .pytest_cache, .ruff_cache, __pycache__, coverage files) — safe, no containers/volumes/env files touched
	rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name '__pycache__' -not -path './.venv/*' -exec rm -rf {} +
	find . -type f -name '*.py[co]' -not -path './.venv/*' -delete

# ---- Health / status ----

.PHONY: ps
ps: ## Show status of all compose services
	$(COMPOSE) ps

.PHONY: health
health: ## Curl /health/ready and pretty-print the JSON
	@curl -s http://localhost:$${PORT:-8000}/health/ready | python3 -m json.tool

.PHONY: help
help: ## Show this help
	@echo "Usage: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
