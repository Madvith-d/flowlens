"""ZIP upload + static analysis integration tests (Phase 4A).

Covers: safe upload ingestion, analysis lifecycle, symbol catalogue search and
pagination, diagnostics, ownership isolation, and parity between the ZIP and
GitHub source providers (same internal snapshot representation).
"""

import io
import zipfile

from tests.conftest import (
    OWNED_INSTALLATION,
    SAMPLE_PROJECT_FILES,
    TEST_ORIGIN,
    build_zip,
)

UPLOAD_HEADERS = {"Origin": TEST_ORIGIN}


def upload(client, files=None, name=None):
    body = build_zip(files if files is not None else SAMPLE_PROJECT_FILES)
    data = {"name": name} if name else {}
    return client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("sample.zip", body, "application/zip")},
        data=data,
        headers=UPLOAD_HEADERS,
    )


def upload_and_analyze(client):
    project = upload(client).json()
    snapshot_id = project["latest_snapshot"]["id"]
    analysis = client.post(
        f"/api/v1/snapshots/{snapshot_id}/analyses", headers=UPLOAD_HEADERS
    )
    assert analysis.status_code == 202, analysis.text
    return project, analysis.json()


# ------------------------------------------------------------------- uploads
def test_upload_requires_auth(client):
    body = build_zip(SAMPLE_PROJECT_FILES)
    response = client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("sample.zip", body, "application/zip")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_upload_creates_project_and_snapshot(auth_client, settings):
    response = upload(auth_client, name="Demo Project")
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["name"] == "Demo Project"
    assert project["source_provider"] == "upload"
    assert project["github_connection"] is None
    snapshot = project["latest_snapshot"]
    assert snapshot["provider"] == "upload"
    assert snapshot["github_provenance"] is None
    # Excluded paths are not counted; .git/config and README are skipped/kept per rules.
    assert snapshot["file_count"] == 6  # 5 python-ish files + README, minus .git
    assert snapshot["content_hash"]
    snapshot_dir = settings.storage_root + "/snapshots/" + snapshot["id"]
    import pathlib

    root = pathlib.Path(snapshot_dir)
    assert (root / "app" / "main.py").is_file()
    assert not (root / ".git").exists()


def test_upload_rejects_non_zip(auth_client):
    response = auth_client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("notes.zip", b"this is not a zip file", "application/zip")},
        headers=UPLOAD_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_INVALID"
    assert auth_client.get("/api/v1/projects").json()["pagination"]["total"] == 0


def test_upload_rejects_traversal_archive(auth_client):
    response = upload(auth_client, files={"../evil.py": b"print('x')\n"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_INVALID"
    assert auth_client.get("/api/v1/projects").json()["pagination"]["total"] == 0


def test_upload_enforces_size_limit(auth_client, settings):
    # The route enforces the archive limit while streaming the upload, before
    # any ZIP validation, so plain oversized bytes trigger 413.
    settings.snapshot_max_archive_bytes = 1024
    try:
        response = auth_client.post(
            "/api/v1/projects/from-upload",
            files={"file": ("big.zip", b"x" * 4096, "application/zip")},
            headers=UPLOAD_HEADERS,
        )
    finally:
        settings.snapshot_max_archive_bytes = 200 * 1024 * 1024
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_upload_empty_archive_rejected(auth_client):
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, mode="w"):
        pass
    response = auth_client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("empty.zip", empty.getvalue(), "application/zip")},
        headers=UPLOAD_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UPLOAD_INVALID"


# ------------------------------------------------------------------ analyses
def test_analysis_requires_auth(client):
    response = client.post("/api/v1/snapshots/whatever/analyses")
    assert response.status_code == 401


def test_analysis_runs_and_populates_symbols(auth_client):
    _project, analysis = upload_and_analyze(auth_client)
    assert analysis["state"] == "completed_with_warnings"  # app/broken.py has a syntax error
    assert analysis["python_file_count"] == 5
    assert analysis["symbol_count"] > 0
    assert analysis["edge_count"] == 0  # graph edges are Phase 5A
    summary = analysis["diagnostics_summary"]
    assert summary["syntax_errors"] == 1
    assert summary["skipped_files"] == 0

    symbols = auth_client.get(f"/api/v1/analyses/{analysis['id']}/symbols").json()
    names = {item["qualified_name"] for item in symbols["items"]}
    assert "app.main:main" in names
    assert "app.service:Service.run" in names
    assert "app.service:Service.run.inner" in names
    assert "app.broken" not in names

    run_symbol = next(
        item for item in symbols["items"] if item["qualified_name"] == "app.service:Service.run"
    )
    assert run_symbol["kind"] == "method"
    assert run_symbol["location"]["start_line"] >= 1
    assert run_symbol["file_path"] == "app/service.py"
    assert run_symbol["parent_id"]


def test_analysis_status_endpoint(auth_client):
    _project, analysis = upload_and_analyze(auth_client)
    fetched = auth_client.get(f"/api/v1/analyses/{analysis['id']}").json()
    assert fetched["id"] == analysis["id"]
    assert fetched["state"] == analysis["state"]
    assert fetched["flowlens_version"]
    assert fetched["graph_schema_version"] == "1"
    assert fetched["started_at"] and fetched["finished_at"]
    assert fetched["error_code"] is None


def test_symbol_search_and_filters(auth_client):
    _project, analysis = upload_and_analyze(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/symbols"

    by_name = auth_client.get(base, params={"q": "Service"}).json()
    assert by_name["pagination"]["total"] >= 2
    assert all("service" in item["qualified_name"].lower() for item in by_name["items"])

    classes = auth_client.get(base, params={"kind": "class"}).json()
    assert classes["pagination"]["total"] >= 1
    assert all(item["kind"] == "class" for item in classes["items"])

    invalid_kind = auth_client.get(base, params={"kind": "interface"})
    assert invalid_kind.status_code == 400
    assert invalid_kind.json()["error"]["code"] == "VALIDATION_ERROR"


def test_symbol_pagination_is_deterministic(auth_client):
    _project, analysis = upload_and_analyze(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/symbols"
    page1 = auth_client.get(base, params={"page": 1, "per_page": 2}).json()
    page2 = auth_client.get(base, params={"page": 2, "per_page": 2}).json()
    assert page1["pagination"]["per_page"] == 2
    assert page1["pagination"]["total_pages"] >= 2
    ids_page1 = [item["id"] for item in page1["items"]]
    ids_page2 = [item["id"] for item in page2["items"]]
    assert not set(ids_page1) & set(ids_page2)
    repeat = auth_client.get(base, params={"page": 1, "per_page": 2}).json()
    assert [item["id"] for item in repeat["items"]] == ids_page1


def test_analysis_records_source_files(auth_client, session_factory):
    _project, analysis = upload_and_analyze(auth_client)
    from sqlalchemy import select

    from app.models.analysis import SourceFile

    session = session_factory()
    try:
        files = session.scalars(
            select(SourceFile).where(SourceFile.analysis_id == analysis["id"])
        ).all()
    finally:
        session.close()
    paths = {item.path for item in files}
    assert {"app/main.py", "app/service.py", "app/broken.py"} <= paths
    broken = next(item for item in files if item.path == "app/broken.py")
    assert broken.has_syntax_error is True
    good = next(item for item in files if item.path == "app/service.py")
    assert good.has_syntax_error is False
    assert len(good.sha256) == 64


def test_no_python_files_state(auth_client):
    project = upload(auth_client, files={"README.md": b"# docs only\n"}).json()
    analysis = auth_client.post(
        f"/api/v1/snapshots/{project['latest_snapshot']['id']}/analyses",
        headers=UPLOAD_HEADERS,
    ).json()
    assert analysis["state"] == "completed_with_warnings"
    assert analysis["symbol_count"] == 0
    assert analysis["python_file_count"] == 0


def test_project_view_exposes_latest_analysis(auth_client):
    project, analysis = upload_and_analyze(auth_client)
    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()
    assert detail["latest_analysis"]["id"] == analysis["id"]
    listing = auth_client.get("/api/v1/projects").json()
    assert listing["items"][0]["latest_analysis"]["state"] == analysis["state"]


# --------------------------------------------------- provider parity + access
def test_zip_and_github_sources_share_symbol_representation(auth_client):
    """Both providers produce the same internal snapshot → same symbol catalog."""
    github_project = auth_client.post(
        "/api/v1/projects/from-github",
        json={
            "repository_id": 1001,
            "installation_id": OWNED_INSTALLATION,
            "ref": "main",
        },
        headers=UPLOAD_HEADERS,
    ).json()

    # Same two Python files as the mocked GitHub tarball, uploaded as a ZIP.
    upload_project = upload(
        auth_client,
        files={
            "app/main.py": b"print('hello')\n",
            "pkg/utils.py": b"def helper():\n    return 1\n",
        },
    ).json()

    catalogs = []
    for snapshot in (github_project["latest_snapshot"], upload_project["latest_snapshot"]):
        analysis = auth_client.post(
            f"/api/v1/snapshots/{snapshot['id']}/analyses", headers=UPLOAD_HEADERS
        ).json()
        symbols = auth_client.get(
            f"/api/v1/analyses/{analysis['id']}/symbols", params={"per_page": 200}
        ).json()
        catalogs.append(
            sorted((item["qualified_name"], item["kind"]) for item in symbols["items"])
        )

    assert catalogs[0] == catalogs[1]
    assert ("app.main", "module") in catalogs[0]
    assert ("pkg.utils:helper", "function") in catalogs[0]


def test_analysis_ownership_isolated(app_client):
    """A second user cannot read or start analyses on another user's snapshot."""
    from tests.conftest import start_and_get_state

    state = start_and_get_state(app_client)
    first = app_client.get(
        "/api/v1/auth/github/callback", params={"code": "valid-code", "state": state}
    )
    app_client.cookies.set(
        "flowlens_session", first.cookies.get("flowlens_session"), domain="testserver"
    )
    project, analysis = upload_and_analyze(app_client)

    app_client.cookies.clear()
    state2 = start_and_get_state(app_client)
    second = app_client.get(
        "/api/v1/auth/github/callback", params={"code": "user-two", "state": state2}
    )
    app_client.cookies.set(
        "flowlens_session", second.cookies.get("flowlens_session"), domain="testserver"
    )

    assert app_client.get(f"/api/v1/analyses/{analysis['id']}").status_code == 404
    assert (
        app_client.get(f"/api/v1/analyses/{analysis['id']}/symbols").status_code == 404
    )
    start = app_client.post(
        f"/api/v1/snapshots/{project['latest_snapshot']['id']}/analyses",
        headers=UPLOAD_HEADERS,
    )
    assert start.status_code == 404
    assert start.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"


def test_unknown_snapshot_and_analysis_return_not_found(auth_client):
    missing_snapshot = auth_client.post(
        "/api/v1/snapshots/does-not-exist/analyses", headers=UPLOAD_HEADERS
    )
    assert missing_snapshot.status_code == 404
    assert missing_snapshot.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
    missing_analysis = auth_client.get("/api/v1/analyses/does-not-exist")
    assert missing_analysis.status_code == 404
    assert missing_analysis.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_uploaded_source_is_never_executed(auth_client, settings, tmp_path):
    marker = tmp_path / "executed.marker"
    files = {
        "app/evil.py": f"open({str(marker)!r}, 'w').write('pwned')\n".encode(),
        "app/main.py": b"def main():\n    return 1\n",
    }
    project = upload(auth_client, files=files).json()
    auth_client.post(
        f"/api/v1/snapshots/{project['latest_snapshot']['id']}/analyses",
        headers=UPLOAD_HEADERS,
    )
    assert not marker.exists()
