"""Coverage API integration tests (Phase 7A).

Drives POST /analyses/{id}/coverage through a real upload → analysis run:
schema validation, path matching (exact, prefix, unmatched), per-symbol
covered/partial/uncovered/unknown classification, coverage_summary and the
risk coverage factor on the impact endpoint, graph node coverage status,
re-attachment semantics, and the error envelope (401/404/409/400).
"""

from tests.integration.test_graph_api import GRAPH_HEADERS
from tests.integration.test_graph_api import upload_graph_project as upload
from tests.integration.test_impact_api import graph_node_ids

COVERAGE_PAYLOAD = {
    "meta": {"format": 3, "version": "7.6.1"},
    "files": {
        "app/service.py": {
            "executed_lines": [2, 6],
            "missing_lines": [10],
            "excluded_lines": [],
            "summary": {"covered_lines": 2, "missing_lines": 1},
        },
        "app/main.py": {
            "executed_lines": [4],
            "missing_lines": [5],
            "excluded_lines": [],
            "summary": {},
        },
    },
    "totals": {"covered_lines": 3, "num_statements": 5},
}


def post_coverage(client, analysis_id, payload):
    return client.post(
        f"/api/v1/analyses/{analysis_id}/coverage",
        json=payload,
        headers=GRAPH_HEADERS,
    )


def node_detail(auth_client, analysis_id, node_id):
    response = auth_client.get(
        f"/api/v1/analyses/{analysis_id}/nodes/{node_id}", headers=GRAPH_HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_coverage_requires_auth(client):
    response = client.post(
        "/api/v1/analyses/whatever/coverage", json=COVERAGE_PAYLOAD
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_coverage_analysis_not_found(auth_client):
    response = post_coverage(auth_client, "nonexistent", COVERAGE_PAYLOAD)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_coverage_not_ready(auth_client, session_factory):
    from app.models.projects import AnalysisRun

    analysis = upload(auth_client)
    session = session_factory()
    try:
        run = session.get(AnalysisRun, analysis["id"])
        run.state = "running"
        session.commit()
    finally:
        session.close()
    response = post_coverage(auth_client, analysis["id"], COVERAGE_PAYLOAD)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


def test_coverage_rejects_malformed_payloads(auth_client):
    analysis = upload(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/coverage"
    bad_payloads = [
        "not-an-object",
        {"meta": {}},
        {"files": "nope"},
        {"files": {}},
        {"files": {"app/service.py": {"executed_lines": "all", "missing_lines": []}}},
        {"files": {"app/service.py": {"executed_lines": [1], "missing_lines": [None]}}},
        {"files": {"x.py": {"missing_lines": [1]}}, "totals": "bad"},
    ]
    for payload in bad_payloads:
        response = post_coverage(auth_client, analysis["id"], payload)
        assert response.status_code == 400, payload
        assert response.json()["error"]["code"] == "COVERAGE_INVALID", payload
    not_json = auth_client.post(
        base,
        content="this is not json",
        headers={**GRAPH_HEADERS, "Content-Type": "application/json"},
    )
    assert not_json.status_code == 400
    assert not_json.json()["error"]["code"] == "COVERAGE_INVALID"


def test_coverage_attaches_and_classifies_symbols(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])

    response = post_coverage(auth_client, analysis["id"], COVERAGE_PAYLOAD)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["analysis_id"] == analysis["id"]
    assert payload["unmatched_file_count"] == 0
    assert payload["warnings"] == []
    summary = payload["summary"]

    # Node detail exposes conservative coverage status per symbol (never zero):
    # helper fully executed; Service.run missed its only executable line;
    # main mixes executed and missing lines; uses_helper has no coverage data.
    coverage = {
        name: node_detail(auth_client, analysis["id"], node_id)["coverage_status"]
        for name, node_id in ids.items()
    }
    assert coverage["app.service:helper"] == "covered"
    assert coverage["app.service:Base.ping"] == "covered"
    assert coverage["app.service:Service.run"] == "uncovered"
    assert coverage["app.main:main"] == "partially_covered"
    assert coverage["app.extra:uses_helper"] == "unknown"
    assert summary["covered"] >= 2
    assert summary["partially_covered"] >= 1
    assert summary["uncovered"] >= 1
    assert summary["unknown"] >= 1
    total = sum(summary.values())
    assert total >= analysis["symbol_count"] - summary["unknown"]
    del ids


def test_coverage_unmatched_files_reported(auth_client):
    analysis = upload(auth_client)
    payload = {
        "files": {
            "not/in/snapshot.py": {"executed_lines": [1], "missing_lines": []},
            "app/service.py": {"executed_lines": [2], "missing_lines": []},
        }
    }
    response = post_coverage(auth_client, analysis["id"], payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unmatched_file_count"] == 1
    assert any("not/in/snapshot.py" in warning for warning in body["warnings"])


def test_coverage_replaces_previous_attachment(auth_client):
    analysis = upload(auth_client)
    assert post_coverage(auth_client, analysis["id"], COVERAGE_PAYLOAD).status_code == 200
    replacement = {
        "files": {
            "app/service.py": {
                "executed_lines": [],
                "missing_lines": [2],
                "excluded_lines": [],
            }
        }
    }
    response = post_coverage(auth_client, analysis["id"], replacement)
    assert response.status_code == 200
    ids = graph_node_ids(auth_client, analysis["id"])
    # helper's only executable line is now missing → uncovered, not stale.
    assert node_detail(auth_client, analysis["id"], ids["app.service:Service.run"])[
        "coverage_status"
    ] == "unknown"
    assert node_detail(auth_client, analysis["id"], ids["app.service:helper"])[
        "coverage_status"
    ] == "uncovered"
    assert node_detail(auth_client, analysis["id"], ids["app.main:main"])[
        "coverage_status"
    ] == "unknown"


def test_coverage_uncovered_symbols_reported(auth_client):
    analysis = upload(auth_client)
    payload = {
        "files": {
            "app/extra.py": {"executed_lines": [], "missing_lines": [4], "excluded_lines": []}
        }
    }
    response = post_coverage(auth_client, analysis["id"], payload)
    assert response.status_code == 200
    ids = graph_node_ids(auth_client, analysis["id"])
    assert node_detail(auth_client, analysis["id"], ids["app.extra:uses_helper"])[
        "coverage_status"
    ] == "uncovered"


def test_impact_attaches_coverage_summary_and_risk_factor(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]

    before = auth_client.post(
        f"/api/v1/analyses/{analysis['id']}/impact",
        json={"target_ids": [helper_id], "direction": "both", "max_depth": 3},
        headers=GRAPH_HEADERS,
    )
    assert before.status_code == 200
    assert before.json()["coverage_summary"] is None
    assert before.json()["risk"]["coverage_included"] is False

    assert post_coverage(auth_client, analysis["id"], COVERAGE_PAYLOAD).status_code == 200

    after = auth_client.post(
        f"/api/v1/analyses/{analysis['id']}/impact",
        json={"target_ids": [helper_id], "direction": "both", "max_depth": 3},
        headers=GRAPH_HEADERS,
    )
    assert after.status_code == 200
    payload = after.json()
    assert payload["coverage_summary"]["covered"] >= 1
    assert payload["risk"]["coverage_included"] is True
    factors = {factor["key"]: factor for factor in payload["risk"]["factors"]}
    assert factors["coverage_deficiency"]["included"] is True
    # helper is fully covered by the attached artifact → deficiency 0.
    assert factors["coverage_deficiency"]["normalized_value"] == 0.0
