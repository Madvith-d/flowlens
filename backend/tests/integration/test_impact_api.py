"""Impact API integration tests (Phase 6A).

Drives POST /analyses/{id}/impact through real upload → analysis runs:
direction semantics (upstream/downstream/both), direct vs indirect, hop
distances, per-target attribution and multi-target deduplication, valid
representative paths, max depth, IMPACT_MAX_IMPACTED_NODES truncation, the
risk breakdown (factors, renormalization without coverage, caveats),
determinism, plus the whole error-envelope matrix (401/404/409/400) and
ownership isolation.
"""

from tests.conftest import SESSION_COOKIE, TEST_ORIGIN
from tests.integration.test_graph_api import GRAPH_HEADERS, GRAPH_PROJECT_FILES
from tests.integration.test_graph_api import upload_graph_project as upload


def impact_fixture(auth_client, **overrides):
    analysis = upload(auth_client)
    return analysis, impact(auth_client, analysis["id"], **overrides)


def impact(client, analysis_id, target_ids, direction="both", max_depth=3):
    return client.post(
        f"/api/v1/analyses/{analysis_id}/impact",
        json={"target_ids": target_ids, "direction": direction, "max_depth": max_depth},
        headers=GRAPH_HEADERS,
    )


def node_id_by_qname(graph_payload, qualified_name):
    return next(node["id"] for node in graph_payload["nodes"] if node["qualified_name"] == qualified_name)


def graph_of(auth_client, analysis_id):
    response = auth_client.get(f"/api/v1/analyses/{analysis_id}/graph", headers=GRAPH_HEADERS)
    assert response.status_code == 200
    return response.json()


def test_impact_requires_auth(client):
    response = client.post("/api/v1/analyses/whatever/impact", json={"target_ids": ["x"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_impact_analysis_not_found(auth_client):
    response = impact(auth_client, "nonexistent", ["x"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_impact_target_not_found(auth_client):
    analysis = upload(auth_client)
    response = impact(auth_client, analysis["id"], ["does-not-exist"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["details"]["missing_target_ids"] == ["does-not-exist"]


def test_impact_request_validation(auth_client):
    analysis = upload(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/impact"

    def post(body):
        return auth_client.post(base, json=body, headers=GRAPH_HEADERS)

    assert post({"target_ids": [], "direction": "both"}).status_code == 400
    assert post({"target_ids": [f"t{i}" for i in range(11)]}).status_code == 400
    assert post({"target_ids": ["x"], "direction": "sideways"}).status_code == 400
    assert post({"target_ids": ["x"], "max_depth": 11}).status_code == 400
    assert post({"target_ids": ["x"], "max_depth": 0}).status_code == 400
    assert auth_client.post(base, headers=GRAPH_HEADERS).status_code == 400
    for bad in ({"target_ids": None}, {}):
        response = auth_client.post(base, json=bad, headers=GRAPH_HEADERS)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_impact_not_ready(auth_client, session_factory):
    analysis = upload(auth_client)
    from app.models.projects import AnalysisRun

    session = session_factory()
    try:
        run = session.get(AnalysisRun, analysis["id"])
        run.state = "running"
        session.flush()
        session.commit()
    finally:
        session.close()
    response = impact(auth_client, analysis["id"], ["whatever"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


def graph_node_ids(auth_client, analysis_id):
    graph = graph_of(auth_client, analysis_id)
    return {node["qualified_name"]: node["id"] for node in graph["nodes"]}


def test_impact_upstream_callers(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]
    response = impact(auth_client, analysis["id"], [helper_id], direction="upstream")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["direction"] == "upstream"
    impacted = {item["qualified_name"]: item for item in payload["impacted"]}
    # Direct callers of helper().
    assert impacted["app.main:main"]["direct"] is True
    assert impacted["app.main:main"]["min_hops"] == 1
    assert impacted["app.extra:uses_helper"]["direct"] is True
    assert impacted["app.extra:uses_helper"]["min_hops"] == 1
    assert all(item["attributed_to"] == [helper_id] for item in payload["impacted"])
    assert payload["truncated"] is False


def test_impact_downstream_dependencies(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    service_id = ids["app.service:Service"]
    # Class symbols carry no method edges (methods own their own calls):
    # Service's only stored dependency is Base (INHERITS).
    response = impact(auth_client, analysis["id"], [service_id], direction="downstream", max_depth=3)
    assert response.status_code == 200
    payload = response.json()
    impacted = {item["qualified_name"]: item for item in payload["impacted"]}
    assert impacted["app.service:Base"]["direct"] is True
    assert impacted["app.service:Base"]["min_hops"] == 1
    # Methods work at symbol level: Service.run → Base.ping (CALLS, direct).
    run_id = ids["app.service:Service.run"]
    run_payload = impact(auth_client, analysis["id"], [run_id], direction="downstream")
    assert run_payload.status_code == 200
    run_impacted = {item["qualified_name"]: item for item in run_payload.json()["impacted"]}
    assert run_impacted["app.service:Base.ping"]["direct"] is True
    assert run_impacted["app.service:Base.ping"]["min_hops"] == 1


def test_impact_paths_are_valid_edge_sequences(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    base_id = ids["app.service:Base"]
    # Upstream of Base: Service (INHERITS, 1 hop) and main (main → Service,
    # CALLS + Service →Base INHERITS = 2 hops).
    response = impact(auth_client, analysis["id"], [base_id], direction="upstream", max_depth=3)
    assert response.status_code == 200
    payload = response.json()
    impacted = {item["qualified_name"]: item for item in payload["impacted"]}
    assert impacted["app.service:Service"]["min_hops"] == 1
    main_impact = impacted["app.main:main"]
    assert main_impact["min_hops"] == 2
    assert main_impact["direct"] is False
    assert main_impact["paths"], "indirect nodes carry representative paths"
    graph = graph_of(auth_client, analysis["id"])
    edge_by_id = {edge["id"]: edge for edge in graph["edges"]}
    for path in main_impact["paths"]:
        assert path["edges"]
        # Upstream paths are ordered impacted → target (valid edge sequence).
        chain = ["app.main:main"]
        for edge_id in path["edges"]:
            edge = edge_by_id.get(edge_id)
            assert edge is not None, f"unknown edge id {edge_id}"
            assert edge["kind"] != "CONTAINS", "CONTAINS is never traversed"
            assert edge["source"] == ids[chain[-1]], "path is an ordered edge sequence"
            chain.append(next(q for q, nid in ids.items() if nid == edge["target"]))
        assert chain[-1] == "app.service:Base", "path ends at the target"


def test_impact_max_depth_bounds_traversal(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    base_id = ids["app.service:Base"]
    shallow = impact(auth_client, analysis["id"], [base_id], direction="upstream", max_depth=1)
    names = {item["qualified_name"] for item in shallow.json()["impacted"]}
    assert "app.service:Service" in names  # 1 hop
    assert "app.main:main" not in names  # 2 hops, capped out


def test_impact_multi_target_deduplication(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]
    base_id = ids["app.service:Base"]
    response = impact(auth_client, analysis["id"], [helper_id, base_id, helper_id], direction="both")
    assert response.status_code == 200
    payload = response.json()
    # Duplicated request target IDs collapse in the targets list.
    assert len(payload["targets"]) == 2
    nodes = {item["qualified_name"] for item in payload["impacted"]}
    assert nodes  # some impact exists
    # No node (and no target) appears twice.
    seen = [item["qualified_name"] for item in payload["impacted"]]
    assert len(seen) == len(set(seen))
    assert not (nodes & {"app.service:helper", "app.service:Base"})
    main_impact = next(item for item in payload["impacted"] if item["qualified_name"] == "app.main:main")
    # main is a direct caller of helper and an indirect dependent of Base.
    assert main_impact["min_hops"] == 1
    assert set(main_impact["attributed_to"]) == {helper_id, base_id}


def test_impact_truncation_reported(auth_client, settings):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]
    settings.impact_max_impacted_nodes = 1
    try:
        response = impact(auth_client, analysis["id"], [helper_id], direction="both")
    finally:
        settings.impact_max_impacted_nodes = 500
    payload = response.json()
    assert payload["truncated"] is True
    assert len(payload["impacted"]) == 1
    assert any("truncated" in warning.lower() for warning in payload["warnings"])


def test_impact_risk_payload(auth_client, settings):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    helper_id = ids["app.service:helper"]
    payload = impact(
        auth_client, analysis["id"], [helper_id], direction="both", max_depth=3
    ).json()
    risk = payload["risk"]
    assert 0 <= risk["score"] <= 100
    assert risk["version"] == settings.risk_score_version
    assert risk["coverage_included"] is False  # coverage is Phase 7A
    factor_keys = {factor["key"] for factor in risk["factors"]}
    assert factor_keys == {
        "upstream_reachable_dependents",
        "in_degree_centrality",
        "downstream_breadth",
        "public_entry_point",
        "coverage_deficiency",
    }
    included = [factor for factor in risk["factors"] if factor["included"]]
    assert abs(sum(factor["weight"] for factor in included) - 1.0) < 0.001
    excluded = {factor["key"] for factor in risk["factors"] if not factor["included"]}
    assert excluded == {"coverage_deficiency"}
    caveats = " ".join(risk["caveats"])
    assert "NOT a probability of failure" in caveats
    assert "coverage" in caveats  # discloses the exclusion
    # Honest factor values: helper has ≥2 direct dependents in this fixture?
    upstream = next(f for f in risk["factors"] if f["key"] == "upstream_reachable_dependents")
    assert upstream["raw_value"] >= 0


def test_impact_unresolved_warning(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    # The fixture has unresolved references (e.g. `service.run(...)`, json).
    payload = impact(auth_client, analysis["id"], [ids["app.service:helper"]]).json()
    assert any("unresolved" in warning.lower() for warning in payload["warnings"])


def test_impact_deterministic(auth_client):
    analysis = upload(auth_client)
    ids = graph_node_ids(auth_client, analysis["id"])
    base_id = ids["app.service:Base"]
    first = impact(auth_client, analysis["id"], [base_id], direction="both", max_depth=5)
    second = impact(auth_client, analysis["id"], [base_id], direction="both", max_depth=5)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_impact_ownership_isolated(auth_client):
    analysis = upload(auth_client)
    # Sign in a second, different user via the mocked provider.
    from urllib.parse import parse_qs, urlparse

    response = auth_client.get("/api/v1/auth/github/start")
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    callback = auth_client.get(
        "/api/v1/auth/github/callback",
        params={"code": "user-two", "state": state},
        headers={"Origin": TEST_ORIGIN},
    )
    assert callback.status_code == 302
    auth_client.cookies.set(SESSION_COOKIE, callback.cookies.get(SESSION_COOKIE), domain="testserver")
    response = impact(auth_client, analysis["id"], ["whatever"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
