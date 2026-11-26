"""Reports API integration tests (Phase 7A).

Drives POST /analyses/{id}/reports and GET /reports/{id}/download through a
real upload → analysis run: report metadata, deterministic Markdown matching
stored impact data, escaping, coverage sections, and the error envelope
(401/404/409).
"""

from tests.integration.test_graph_api import GRAPH_HEADERS
from tests.integration.test_graph_api import upload_graph_project as upload
from tests.integration.test_impact_api import graph_node_ids
from tests.integration.test_coverage_api import COVERAGE_PAYLOAD, post_coverage
from tests.conftest import SAMPLE_PROJECT_FILES, build_zip


def generate(client, analysis_id, body=None):
    return client.post(
        f"/api/v1/analyses/{analysis_id}/reports",
        json=body or {},
        headers=GRAPH_HEADERS,
    )


def download(client, report_id):
    return client.get(f"/api/v1/reports/{report_id}/download", headers=GRAPH_HEADERS)


def impact_payload(auth_client, analysis_id, target_id):
    response = auth_client.post(
        f"/api/v1/analyses/{analysis_id}/impact",
        json={"target_ids": [target_id], "direction": "both", "max_depth": 3},
        headers=GRAPH_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reports_require_auth(client):
    response = client.post("/api/v1/analyses/whatever/reports", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert client.get("/api/v1/reports/whatever/download").status_code == 401


def test_report_analysis_not_found(auth_client):
    response = generate(auth_client, "nonexistent")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_report_download_not_found(auth_client):
    response = download(auth_client, "nonexistent")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_report_not_ready(auth_client, session_factory):
    from app.models.projects import AnalysisRun

    analysis = upload(auth_client)
    session = session_factory()
    try:
        run = session.get(AnalysisRun, analysis["id"])
        run.state = "running"
        session.commit()
    finally:
        session.close()
    response = generate(auth_client, analysis["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


def test_report_metadata_and_download(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])

    response = generate(
        auth_client,
        analysis["id"],
        {"target_ids": [ids["app.service:helper"]], "direction": "both", "max_depth": 3},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "analysis_id", "format", "created_at", "filename"}
    assert body["analysis_id"] == analysis["id"]
    assert body["format"] == "markdown"
    assert body["filename"] == f"flowlens-report-{analysis['id']}.md"

    file = download(auth_client, body["id"])
    assert file.status_code == 200
    assert file.headers["content-type"].startswith("text/markdown")
    assert file.headers["content-disposition"] == f'attachment; filename="{body["filename"]}"'
    markdown = file.text
    assert markdown.startswith("# FlowLens Impact Report")
    for section in (
        "## Metadata",
        "## Targets",
        "## Impacted nodes",
        "## Risk score",
        "## Coverage",
        "## Diagnostics summary",
        "## Exclusions and limitations",
    ):
        assert section in markdown


def test_report_matches_impact_data(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]
    impact = impact_payload(auth_client, analysis["id"], helper_id)

    response = generate(
        auth_client, analysis["id"], {"target_ids": [helper_id], "max_depth": 3}
    )
    assert response.status_code == 201
    markdown = download(auth_client, response.json()["id"]).text

    # Deterministic: same inputs → same document.
    second = download(auth_client, generate(auth_client, analysis["id"], {"target_ids": [helper_id]}).json()["id"]).text
    assert markdown == second
    # The report reproduces the stored impact/risk data exactly.
    assert "app.service:helper" in markdown
    for node in impact["impacted"]:
        assert node["qualified_name"] in markdown
    risk = impact["risk"]
    assert f"{risk['score']}/100" in markdown
    for factor in risk["factors"]:
        assert factor["label"] in markdown
    for caveat in risk["caveats"]:
        assert caveat in markdown


def test_report_defaults_targets_deterministically(auth_client):
    analysis = upload(auth_client)
    first = generate(auth_client, analysis["id"])
    assert first.status_code == 201, first.text
    second = generate(auth_client, analysis["id"])
    assert second.status_code == 201
    assert download(auth_client, first.json()["id"]).text == download(
        auth_client, second.json()["id"]
    ).text


def test_report_escapes_markdown_hazards(auth_client):
    body = build_zip(SAMPLE_PROJECT_FILES)
    created = auth_client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("esc.zip", body, "application/zip")},
        data={"name": "Pipe | Backslash \\ Project"},
        headers=GRAPH_HEADERS,
    )
    assert created.status_code == 201, created.text
    snapshot_id = created.json()["latest_snapshot"]["id"]
    analysis = auth_client.post(
        f"/api/v1/snapshots/{snapshot_id}/analyses", headers=GRAPH_HEADERS
    ).json()

    response = generate(auth_client, analysis["id"])
    assert response.status_code == 201, response.text
    markdown = download(auth_client, response.json()["id"]).text
    # Pipe in the project name is escaped so the metadata table stays intact.
    assert r"Pipe \| Backslash \\ Project" in markdown
    assert "Pipe | Backslash" not in markdown


def test_report_includes_coverage_when_attached(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])

    before = generate(auth_client, analysis["id"], {"target_ids": [ids["app.service:helper"]]})
    assert before.status_code == 201
    without = download(auth_client, before.json()["id"]).text
    assert "_No Coverage.py artifact is attached" in without

    assert post_coverage(auth_client, analysis["id"], COVERAGE_PAYLOAD).status_code == 200
    after = generate(auth_client, analysis["id"], {"target_ids": [ids["app.service:helper"]]})
    assert after.status_code == 201
    with_coverage = download(auth_client, after.json()["id"]).text
    assert "| covered |" in with_coverage
    assert "| partially_covered |" in with_coverage
    assert "app.service:helper" in with_coverage
    assert "missing coverage is never reported as zero" in with_coverage


def test_report_rejects_other_owner_and_ready_only(auth_client, client):
    analysis = upload(auth_client)
    anonymous = client.post(
        f"/api/v1/analyses/{analysis['id']}/reports", json={}, headers=GRAPH_HEADERS
    )
    assert anonymous.status_code == 401
