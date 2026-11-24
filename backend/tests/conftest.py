"""Shared test fixtures: in-memory SQLite, test settings, mocked provider."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models)
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.services.github.client import (
    GitHubOAuthProvider,
    GitHubUserInfo,
    TokenExchangeResult,
)

TEST_ORIGIN = "http://localhost:3000"
SESSION_COOKIE = "flowlens_session"
TEST_ACCESS_TOKEN = "test-access-token-abc123"
TEST_REFRESH_TOKEN = "test-refresh-token-def456"


class MockGitHubProvider(GitHubOAuthProvider):
    """Scripted provider: raises on specially marked codes/tokens."""

    def __init__(self) -> None:
        self.github_user = GitHubUserInfo(
            github_id=4242,
            login="octocat",
            avatar_url="https://avatars.example/octocat.png",
        )

    def exchange_code(self, code: str) -> TokenExchangeResult:
        if code in {"fail-exchange", "revoked-authorization"}:
            from app.services.github.client import TOKEN_EXCHANGE_FAILED

            raise TOKEN_EXCHANGE_FAILED
        return TokenExchangeResult(
            access_token=TEST_ACCESS_TOKEN,
            refresh_token=TEST_REFRESH_TOKEN,
            expires_in=3600,
            scopes="read:user",
        )

    def get_user(self, access_token: str) -> GitHubUserInfo:
        if access_token in {"revoked", TEST_ACCESS_TOKEN + "-invalid"}:
            from app.services.github.client import USER_FETCH_FAILED

            raise USER_FETCH_FAILED
        return self.github_user


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="development",
        backend_public_url="http://localhost:8000",
        frontend_origin=TEST_ORIGIN,
        cors_allowed_origins=TEST_ORIGIN,
        session_signing_secret="test-signing-secret",
        token_encryption_key="test-encryption-key",
        session_ttl_seconds=3600,
        oauth_state_ttl_seconds=600,
        database_url="sqlite:///:memory:",
        github_app_client_id="test-client-id",
        github_app_client_secret="test-client-secret",
    )


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def mock_provider() -> MockGitHubProvider:
    return MockGitHubProvider()


@pytest.fixture
def client(settings, session_factory, mock_provider) -> TestClient:
    app = create_app(
        settings=settings,
        session_factory=session_factory,
        github_provider=mock_provider,
    )
    # Redirects target external origins (github.com / the frontend); following
    # them inside TestClient would re-route them into the ASGI app.
    return TestClient(app, follow_redirects=False)


def start_and_get_state(client: TestClient) -> str:
    response = client.get("/api/v1/auth/github/start")
    assert response.status_code == 302
    from urllib.parse import parse_qs, urlparse

    location = response.headers["location"]
    assert "github.com/login/oauth/authorize" in location
    return parse_qs(urlparse(location).query)["state"][0]
