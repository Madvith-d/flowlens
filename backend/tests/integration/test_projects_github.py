"""GitHub project import / refresh / disconnect tests (mocked GitHub API)."""

from tests.conftest import OWNED_INSTALLATION, TEST_ORIGIN

IMPORT_BODY = {
    "repository_id": 1001,
    "installation_id": OWNED_INSTALLATION,
    "ref": "main",
}


def _import_project(auth_client, **overrides):
    body = {**IMPORT_BODY, **overrides}
    return auth_client.post(
        "/api/v1/projects/from-github",
        json=body,
        headers={"Origin": TEST_ORIGIN},
    )


# ------------------------------------------------------------------ auth
def test_all_project_routes_require_auth(client):
    cases = [
        ("get", "/api/v1/projects", None),
        ("get", "/api/v1/projects/pid", None),
        ("get", "/api/v1/projects/pid/snapshots", None),
        ("post", "/api/v1/projects/from-github", {}),
        ("post", "/api/v1/projects/pid/refresh", {}),
        ("delete", "/api/v1/projects/pid/github-connection", None),
    ]
    for method, url, body in cases:
        if body is None:
            response = getattr(client, method)(url)
        else:
            response = getattr(client, method)(url, json=body)
        assert response.status_code in (401, 422), (method, url, response.status_code)


# -------------------------------------------------------------- import flow
def test_import_creates_project_and_snapshot(auth_client, settings):
    response = _import_project(auth_client)
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["id"]
    assert project["name"] == "octocat/hello-world"
    connection = project["github_connection"]
    assert connection["repository_id"] == 1001
    assert connection["installation_id"] == OWNED_INSTALLATION
    assert connection["ref"] == "main"
    # Snapshot provenance: resolved commit SHA recorded, immutable.
    snapshot = project["latest_snapshot"]
    assert snapshot["github_provenance"]["commit_sha"].startswith("sha-main")
    assert snapshot["file_count"] == 2  # .git/config is excluded
    assert snapshot["content_hash"]
    # Files are on disk under the storage root, not in any served dir.
    snapshot_dir = __import__("pathlib").Path(settings.storage_root) / "snapshots" / snapshot["id"]
    assert (snapshot_dir / "app" / "main.py").is_file()
    # Contract: no GitHub tokens anywhere in the response.
    assert "token" not in response.text.lower()


def test_import_denies_repository_outside_installation(auth_client):
    response = _import_project(auth_client, repository_id=9999)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REPOSITORY_ACCESS_DENIED"


def test_import_denies_foreign_installation(auth_client):
    response = _import_project(auth_client, installation_id=8888)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REPOSITORY_ACCESS_DENIED"


def test_import_invalid_ref(auth_client):
    response = _import_project(auth_client, ref="does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_import_archive_failure_is_clean(auth_client):
    """`broken-branch` resolves but its archive download fails; no partial
    project row may survive the failed import."""
    response = _import_project(auth_client, ref="broken-branch")
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "GITHUB_API_ERROR"
    # No project row leaks to the dashboard after a failed import.
    assert auth_client.get("/api/v1/projects").json()["pagination"]["total"] == 0


def test_import_validates_request(auth_client):
    response = auth_client.post(
        "/api/v1/projects/from-github",
        json={"repository_id": 1001, "installation_id": OWNED_INSTALLATION},
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------ refresh
def test_refresh_creates_new_immutable_snapshot(auth_client):
    project = _import_project(auth_client).json()
    first_snapshot = project["latest_snapshot"]

    refresh = auth_client.post(
        f"/api/v1/projects/{project['id']}/refresh",
        json={},
        headers={"Origin": TEST_ORIGIN},
    )
    assert refresh.status_code == 201, refresh.text
    new_snapshot = refresh.json()
    assert new_snapshot["id"] != first_snapshot["id"]
    assert new_snapshot["github_provenance"]["commit_sha"] == first_snapshot["github_provenance"]["commit_sha"]

    snapshots = auth_client.get(f"/api/v1/projects/{project['id']}/snapshots").json()
    assert len(snapshots["items"]) == 2
    assert new_snapshot["id"] in {item["id"] for item in snapshots["items"]}
    assert first_snapshot["id"] in {item["id"] for item in snapshots["items"]}


def test_refresh_with_new_ref_updates_connection(auth_client):
    project = _import_project(auth_client).json()
    refresh = auth_client.post(
        f"/api/v1/projects/{project['id']}/refresh",
        json={"ref": "v1.0.0"},
        headers={"Origin": TEST_ORIGIN},
    )
    assert refresh.status_code == 201
    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()
    assert detail["github_connection"]["ref"] == "v1.0.0"


def test_refresh_denied_after_disconnect(auth_client):
    project = _import_project(auth_client).json()
    auth_client.delete(
        f"/api/v1/projects/{project['id']}/github-connection",
        headers={"Origin": TEST_ORIGIN},
    )
    refresh = auth_client.post(
        f"/api/v1/projects/{project['id']}/refresh", json={}, headers={"Origin": TEST_ORIGIN}
    )
    assert refresh.status_code == 409


# --------------------------------------------------------------- disconnect
def test_disconnect_keeps_snapshots(auth_client):
    project = _import_project(auth_client).json()
    snapshot_id = project["latest_snapshot"]["id"]

    response = auth_client.delete(
        f"/api/v1/projects/{project['id']}/github-connection",
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 204

    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()
    assert detail["github_connection"] is None
    snapshots = auth_client.get(f"/api/v1/projects/{project['id']}/snapshots").json()
    assert [item["id"] for item in snapshots["items"]] == [snapshot_id]


# ------------------------------------------------------- listing + ownership
def test_empty_dashboard_then_project_list(auth_client):
    empty = auth_client.get("/api/v1/projects").json()
    assert empty["items"] == []
    assert empty["pagination"]["total"] == 0
    project = _import_project(auth_client).json()
    listing = auth_client.get("/api/v1/projects").json()
    assert listing["pagination"]["total"] == 1
    assert listing["items"][0]["id"] == project["id"]
    assert listing["items"][0]["latest_snapshot"]["id"] == project["latest_snapshot"]["id"]


def test_project_ownership_isolated(app_client):
    """A second signed-in user cannot see or mutate the first user's project."""
    from tests.conftest import start_and_get_state

    # First user signs in and imports a project.
    state = start_and_get_state(app_client)
    first = app_client.get(
        "/api/v1/auth/github/callback", params={"code": "valid-code", "state": state}
    )
    app_client.cookies.set(
        "flowlens_session", first.cookies.get("flowlens_session"), domain="testserver"
    )
    project = app_client.post(
        "/api/v1/projects/from-github",
        json=IMPORT_BODY,
        headers={"Origin": TEST_ORIGIN},
    ).json()

    # Second user (different GitHub identity) signs in.
    app_client.cookies.clear()
    state2 = start_and_get_state(app_client)
    second = app_client.get(
        "/api/v1/auth/github/callback", params={"code": "user-two", "state": state2}
    )
    app_client.cookies.set(
        "flowlens_session", second.cookies.get("flowlens_session"), domain="testserver"
    )

    me = app_client.get("/api/v1/auth/me").json()["user"]["github_login"]
    assert me == "codetwo"

    detail = app_client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    snapshots = app_client.get(f"/api/v1/projects/{project['id']}/snapshots")
    assert snapshots.status_code == 404
    refresh = app_client.post(
        f"/api/v1/projects/{project['id']}/refresh",
        json={},
        headers={"Origin": TEST_ORIGIN},
    )
    assert refresh.status_code == 404
    disconnect = app_client.delete(
        f"/api/v1/projects/{project['id']}/github-connection",
        headers={"Origin": TEST_ORIGIN},
    )
    assert disconnect.status_code == 404
    # And the second user's dashboard is empty.
    assert app_client.get("/api/v1/projects").json()["pagination"]["total"] == 0
