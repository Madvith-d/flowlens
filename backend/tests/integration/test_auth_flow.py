"""Integration tests: GitHub auth flow end to end with a mocked provider.

Covers: valid callback, invalid/replayed state, token exchange failure,
expired session, logout, CSRF origin rejection, revoked credentials, and
the invariant that tokens never appear in cookies or API responses.
"""

from urllib.parse import parse_qs, urlparse

from app.core.security import decrypt_secret
from app.models.github import GitHubCredential
from app.models.user import User
from tests.conftest import (
    SESSION_COOKIE,
    TEST_ACCESS_TOKEN,
    TEST_ORIGIN,
    start_and_get_state,
)


def login(client) -> None:
    """Perform a full mocked sign-in; leaves the session cookie on `client`."""
    state = start_and_get_state(client)
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith(TEST_ORIGIN)
    assert SESSION_COOKIE in client.cookies


# ----------------------------------------------------------------- happy path
def test_valid_callback_creates_session_and_user(client, session_factory, settings) -> None:
    state = start_and_get_state(client)
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith(TEST_ORIGIN)
    assert "login_error" not in response.headers["location"]

    cookie_header = response.headers["set-cookie"]
    assert "httponly" in cookie_header.lower()
    assert SESSION_COOKIE in cookie_header

    # Session state visible to the client, credentials are not.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    payload = me.json()
    assert payload == {
        "authenticated": True,
        "user": {
            "id": payload["user"]["id"],
            "github_login": "octocat",
            "avatar_url": "https://avatars.example/octocat.png",
            "created_at": payload["user"]["created_at"],
        },
    }

    # Token stored encrypted at rest.
    db = session_factory()
    credential = db.query(GitHubCredential).one()
    assert credential.encrypted_access_token != TEST_ACCESS_TOKEN
    assert decrypt_secret(credential.encrypted_access_token, settings) == TEST_ACCESS_TOKEN
    user = db.query(User).one()
    assert user.github_id == 4242
    assert user.github_login == "octocat"


def test_user_upsert_by_github_id(client, session_factory) -> None:
    login(client)
    login(client)  # second sign-in same GitHub identity
    db = session_factory()
    assert db.query(User).count() == 1
    assert db.query(User).one().github_id == 4242


# ------------------------------------------------------------------- failures
def test_replayed_state_rejected(client) -> None:
    state = start_and_get_state(client)
    first = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
    )
    assert first.status_code == 302
    client.cookies.clear()

    state2 = start_and_get_state(client)
    replay = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state2},
    )
    assert replay.status_code == 302
    client.cookies.clear()

    # Also try literally the same state a second time via a fresh flow client.
    fresh = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state2},
    )
    assert fresh.status_code == 302
    assert "OAUTH_STATE_INVALID" in fresh.headers["location"]
    assert SESSION_COOKIE not in client.cookies


def test_unknown_state_rejected(client) -> None:
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": "forged-state-value"},
    )
    assert response.status_code == 302
    assert "OAUTH_STATE_INVALID" in response.headers["location"]
    assert SESSION_COOKIE not in client.cookies


def test_missing_code_or_state_rejected(client) -> None:
    response = client.get("/api/v1/auth/github/callback")
    assert response.status_code == 302
    assert "OAUTH_STATE_INVALID" in response.headers["location"]


def test_token_exchange_failure(client) -> None:
    state = start_and_get_state(client)
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "fail-exchange", "state": state},
    )
    assert response.status_code == 302
    assert "GITHUB_TOKEN_ERROR" in response.headers["location"]
    assert SESSION_COOKIE not in client.cookies


def test_no_github_client_id_configured(settings, session_factory, mock_provider) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(
        settings=settings.model_copy(update={"github_app_client_id": ""}),
        session_factory=session_factory,
        github_provider=mock_provider,
    )
    client = TestClient(app)
    response = client.get("/api/v1/auth/github/start")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GITHUB_APP_NOT_CONFIGURED"


# -------------------------------------------------------------------- session
def test_expired_session_reports_unauthenticated(client, session_factory) -> None:
    login(client)
    db = session_factory()
    from app.models.auth import UserSession

    record = db.query(UserSession).one()
    from datetime import datetime, timedelta, timezone

    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == {"authenticated": False, "user": None}


def test_tampered_cookie_rejected(client) -> None:
    login(client)
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, "forged-session-id.deadbeef")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is False


# --------------------------------------------------------------------- logout
def test_logout_revokes_session(client) -> None:
    login(client)
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 204
    me = client.get("/api/v1/auth/me")
    assert me.json()["authenticated"] is False


def test_logout_without_session_401(client) -> None:
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


# ------------------------------------------------------------------------ CSRF
def test_unsafe_request_with_disallowed_origin_rejected(client) -> None:
    login(client)
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_ORIGIN_REJECTED"
    # Session untouched.
    assert client.get("/api/v1/auth/me").json()["authenticated"] is True


# ------------------------------------------------------------ revoked GitHub auth
def test_revoked_authorization_prevents_new_exchange(client, session_factory) -> None:
    login(client)
    client.cookies.clear()
    db = session_factory()
    from app.repositories.github import GitHubCredentialRepository

    GitHubCredentialRepository(db).revoke(db.query(User).one().id)
    db.commit()

    # A user re-signing-in with a compromised/revoked grant fails at exchange.
    state = start_and_get_state(client)
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "revoked-authorization", "state": state},
    )
    assert response.status_code == 302
    assert "GITHUB_TOKEN_ERROR" in response.headers["location"]


# ---------------------------------------------------------------- invariants
def test_no_token_in_responses_or_cookies(client) -> None:
    state = start_and_get_state(client)
    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
    )
    body = response.text
    cookie_header = response.headers.get("set-cookie", "")
    assert TEST_ACCESS_TOKEN not in body
    assert "access_token" not in body
    assert TEST_ACCESS_TOKEN not in cookie_header

    me = client.get("/api/v1/auth/me")
    assert TEST_ACCESS_TOKEN not in me.text
    assert "token" not in me.text.lower()


def test_state_only_accepted_from_start_endpoint(client) -> None:
    # A state generated by the server is required; the authorize redirect must
    # carry the state, and consumers cannot predict it.
    response = client.get("/api/v1/auth/github/start")
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["test-client-id"]
    assert len(query["state"][0]) >= 32
