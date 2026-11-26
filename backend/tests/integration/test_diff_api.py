"""Diff API integration tests (Phase 7A).

Drives POST /analyses/{id}/diff through a real upload → analysis run: line-range
mapping, added/modified/deleted/unmapped classification, module-level changes,
deleted files, path mismatches, combined impact with per-target attribution,
and the error-envelope matrix (401/404/409/400/422).
"""

from tests.conftest import TEST_ORIGIN
from tests.integration.test_graph_api import GRAPH_HEADERS
from tests.integration.test_graph_api import upload_graph_project as upload
from tests.integration.test_impact_api import graph_node_ids

HELPER_DIFF = "\n".join(
    [
        "--- a/app/service.py",
        "+++ b/app/service.py",
        "@@ -1,3 +1,3 @@",
        " def helper(value):",
        "-    return value",
        "+    return value + 1",
        " ",
    ]
)

MODULE_LEVEL_DIFF = "\n".join(
    [
        "diff --git a/app/main.py b/app/main.py",
        "index 111..222 100644",
        "--- a/app/main.py",
        "+++ b/app/main.py",
        "@@ -1,3 +1,4 @@",
        "+import os",
        " from app.service import Service, helper as help_fn",
        " ",
        " def main(argv=None):",
    ]
)

DELETED_FILE_DIFF = "\n".join(
    [
        "diff --git a/app/extra.py b/app/extra.py",
        "deleted file mode 100644",
        "index 111..000",
        "--- a/app/extra.py",
        "+++ /dev/null",
        "@@ -1,4 +0,0 @@",
        "-from app import service as svc",
        "-",
        "-def uses_helper():",
        "-    return svc.helper(2)",
    ]
)

UNMATCHED_PATH_DIFF = "\n".join(
    [
        "--- a/nowhere/unknown.py",
        "+++ b/nowhere/unknown.py",
        "@@ -3,2 +3,2 @@",
        " context",
        "-old = 1",
        "+new = 2",
    ]
)


def post_diff(client, analysis_id, text):
    return client.post(
        f"/api/v1/analyses/{analysis_id}/diff",
        json={"unified_diff": text},
        headers=GRAPH_HEADERS,
    )


def test_diff_requires_auth(client):
    response = client.post(
        "/api/v1/analyses/whatever/diff", json={"unified_diff": HELPER_DIFF}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_diff_analysis_not_found(auth_client):
    response = post_diff(auth_client, "nonexistent", HELPER_DIFF)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_diff_not_ready(auth_client, session_factory):
    from app.models.projects import AnalysisRun

    analysis = upload(auth_client)
    session = session_factory()
    try:
        run = session.get(AnalysisRun, analysis["id"])
        run.state = "running"
        session.commit()
    finally:
        session.close()
    response = post_diff(auth_client, analysis["id"], HELPER_DIFF)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


def test_diff_rejects_empty_and_malformed(auth_client):
    analysis = upload(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/diff"

    assert auth_client.post(base, json={"unified_diff": ""}, headers=GRAPH_HEADERS).status_code == 400
    assert auth_client.post(base, headers=GRAPH_HEADERS).status_code == 400
    for bad in ("hello world", "not a diff", "@@ -1 +1 @@\n+orphan"):
        response = post_diff(auth_client, analysis["id"], bad)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DIFF_INVALID"


def test_diff_maps_changed_lines_to_symbols(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]

    response = post_diff(auth_client, analysis["id"], HELPER_DIFF)
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["analysis_id"] == analysis["id"]
    assert len(payload["files"]) == 1
    diff_file = payload["files"][0]
    assert diff_file["path"] == "app/service.py"
    assert diff_file["change_type"] == "modified"
    assert diff_file["changed_line_count"] == 2
    assert diff_file["unmapped_line_count"] == 0
    assert diff_file["mapped_symbols"] == [
        {
            "symbol_id": helper_id,
            "qualified_name": "app.service:helper",
            "change_type": "modified",
        }
    ]

    combined = payload["combined_impact"]
    assert [target["node_id"] for target in combined["targets"]] == [helper_id]
    impacted = {item["qualified_name"]: item for item in combined["impacted"]}
    assert impacted["app.main:main"]["direct"] is True
    assert impacted["app.extra:uses_helper"]["direct"] is True
    assert all(
        item["attributed_to"] == [helper_id] for item in combined["impacted"]
    )
    assert combined["coverage_summary"] is None


def test_diff_reports_module_level_change_as_unmapped(auth_client):
    analysis = upload(auth_client)
    response = post_diff(auth_client, analysis["id"], MODULE_LEVEL_DIFF)
    assert response.status_code == 200, response.text
    diff_file = response.json()["files"][0]
    assert diff_file["change_type"] == "modified"
    assert diff_file["changed_line_count"] == 1
    assert diff_file["mapped_symbols"] == []
    assert diff_file["unmapped_line_count"] == 1
    assert "module-level" in diff_file["unmapped_reason"]
    combined = response.json()["combined_impact"]
    assert combined["targets"] == []
    assert combined["impacted"] == []
    assert any("No changed lines mapped" in warning for warning in response.json()["warnings"])


def test_diff_marks_symbols_in_deleted_file(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    uses_helper_id = ids["app.extra:uses_helper"]

    response = post_diff(auth_client, analysis["id"], DELETED_FILE_DIFF)
    assert response.status_code == 200, response.text
    payload = response.json()
    diff_file = payload["files"][0]
    assert diff_file["path"] == "app/extra.py"
    assert diff_file["change_type"] == "deleted"
    assert diff_file["changed_line_count"] == 4
    mapped = {(item["symbol_id"], item["change_type"]) for item in diff_file["mapped_symbols"]}
    assert (uses_helper_id, "deleted") in mapped
    assert {item["symbol_id"] for item in diff_file["mapped_symbols"]} == {uses_helper_id}


def test_diff_path_mismatch_stays_unmapped(auth_client):
    analysis = upload(auth_client)
    response = post_diff(auth_client, analysis["id"], UNMATCHED_PATH_DIFF)
    assert response.status_code == 200, response.text
    diff_file = response.json()["files"][0]
    assert diff_file["path"] == "nowhere/unknown.py"
    assert diff_file["mapped_symbols"] == []
    assert diff_file["unmapped_line_count"] == 2
    assert "not found" in diff_file["unmapped_reason"]
    assert any("does not exist" in warning for warning in response.json()["warnings"])


def test_diff_multiple_files_and_determinism(auth_client):
    analysis = upload(auth_client)
    multi = "\n".join(
        HELPER_DIFF.splitlines()
        + ["diff --git a/nowhere/unknown.py b/nowhere/unknown.py"]
        + UNMATCHED_PATH_DIFF.splitlines()
    )
    first = post_diff(auth_client, analysis["id"], multi)
    second = post_diff(auth_client, analysis["id"], multi)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    paths = [item["path"] for item in first.json()["files"]]
    assert set(paths) == {"app/service.py", "nowhere/unknown.py"}


def test_diff_requires_same_owner(auth_client, client, session_factory):
    from tests.conftest import SESSION_COOKIE

    analysis = upload(auth_client)
    other = client  # a separate, unauthenticated app instance sees 401
    response = other.post(
        f"/api/v1/analyses/{analysis['id']}/diff",
        json={"unified_diff": HELPER_DIFF},
        headers={"Origin": TEST_ORIGIN},
    )
    assert response.status_code == 401
    assert SESSION_COOKIE not in other.cookies
