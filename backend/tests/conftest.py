"""Shared test fixtures: in-memory SQLite, test settings, mocked providers."""

import io
import tarfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models)
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.services.github.app_client import (
    ARCHIVE_DOWNLOAD_FAILED,
    INSTALLATION_ACCESS_DENIED,
    REF_NOT_FOUND,
    REPOSITORY_ACCESS_DENIED,
    GitHubAppClient,
    InstallationInfo,
    InstallationToken,
    RepositoryInfo,
    RepositoriesPage,
    ResolvedRef,
)
from app.services.github.client import (
    GitHubOAuthProvider,
    GitHubUserInfo,
    TokenExchangeResult,
)

TEST_ORIGIN = "http://localhost:3000"
SESSION_COOKIE = "flowlens_session"
TEST_ACCESS_TOKEN = "test-access-token-abc123"
TEST_REFRESH_TOKEN = "test-refresh-token-def456"

OWNED_INSTALLATION = 5001
FOREIGN_INSTALLATION = 6002
EXPIRED_TOKEN_INSTALLATION = 5999

EXPIRED_INSTALLATION_TOKEN = "expired-installation-token"


def build_repo_tarball(files: dict[str, bytes] | None = None) -> bytes:
    """In-memory tar.gz fixture: safe archive with two Python files."""
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        payload = files or {
            "app/main.py": b"print('hello')\n",
            "pkg/utils.py": b"def helper():\n    return 1\n",
            ".git/config": b"should be excluded\n",
        }
        for name, data in payload.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 1_700_000_000
            tar.addfile(info, io.BytesIO(data))
    return archive.getvalue()


def _installation(installation_id: int, login: str, kind: str) -> InstallationInfo:
    return InstallationInfo(
        installation_id=installation_id,
        account_login=login,
        account_type=kind,
        avatar_url=None,
    )


class MockGitHubAppClient(GitHubAppClient):
    """Scripted installation-side GitHub client (no network access).

    Owns: installation 5001 (user octocat) with repositories 1001 (public)
    and 1002 (private). Installation 6002 exists but is not accessible to the
    user. Installation 5999 issues tokens that GitHub treats as expired.
    """

    def __init__(self, total_repositories: int = 2) -> None:
        self.total_repositories = total_repositories
        self.repositories = {
            1001: RepositoryInfo(
                repository_id=1001,
                full_name="octocat/hello-world",
                owner="octocat",
                visibility="public",
                default_branch="main",
                description="Sample repo",
            ),
            1002: RepositoryInfo(
                repository_id=1002,
                full_name="octocat/secret-project",
                owner="octocat",
                visibility="private",
                default_branch="main",
                description=None,
            ),
        }

    # ------------------------------------------------------------ tokens
    def build_installation_token(
        self, installation_id: int, repository_ids: list[int] | None = None
    ) -> InstallationToken:
        if installation_id == EXPIRED_TOKEN_INSTALLATION:
            return InstallationToken(
                token=EXPIRED_INSTALLATION_TOKEN,
                expires_at=datetime.now(timezone.utc).timestamp() - 60,
            )
        return InstallationToken(
            token=f"installation-token-{installation_id}",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
        )

    # ------------------------------------------------------- installations
    def list_user_installations(self, user_access_token: str) -> list[InstallationInfo]:
        if user_access_token != TEST_ACCESS_TOKEN:
            # Second mock user has not installed the FlowLens GitHub App.
            return []
        return [
            _installation(OWNED_INSTALLATION, "octocat", "user"),
            _installation(EXPIRED_TOKEN_INSTALLATION, "expired-app", "user"),
        ]

    def list_installation_repositories(
        self, installation_token: str, page: int, per_page: int
    ) -> RepositoriesPage:
        if installation_token == EXPIRED_INSTALLATION_TOKEN:
            raise INSTALLATION_ACCESS_DENIED
        if not installation_token.startswith(f"installation-token-{OWNED_INSTALLATION}"):
            raise INSTALLATION_ACCESS_DENIED
        items = list(self.repositories.values())
        start = (page - 1) * per_page
        return RepositoriesPage(
            items=items[start : start + per_page],
            total=self.total_repositories,
        )

    # -------------------------------------------------- repository access
    def get_repository(self, installation_token: str, repository_id: int) -> RepositoryInfo:
        if installation_token == EXPIRED_INSTALLATION_TOKEN:
            raise INSTALLATION_ACCESS_DENIED
        if installation_token == f"installation-token-{OWNED_INSTALLATION}" and repository_id in self.repositories:
            return self.repositories[repository_id]
        raise REPOSITORY_ACCESS_DENIED

    def resolve_ref(self, installation_token: str, full_name: str, ref: str) -> ResolvedRef:
        if installation_token == EXPIRED_INSTALLATION_TOKEN:
            raise INSTALLATION_ACCESS_DENIED
        if ref == "broken-branch":
            # Resolves fine, but the archive download for this ref fails.
            return ResolvedRef(ref=ref, commit_sha="sha-broken".ljust(40, "0"))
        if ref in {"main", "v1.0.0", "deadbeef1234567890abcdef1234567890abcdef"}:
            return ResolvedRef(ref=ref, commit_sha=f"sha-{ref}"[:40].ljust(40, "0"))
        raise REF_NOT_FOUND

    def download_archive(self, installation_token: str, full_name: str, ref: str) -> bytes:
        if installation_token == EXPIRED_INSTALLATION_TOKEN:
            raise ARCHIVE_DOWNLOAD_FAILED
        if ref.startswith("sha-broken"):
            raise ARCHIVE_DOWNLOAD_FAILED
        return build_repo_tarball()


class MockGitHubProvider(GitHubOAuthProvider):
    """Scripted provider: raises on specially marked codes/tokens.

    The code `user-two` signs in a *different* GitHub identity, which lets
    ownership-isolation tests run against two distinct accounts.
    """

    SECOND_USER = GitHubUserInfo(
        github_id=5151,
        login="codetwo",
        avatar_url="https://avatars.example/codetwo.png",
    )
    SECOND_USER_TOKEN = "test-access-token-user-two"

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
        access_token = (
            self.SECOND_USER_TOKEN if code == "user-two" else TEST_ACCESS_TOKEN
        )
        return TokenExchangeResult(
            access_token=access_token,
            refresh_token=TEST_REFRESH_TOKEN,
            expires_in=3600,
            scopes="read:user",
        )

    def get_user(self, access_token: str) -> GitHubUserInfo:
        if access_token == self.SECOND_USER_TOKEN:
            return self.SECOND_USER
        if access_token in {"revoked", TEST_ACCESS_TOKEN + "-invalid"}:
            from app.services.github.client import USER_FETCH_FAILED

            raise USER_FETCH_FAILED
        return self.github_user


@pytest.fixture
def settings(tmp_path) -> Settings:
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
        github_app_id=1234,
        github_app_slug="flowlens-test-app",
        github_app_private_key="test-private-key-not-used-by-mocks",
        storage_root=str(tmp_path / "storage"),
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
def mock_app_client() -> MockGitHubAppClient:
    return MockGitHubAppClient()


@pytest.fixture
def client(settings, session_factory, mock_provider) -> TestClient:
    app = create_app(
        settings=settings,
        session_factory=session_factory,
        github_provider=mock_provider,
        github_app_client=MockGitHubAppClient(),
    )
    # Redirects target external origins (github.com / the frontend); following
    # them inside TestClient would re-route them into the ASGI app.
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def app_client(settings, session_factory, mock_provider, mock_app_client) -> TestClient:
    """TestClient with the fully wired mocked GitHub App client."""
    app = create_app(
        settings=settings,
        session_factory=session_factory,
        github_provider=mock_provider,
        github_app_client=mock_app_client,
    )
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def auth_client(app_client) -> TestClient:
    """Authenticated session via the (mocked) GitHub OAuth flow."""
    state = start_and_get_state(app_client)
    response = app_client.get(
        "/api/v1/auth/github/callback",
        params={"code": "ok-code", "state": state},
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 302
    session_cookie = response.cookies.get(SESSION_COOKIE)
    assert session_cookie
    app_client.cookies.set(SESSION_COOKIE, session_cookie, domain="testserver")
    return app_client


def start_and_get_state(client: TestClient) -> str:
    response = client.get("/api/v1/auth/github/start")
    assert response.status_code == 302
    from urllib.parse import parse_qs, urlparse

    location = response.headers["location"]
    assert "github.com/login/oauth/authorize" in location
    return parse_qs(urlparse(location).query)["state"][0]


def captured_install_state(client: TestClient) -> str:
    """Authenticated install-start state for installation callback tests."""
    response = client.get("/api/v1/github/install/start")
    assert response.status_code == 302
    from urllib.parse import parse_qs, urlparse

    location = response.headers["location"]
    assert "github.com/apps/flowlens-test-app/installations/new" in location
    return parse_qs(urlparse(location).query)["state"][0]
