"""Typed application settings loaded from environment variables.

Secrets are never logged; values marked in `.env.example` only.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_env: str = "development"
    backend_public_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:3000"
    # Comma-separated list of allowed CORS origins for browser requests.
    cors_allowed_origins: str = "http://localhost:3000"

    # --- Session / crypto ---
    session_signing_secret: str = "insecure-dev-only-change-me"
    token_encryption_key: str = "insecure-dev-only-change-me"
    session_ttl_seconds: int = 7 * 24 * 3600
    oauth_state_ttl_seconds: int = 600
    session_cookie_name: str = "flowlens_session"

    # --- GitHub App OAuth (user authorization) ---
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    github_oauth_base_url: str = "https://github.com"
    github_api_base_url: str = "https://api.github.com"

    # --- Database / storage ---
    database_url: str = "sqlite:///./flowlens.db"
    storage_root: str = "./storage"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        return [origin for origin in origins if origin]

    @property
    def session_cookie_secure(self) -> bool:
        # Secure cookies only over HTTPS in production.
        return self.is_production

    @property
    def github_oauth_callback_url(self) -> str:
        return f"{self.backend_public_url}/api/v1/auth/github/callback"


def get_settings() -> Settings:
    """Cached settings accessor (overridable in tests)."""
    return Settings()  # pragma: no cover - thin wrapper for cacheability


@lru_cache
def cached_settings() -> Settings:
    return get_settings()
