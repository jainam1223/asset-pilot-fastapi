.DEFAULT_GOAL := help

COMPOSE := docker compose
API := $(COMPOSE) exec api
RUN_API := $(COMPOSE) run --rm api

# ---- Setup ----

.PHONY: install
install: ## Sync all dependencies (incl. dev) via uv
	uv sync

.PHONY: env
env: ## Copy .env.example -> .env.development if it doesn't exist yet
	@test -f .env.development || cp .env.example .env.development
	@echo "-> .env.development ready"

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

.PHONY: logs-db
logs-db: ## Tail logs for the postgres service
	$(COMPOSE) logs -f postgres

.PHONY: logs-redis
logs-redis: ## Tail logs for the redis service
	$(COMPOSE) logs -f redis

# ---- Shell access ----

.PHONY: shell-api
shell-api: ## Exec into the running api container's shell
	$(API) bash

.PHONY: shell-db
shell-db: ## psql into the postgres container
	$(COMPOSE) exec postgres psql -U $${DATABASE_USER:-postgres} -d $${DATABASE_NAME:-asset_pilot}

.PHONY: shell-redis
shell-redis: ## redis-cli into the redis container
	$(COMPOSE) exec redis redis-cli

# ---- Database / migrations ----

.PHONY: migrate
migrate: ## Apply all pending migrations (alembic upgrade head)
	$(API) alembic upgrade head

.PHONY: makemigrations
makemigrations: ## Autogenerate a migration: make makemigrations message="..."
	$(API) alembic revision --autogenerate -m "$(message)"

.PHONY: migrate-down
migrate-down: ## Roll back one migration
	$(API) alembic downgrade -1

.PHONY: db-reset
db-reset: ## Drop, recreate, and re-migrate the local dev database (destructive, local only)
	$(COMPOSE) down -v postgres
	$(COMPOSE) up -d postgres
	$(API) alembic upgrade head

# ---- Testing ----

.PHONY: test
test: ## Run the full pytest suite (inside the api container)
	$(API) pytest

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(API) pytest tests/unit -m unit

.PHONY: test-integration
test-integration: ## Run integration tests only (needs postgres/redis up)
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
