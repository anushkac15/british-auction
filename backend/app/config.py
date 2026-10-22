from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://auction:auction@localhost:5432/auction"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    sweep_interval_seconds: int = 30
    # Tolerated clock skew when checking that a new RFQ starts in the future.
    start_time_grace_seconds: int = 10
    sse_enabled: bool = True

    # Signs login tokens. Override in any shared or deployed environment.
    secret_key: str = "dev-only-insecure-secret-change-me"
    token_ttl_minutes: int = 12 * 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
