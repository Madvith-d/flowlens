"""Phase 8 hardening integration tests.

Covers the stabilization work that is not tied to one feature:
- unexpected analysis failures surface as `failed` runs (never stuck in
  `running`, never a 500 with internal details),
- the analysis wall-clock budget stops runaway parses with an explicit
  diagnostic,
- every response carries `X-Content-Type-Options: nosniff`,
- no server filesystem path leaks into any API response, including error
  envelopes.
"""

import pytest

from tests.conftest import SAMPLE_PROJECT_FILES, TEST_ORIGIN, build_zip

UPLOAD_HEADERS = {"Origin": TEST_ORIGIN}


def upload(auth_client):
    body = build_zip(SAMPLE_PROJECT_FILES)
    response = auth_client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("sample.zip", body, "application/zip")},
        headers=UPLOAD_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------- analysis failure containment
def test_unexpected_analysis_error_marks_run_failed(
    auth_client, monkeypatch, session_factory
):
    """An unexpected parser crash becomes a `failed` run, not a 500/limbo."""

    def boom(*args, **kwargs):
        raise RuntimeError("simulated internal failure /tmp/secret/path")

    monkeypatch.setattr(
        "app.services.analysis.service.parse_python_file", boom
    )
    project = upload(auth_client)
    snapshot_id = project["latest_snapshot"]["id"]
    response = auth_client.post(
        f"/api/v1/snapshots/{snapshot_id}/analyses", headers=UPLOAD_HEADERS
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "failed"
    assert body["error_code"] == "INTERNAL_ERROR"
    # The internal error text never reaches the client.
    assert "simulated internal failure" not in response.text

    # The failed state is persistent and queryable; the diagnostic row records
    # the stable code (the contract's diagnostics_summary stays unchanged).
    fetched = auth_client.get(
        f"/api/v1/analyses/{body['id']}", headers=UPLOAD_HEADERS
    )
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "failed"
    assert fetched.json()["error_code"] == "INTERNAL_ERROR"

    from sqlalchemy import select

    from app.models.analysis import AnalysisDiagnostic

    db = session_factory()
    codes = db.scalars(
        select(AnalysisDiagnostic.code).where(
            AnalysisDiagnostic.analysis_id == body["id"]
        )
    ).all()
    assert "INTERNAL_ERROR" in codes


def test_analysis_time_budget_stops_run_with_diagnostic(
    auth_client, settings, session_factory
):
    """A zero time budget stops parsing with an explicit diagnostic."""
    settings.analysis_max_wall_seconds = -1.0
    project = upload(auth_client)
    snapshot_id = project["latest_snapshot"]["id"]
    response = auth_client.post(
        f"/api/v1/snapshots/{snapshot_id}/analyses", headers=UPLOAD_HEADERS
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "completed_with_warnings"
    assert body["python_file_count"] == 0

    from sqlalchemy import select

    from app.models.analysis import AnalysisDiagnostic

    db = session_factory()
    codes = db.scalars(
        select(AnalysisDiagnostic.code).where(
            AnalysisDiagnostic.analysis_id == body["id"]
        )
    ).all()
    assert "ANALYSIS_TIME_BUDGET_EXCEEDED" in codes


# ----------------------------------------------------------- response hardening
def test_responses_carry_nosniff_header(auth_client):
    """Every response, success or error, sets X-Content-Type-Options."""
    urls = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/projects"),
        ("GET", "/api/v1/projects/does-not-exist"),
    ]
    for method, url in urls:
        response = auth_client.request(method, url, headers=UPLOAD_HEADERS)
        assert response.headers.get("x-content-type-options") == "nosniff", url


def test_error_responses_contain_no_server_paths(auth_client, settings):
    """Error envelopes never include server filesystem paths."""
    storage_root = settings.storage_root
    responses = [
        auth_client.get("/api/v1/projects/does-not-exist", headers=UPLOAD_HEADERS),
        auth_client.get(
            "/api/v1/analyses/does-not-exist", headers=UPLOAD_HEADERS
        ),
        auth_client.post(
            "/api/v1/projects",
            json={"name": ""},
            headers=UPLOAD_HEADERS,
        ),
        auth_client.post(
            "/api/v1/projects/from-upload",
            files={"file": ("x.zip", b"not a zip", "application/zip")},
            headers=UPLOAD_HEADERS,
        ),
    ]
    for response in responses:
        assert response.status_code >= 400
        assert storage_root not in response.text
        assert "Traceback" not in response.text
