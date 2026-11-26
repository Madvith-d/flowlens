"""Typed application settings loaded from environment variables.

Secrets are never logged; values marked in `.env.example` only.
"""

from functools import lru_cache

from pydantic import Field, field_validator
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
    # Installation/archive side (github.com only; no GHES support in the MVP).
    github_app_id: int = 0
    github_app_slug: str = ""
    # PEM private key of the GitHub App (server-only secret, never logged).
    github_app_private_key: str = ""
    github_archive_base_url: str = "https://codeload.github.com"

    # --- Database / storage ---
    database_url: str = "sqlite:///./flowlens.db"
    storage_root: str = "./storage"
    # Ingestion resource limits (applied to GitHub archives; reused for ZIP
    # uploads in a later phase).
    snapshot_max_file_count: int = 20_000
    snapshot_max_uncompressed_bytes: int = 256 * 1024 * 1024
    snapshot_max_archive_bytes: int = 200 * 1024 * 1024
    snapshot_download_timeout_seconds: float = 60.0
    # Per-file limits (ZIP entries and Python source files considered for parsing).
    snapshot_max_file_bytes: int = 5 * 1024 * 1024
    # Reject archives whose uncompressed:compressed ratio exceeds this (zip bombs).
    snapshot_max_compression_ratio: int = 200
    # Static analysis bounds (kept deterministic and bounded; never execute code).
    analysis_max_symbols: int = 100_000
    analysis_max_calls_per_symbol: int = 2_000
    # Resolver bounds (Phase 5A): evidence kept per deduplicated edge, rows kept
    # for unresolved/ambiguous references (occurrence counters stay exact), and
    # an overall dependency-edge budget per analysis run.
    analysis_max_evidence_per_edge: int = 10
    analysis_max_reference_diagnostics: int = 1_000
    analysis_max_edges: int = 200_000
    # Graph query bounds: reachability metrics are only computed while the
    # dependency graph stays within this node budget; responses cap edges.
    graph_metrics_max_nodes: int = 10_000
    graph_max_edges_per_response: int = 5_000
    # Impact traversal bounds (Phase 6A): per-request target count and depth
    # follow the contract (1-10); the impacted list has its own bound.
    impact_max_impacted_nodes: int = 500
    # Versioned risk-score heuristic (Phase 6A). Weights are renormalized over
    # the included factors; the score is a prioritization heuristic, not a
    # failure probability.
    risk_score_version: str = "1"
    risk_weight_upstream_dependents: float = 0.35
    risk_weight_in_degree: float = 0.20
    risk_weight_downstream_breadth: float = 0.15
    risk_weight_public_entry: float = 0.15
    risk_weight_coverage_deficiency: float = 0.15
    # Reachability sizes are normalized against this cap (bounded in [0, 1]).
    risk_normalization_cap: int = 100
    # Diff/coverage/report bounds (Phase 7A): request size and file-count
    # budgets stay bounded; impact depth over mapped diff symbols follows the
    # same contract constraints as the impact endpoint.
    diff_max_files: int = 200
    diff_max_bytes: int = 512 * 1024
    diff_impact_max_depth: int = 3
    coverage_max_files: int = 10_000

    # --- Versions recorded on analysis runs ---
    flowlens_version: str = "0.1.0"
    graph_schema_version: str = "1"

    @field_validator("github_app_private_key", mode="before")
    @classmethod
    def _normalize_private_key(cls, value: object) -> object:
        """Accept PEM keys with real or escaped newlines, as documented.

        Secrets stores and single-line `.env` entries commonly carry the PEM
        with literal `\n` sequences; without this, `load_pem_private_key`
        fails and every installation-token call reports the app as not
        configured. Empty values pass through untouched.
        """
        if not isinstance(value, str) or not value.strip():
            return value
        normalized = value.strip().replace("\\r\\n", "\\n").replace("\\n", "\n").strip()
        return normalized

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

    @property
    def github_install_callback_url(self) -> str:
        return f"{self.backend_public_url}/api/v1/github/install/callback"

    def _host_of(self, url: str) -> str:
        from urllib.parse import urlparse

        return urlparse(url).hostname or ""

    @property
    def github_api_host(self) -> str:
        return self._host_of(self.github_api_base_url)

    @property
    def github_archive_host(self) -> str:
        return self._host_of(self.github_archive_base_url)

    @property
    def github_allowed_hosts(self) -> set[str]:
        """Strict SSRF allowlist: only documented GitHub API/archive hosts."""
        hosts = {self.github_api_host, self.github_archive_host, self._host_of(self.github_oauth_base_url)}
        return {host for host in hosts if host}


def get_settings() -> Settings:
    """Cached settings accessor (overridable in tests)."""
    return Settings()  # pragma: no cover - thin wrapper for cacheability


@lru_cache
def cached_settings() -> Settings:
    return get_settings()
