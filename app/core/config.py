"""Centralized application configuration.

Every environment-specific or swappable value (DB URL, Redis URL, JWT
secrets, CORS origins, pagination defaults, etc.) must live here and
nowhere else. Business/data-access code reads `settings`, it never reads
`os.environ` directly. This is what makes infra swaps (local Docker ->
Azure managed Postgres/Redis) a pure env-var change.

Only two environments exist: local development and production.
- **Local:** values come from a single `.env` file in the repo root
  (gitignored, never committed).
- **Production:** no `.env` file exists at all. Azure App Service /
  Container Apps injects real process environment variables directly,
  including secrets resolved from Azure Key Vault via App Service "Key
  Vault reference" app settings (`@Microsoft.KeyVault(...)`) — Azure
  resolves those into plain env vars before the process starts, so
  `Settings` never talks to Key Vault itself.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Reads from process environment first, then from `.env` if present.
    Locally that file supplies every value. In production no `.env` file
    exists, so this falls through entirely to real process env vars —
    the same ones Azure injects from App Service settings / Key Vault
    references.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
    # Single source of truth: a full connection string, always. Local dev
    # points it at your host/system Postgres; production points it at
    # whatever managed Postgres is in play. Async driver is
    # asyncpg — scheme must be `postgresql+asyncpg://`. Encode SSL directly
    # in the URL query string where needed, e.g. `?ssl=require` for Azure
    # Postgres Flexible Server.
    DATABASE_URL: PostgresDsn

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
    LOG_JSON: bool = False  # forced True in production, see below

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
        return str(self.DATABASE_URL)

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
        return self.LOG_JSON or self.is_production


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Depend on this, not on Settings() directly,
    so the whole app shares one instance and env files are parsed once.
    """
    return Settings()


settings = get_settings()
