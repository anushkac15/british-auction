from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "production" turns on the startup safety checks and hides the interactive API docs.
    app_env: str = "development"

    database_url: str = "postgresql+psycopg://auction:auction@localhost:5432/auction"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    sweep_interval_seconds: int = 30
    # Tolerated clock skew when checking that a new RFQ starts in the future.
    start_time_grace_seconds: int = 10
    sse_enabled: bool = True

    # Signs login tokens. Override in any shared or deployed environment.
    secret_key: str = DEV_SECRET_KEY
    token_ttl_minutes: int = 12 * 60

    # Failed logins allowed per email within the window before further attempts are refused.
    login_max_failures: int = 5
    login_lockout_seconds: int = 15 * 60
    # "redis" shares the failure count between API processes; "memory" keeps it per process.
    login_throttle_store: Literal["memory", "redis"] = "memory"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        # Managed databases usually hand out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.is_production and (self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32):
            raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters when APP_ENV=production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
