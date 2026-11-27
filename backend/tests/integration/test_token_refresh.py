"""GitHub access-token refresh tests (Phase 8).

An expired stored access token is refreshed transparently with the stored
(encrypted) refresh token; a failed refresh surfaces the stable 401
GITHUB_TOKEN_ERROR envelope so the client prompts a new sign-in. Tokens are
never visible in any response.
"""

from datetime import datetime, timezone

from tests.conftest import (
    OWNED_INSTALLATION,
    SESSION_COOKIE,
    TEST_ORIGIN,
    start_and_get_state,
)
from app.core.security import decrypt_secret
from app.models.github import GitHubCredential

HEADERS = {"Origin": TEST_ORIGIN}


def sign_in(client, code: str):
    state = start_and_get_state(client)
    return client.get(
        "/api/v1/auth/github/callback",
        params={"code": code, "state": state},
        headers=HEADERS,
    )


def test_expired_access_token_is_refreshed(client, session_factory, settings) -> None:
    """Sign-in stores an already-expired token; the next GitHub call refreshes."""
    response = sign_in(client, "expired-creds")
    assert response.status_code == 302
    client.cookies.set(SESSION_COOKIE, response.cookies.get(SESSION_COOKIE), domain="testserver")

    listings = client.get("/api/v1/github/installations", headers=HEADERS)
    assert listings.status_code == 200, listings.text
    ids = [item["id"] for item in listings.json()["items"]]
    assert OWNED_INSTALLATION in ids

    # The rotated credential pair is stored encrypted with a fresh expiry.
    from app.db.base import ensure_aware

    db = session_factory()
    rows = db.query(GitHubCredential).all()
    assert len(rows) == 1
    stored = rows[0]
    assert decrypt_secret(stored.encrypted_access_token, settings) == "refreshed-access-token"
    assert decrypt_secret(stored.encrypted_refresh_token, settings) == "rotated-refresh-token"
    assert stored.expires_at is not None
    assert ensure_aware(stored.expires_at) > datetime.now(timezone.utc)


def test_refresh_failure_requires_reauth(client) -> None:
    """A stale refresh token yields the stable 401 envelope, not a 500."""
    response = sign_in(client, "expired-bad-refresh")
    assert response.status_code == 302
    client.cookies.set(SESSION_COOKIE, response.cookies.get(SESSION_COOKIE), domain="testserver")

    listings = client.get("/api/v1/github/installations", headers=HEADERS)
    assert listings.status_code == 401
    assert listings.json()["error"]["code"] == "GITHUB_TOKEN_ERROR"


def test_tokens_never_appear_in_refresh_flow_responses(client) -> None:
    """Neither the old, refreshed, nor rotated tokens leak into responses."""
    response = sign_in(client, "expired-creds")
    client.cookies.set(SESSION_COOKIE, response.cookies.get(SESSION_COOKIE), domain="testserver")

    listings = client.get("/api/v1/github/installations", headers=HEADERS)
    assert listings.status_code == 200
    body = listings.text
    for secret in (
        "test-access-token-abc123",
        "test-refresh-token-def456",
        "refreshed-access-token",
        "rotated-refresh-token",
    ):
        assert secret not in body
