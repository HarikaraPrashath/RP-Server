from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "RP-Server API")
    app_env: str = os.getenv("APP_ENV", "dev")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/rp_server",
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_ttl_minutes: int = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "30"))
    refresh_token_ttl_days: int = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "14"))
    reset_token_ttl_minutes: int = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))
    cors_origins: list[str] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()
    )
    debug_password_reset_tokens: bool = os.getenv("DEBUG_PASSWORD_RESET_TOKENS", "1") in ("1", "true", "True")
    use_db_compat_storage: bool = os.getenv("USE_DB_COMPAT_STORAGE", "1") in ("1", "true", "True")
    jobs_refresh_background_default: bool = os.getenv("JOBS_REFRESH_BACKGROUND_DEFAULT", "0") in ("1", "true", "True")
    crawler_min_interval_seconds: int = int(os.getenv("CRAWLER_MIN_INTERVAL_SECONDS", "20"))


settings = Settings()
