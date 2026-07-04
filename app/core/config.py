"""Centralized application configuration.

Every environment-specific or swappable value (DB URL, Redis URL, JWT
secrets, CORS origins, pagination defaults, etc.) must live here and
nowhere else. Business/data-access code reads `settings`, it never reads
`os.environ` directly. This is what makes infra swaps (local Docker ->
Azure managed Postgres/Redis) a pure env-var change.
"""

import os
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


def _resolve_env_file() -> str:
    """Picks exactly ONE env file based on `ENVIRONMENT`/`ENV_FILE` — never
    merge multiple, since e.g. `.env.production`'s placeholder secrets
    would silently clobber `.env.development`'s real local values if all
    were loaded together. Missing files are ignored by pydantic-settings,
    so this is a no-op in containers where real env vars are injected
    directly (Azure App Service / Container Apps) and no .env file exists.
    """
    if env_file := os.getenv("ENV_FILE"):
        return env_file
    environment = os.getenv("ENVIRONMENT", Environment.DEVELOPMENT.value)
    return f".env.{environment}"


class Settings(BaseSettings):
    """Reads from process environment first, then from a single env file
    selected by `ENVIRONMENT` (local dev convenience only). Production
    never needs an env file — Azure App Service / Container Apps injects
    real environment variables directly.
    """

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Core / environment ---
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    APP_NAME: str = "asset-pilot-fastapi"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # --- API ---
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS / middleware ---
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: list[str] = Field(default_factory=lambda: ["*"])
    TRUSTED_HOSTS: list[str] = Field(default_factory=lambda: ["*"])
    GZIP_MIN_SIZE: int = 500

    # --- Database (SQLAlchemy async / PostgreSQL) ---
    # Full URL is derived unless DATABASE_URL is explicitly set (e.g. Azure
    # connection string). Async driver is asyncpg; Azure Postgres Flexible
    # Server requires sslmode=require, expressed via DATABASE_SSL_MODE.
    DATABASE_URL: PostgresDsn | None = None
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"
    DATABASE_HOST: str = "postgres"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "asset_pilot"
    DATABASE_SSL_MODE: str = "disable"  # "require" in Azure production

    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: RedisDsn | None = None
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False  # true for Azure Cache for Redis (rediss://)
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_MAX_CONNECTIONS: int = 20

    # --- JWT / security ---
    JWT_SECRET_KEY: str = "change-me-in-env-to-a-random-string-of-at-least-32-bytes"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    JWT_ISSUER: str = "asset-pilot-fastapi"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False  # forced True for staging/production, see below

    # --- Pagination defaults (shared across list endpoints) ---
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # --- Health checks ---
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 2.0

    # --- Rate limiting (plumbing only, no enforcement logic yet) ---
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # --- Future AI chatbot module placeholder (not wired up yet) ---
    LLM_PROVIDER: str | None = None
    LLM_API_KEY: str | None = None
    LLM_MODEL_NAME: str | None = None
    LLM_REQUEST_TIMEOUT_SECONDS: float = 30.0

    @model_validator(mode="after")
    def _forbid_wildcard_origin_with_credentials(self) -> "Settings":
        # Browsers reject Access-Control-Allow-Origin: * paired with
        # Access-Control-Allow-Credentials: true (Fetch spec) — every
        # credentialed cross-origin request would silently fail client-side.
        # Self-correct rather than error, since "*" is a reasonable default
        # for anonymous/local-dev use.
        if self.CORS_ALLOW_ORIGINS == ["*"] and self.CORS_ALLOW_CREDENTIALS:
            self.CORS_ALLOW_CREDENTIALS = False
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL is not None:
            return str(self.DATABASE_URL)
        query = "" if self.DATABASE_SSL_MODE == "disable" else f"?ssl={self.DATABASE_SSL_MODE}"
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}{query}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_uri(self) -> str:
        if self.REDIS_URL is not None:
            return str(self.REDIS_URL)
        scheme = "rediss" if self.REDIS_SSL else "redis"
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_log_json(self) -> bool:
        return self.LOG_JSON or self.ENVIRONMENT in (Environment.PRODUCTION, Environment.STAGING)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Depend on this, not on Settings() directly,
    so the whole app shares one instance and env files are parsed once.
    """
    return Settings()


settings = get_settings()
