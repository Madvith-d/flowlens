"""Installation-flow and repository-listing tests (mocked GitHub API)."""

from tests.conftest import (
    OWNED_INSTALLATION,
    TEST_ORIGIN,
    captured_install_state,
)


# ------------------------------------------------------------- install start
def test_install_start_requires_auth(client):
    response = client.get("/api/v1/github/install/start")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_install_start_redirects_with_state(auth_client):
    response = auth_client.get("/api/v1/github/install/start")
    assert response.status_code == 302
    location = response.headers["location"]
    assert "github.com/apps/flowlens-test-app/installations/new" in location
    assert "state=" in location


# ---------------------------------------------------------- install callback
def test_install_callback_requires_auth(client):
    response = client.get(
        "/api/v1/github/install/callback", params={"installation_id": 5001, "state": "s"}
    )
    assert response.status_code == 401


def test_install_callback_missing_params_redirects_with_error(auth_client):
    response = auth_client.get("/api/v1/github/install/callback")
    assert response.status_code == 302
    assert "install_error=INSTALLATION_NOT_FOUND" in response.headers["location"]


def test_install_callback_rejects_replayed_state(auth_client):
    state = captured_install_state(auth_client)
    location = auth_client.get(
        "/api/v1/github/install/callback",
        params={"installation_id": OWNED_INSTALLATION, "state": state},
    ).headers["location"]
    assert "installed_account=octocat" in location
    # Replay: state is one-time; the second attempt is rejected.
    replay = auth_client.get(
        "/api/v1/github/install/callback",
        params={"installation_id": OWNED_INSTALLATION, "state": state},
    )
    assert "install_error=OAUTH_STATE_INVALID" in replay.headers["location"]


def test_install_callback_unverifiable_installation_denied(auth_client):
    state = captured_install_state(auth_client)
    response = auth_client.get(
        "/api/v1/github/install/callback",
        params={"installation_id": 8888, "state": state},
    )
    assert response.status_code == 302
    assert "install_error=REPOSITORY_ACCESS_DENIED" in response.headers["location"]


# ------------------------------------------------------------ installations
def test_list_installations_returns_verified_items(auth_client):
    response = auth_client.get("/api/v1/github/installations")
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["id"] for item in items} == {OWNED_INSTALLATION, 5999}
    assert all(item["account_login"] == "octocat" or item["account_login"] == "expired-app" for item in items)
    body = items[0]
    assert set(body) >= {"id", "account_login", "account_type", "avatar_url"}


def test_list_installations_requires_auth(client):
    response = client.get("/api/v1/github/installations")
    assert response.status_code == 401


# -------------------------------------------------------------- repositories
def test_repository_pagination(auth_client):
    page1 = auth_client.get(
        f"/api/v1/github/installations/{OWNED_INSTALLATION}/repositories",
        params={"page": 1, "per_page": 1},
    )
    assert page1.status_code == 200
    body = page1.json()
    assert len(body["items"]) == 1
    assert body["pagination"] == {"page": 1, "per_page": 1, "total": 2, "total_pages": 2}
    page2 = auth_client.get(
        f"/api/v1/github/installations/{OWNED_INSTALLATION}/repositories",
        params={"page": 2, "per_page": 1},
    )
    ids = [item["id"] for item in body["items"]] + [
        item["id"] for item in page2.json()["items"]
    ]
    assert set(ids) == {1001, 1002}


def test_repositories_include_summary_fields(auth_client):
    response = auth_client.get(
        f"/api/v1/github/installations/{OWNED_INSTALLATION}/repositories"
    )
    repo = response.json()["items"][0]
    assert repo["full_name"] == "octocat/hello-world"
    assert repo["visibility"] in ("public", "private")
    assert repo["default_branch"] == "main"
    assert repo["html_url"] == "https://github.com/octocat/hello-world"
    # Visibility is display metadata only; no access token material anywhere.
    assert not any("token" in key for key in str(repo))


def test_repositories_for_inaccessible_installation_forbidden(auth_client):
    response = auth_client.get(
        f"/api/v1/github/installations/8888/repositories"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REPOSITORY_ACCESS_DENIED"


def test_repositories_with_expired_installation_token(auth_client):
    response = auth_client.get(
        f"/api/v1/github/installations/5999/repositories"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REPOSITORY_ACCESS_DENIED"
