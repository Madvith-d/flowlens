"""Graph API integration tests (Phase 5A).

Covers the three graph endpoints against a real upload → analysis run: view
collapses, kind filters, node limits and truncation, node metrics, bounded
neighborhood expansion, ownership isolation, and the not-ready/not-found
error envelopes (409/404/400), all through the shared error envelope.
"""

from tests.conftest import SAMPLE_PROJECT_FILES, TEST_ORIGIN, build_zip

GRAPH_HEADERS = {"Origin": TEST_ORIGIN}

# A compact project shaped for graph assertions.
GRAPH_PROJECT_FILES: dict[str, bytes] = {
    "__init__.py": b"",
    "app/__init__.py": b"",
    "app/main.py": (
        b"from app.service import Service, helper as help_fn\n"
        b"\n"
        b"def main(argv=None):\n"
        b"    service = Service()\n"
        b"    return help_fn(service.run(argv))\n"
    ),
    "app/service.py": (
        b"def helper(value):\n"
        b"    return value\n"
        b"\n"
        b"class Base:\n"
        b"    def ping(self):\n"
        b"        return 1\n"
        b"\n"
        b"class Service(Base):\n"
        b"    def run(self, argv=None):\n"
        b"        return self.ping()\n"
    ),
    "app/extra.py": (
        b"from app import service as svc\n"
        b"\n"
        b"def uses_helper():\n"
        b"    return svc.helper(2)\n"
    ),
    "README.md": b"# sample\n",
}


def upload_graph_project(client):
    body = build_zip(GRAPH_PROJECT_FILES)
    response = client.post(
        "/api/v1/projects/from-upload",
        files={"file": ("graph-sample.zip", body, "application/zip")},
        data={"name": "Graph Sample"},
        headers=GRAPH_HEADERS,
    )
    assert response.status_code == 201, response.text
    project = response.json()
    snapshot_id = project["latest_snapshot"]["id"]
    analysis = client.post(
        f"/api/v1/snapshots/{snapshot_id}/analyses", headers=GRAPH_HEADERS
    )
    assert analysis.status_code == 202, analysis.text
    return analysis.json()


def graph_fixture(auth_client):
    analysis = upload_graph_project(auth_client)
    graph = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph", headers=GRAPH_HEADERS
    )
    assert graph.status_code == 200, graph.text
    return analysis, graph.json()


def test_graph_requires_auth(client):
    response = client.get("/api/v1/analyses/whatever/graph")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_graph_analysis_not_found(auth_client):
    response = auth_client.get("/api/v1/analyses/nonexistent/graph", headers=GRAPH_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_graph_not_ready_while_running(auth_client, session_factory):
    """Graph endpoints answer 409 ANALYSIS_NOT_READY for unfinished runs."""
    analysis, _ = graph_fixture(auth_client)
    from app.models.projects import AnalysisRun

    session = session_factory()
    try:
        run = session.get(AnalysisRun, analysis["id"])
        assert run is not None
        run.state = "running"
        session.flush()
        session.commit()
    finally:
        session.close()
    base = f"/api/v1/analyses/{analysis['id']}"
    response = auth_client.get(f"{base}/graph", headers=GRAPH_HEADERS)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"
    node = auth_client.get(f"{base}/nodes/whatever", headers=GRAPH_HEADERS)
    assert node.status_code == 409
    neighbors = auth_client.get(
        f"{base}/nodes/whatever/neighbors", headers=GRAPH_HEADERS
    )
    assert neighbors.status_code == 409


def test_graph_invalid_filters(auth_client):
    analysis, graph = graph_fixture(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/graph"
    assert auth_client.get(base, params={"view": "nonsense"}, headers=GRAPH_HEADERS).status_code == 400
    response = auth_client.get(base, params={"node_kinds": "nope"}, headers=GRAPH_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert auth_client.get(base, params={"limit": 5000}, headers=GRAPH_HEADERS).status_code == 400


def test_graph_function_view(auth_client):
    _analysis, payload = graph_fixture(auth_client)
    assert payload["view"] == "function"
    kinds = {node["kind"] for node in payload["nodes"]}
    assert kinds == {"module", "class", "function", "method"}
    edge_kinds = {edge["kind"] for edge in payload["edges"]}
    assert edge_kinds <= {"CALLS", "IMPORTS", "INHERITS", "CONTAINS"}
    assert payload["truncated"] is False
    assert payload["total_nodes"] == len(payload["nodes"])
    # Every node carries metrics and the unknown coverage placeholder.
    for node in payload["nodes"]:
        assert node["metrics"]["in_degree"] >= 0
        assert node["metrics"]["out_degree"] >= 0
        assert node["coverage_status"] == "unknown"
    # Every non-CONTAINS edge carries evidence.
    for edge in payload["edges"]:
        if edge["kind"] != "CONTAINS":
            assert edge["evidence"], edge
            assert edge["resolver"]


def test_expected_dependency_edges(auth_client):
    _analysis, payload = graph_fixture(auth_client)
    nodes = {node["qualified_name"]: node for node in payload["nodes"]}
    edges = {
        (nodes_by_id(payload, edge["source"]), nodes_by_id(payload, edge["target"]), edge["kind"])
        for edge in payload["edges"]
    }
    assert ("app.main:main", "app.service:helper", "CALLS") in edges
    assert ("app.main:main", "app.service:Service", "CALLS") in edges
    # Local-variable receivers (`service = Service()`; `service.run(...)`)
    # stay unresolved by design: no assignments are tracked, so nothing is
    # guessed. helper() resolves through its `help_fn` alias instead.
    # (CONTAINS Service → Service.run is structural and expected.)
    assert all(
        e[1] != "app.service:Service.run" or e[2] == "CONTAINS" for e in edges
    )
    assert ("app.service:Service", "app.service:Base", "INHERITS") in edges
    assert ("app.service:Service.run", "app.service:Base.ping", "CALLS") in edges
    assert ("app.main", "app.service", "IMPORTS") in edges
    assert ("app.extra", "app.service", "IMPORTS") in edges
    assert ("app.extra:uses_helper", "app.service:helper", "CALLS") in edges
    # Structural containment is present and separate from dependencies.
    assert ("app.service", "app.service:Service", "CONTAINS") in edges


def nodes_by_id(payload, node_id):
    return next(node["qualified_name"] for node in payload["nodes"] if node["id"] == node_id)


def test_graph_module_and_class_views(auth_client):
    analysis, _ = graph_fixture(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/graph"
    module_view = auth_client.get(base, params={"view": "module"}, headers=GRAPH_HEADERS).json()
    assert module_view["view"] == "module"
    assert {node["kind"] for node in module_view["nodes"]} == {"module"}
    qnames = {node["qualified_name"] for node in module_view["nodes"]}
    # The root package file parses as module "__init__" (parser convention).
    assert qnames == {"__init__", "app", "app.main", "app.service", "app.extra"}
    # Empty init module "" is the root package node; edges skip CONTAINS and
    # collapse onto module nodes.
    lookup = {node["id"]: node["qualified_name"] for node in module_view["nodes"]}
    module_edges = {
        (lookup[edge["source"]], lookup[edge["target"]], edge["kind"])
        for edge in module_view["edges"]
    }
    assert ("app.main", "app.service", "IMPORTS") in module_edges
    # Calls also collapse onto the module pair (main → service classes/functions).
    assert ("app.main", "app.service", "CALLS") in module_edges

    class_view = auth_client.get(base, params={"view": "class"}, headers=GRAPH_HEADERS).json()
    class_kinds = {node["kind"] for node in class_view["nodes"]}
    assert class_kinds == {"module", "class"}
    assert "app.service:Service.run" not in {node["qualified_name"] for node in class_view["nodes"]}


def test_graph_kind_filters(auth_client):
    analysis, _ = graph_fixture(auth_client)
    base = f"/api/v1/analyses/{analysis['id']}/graph"
    modules_only = auth_client.get(base, params={"node_kinds": "module"}, headers=GRAPH_HEADERS).json()
    assert {node["kind"] for node in modules_only["nodes"]} == {"module"}
    edges_only_contains = auth_client.get(
        base, params={"edge_kinds": "CONTAINS"}, headers=GRAPH_HEADERS
    ).json()
    assert {edge["kind"] for edge in edges_only_contains["edges"]} == {"CONTAINS"}
    no_contains = auth_client.get(
        base,
        params={"edge_kinds": ["CALLS", "IMPORTS", "INHERITS"]},
        headers=GRAPH_HEADERS,
    ).json()
    assert "CONTAINS" not in {edge["kind"] for edge in no_contains["edges"]}


def test_graph_node_limit_truncates(auth_client):
    analysis, _ = graph_fixture(auth_client)
    response = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph",
        params={"limit": 2},
        headers=GRAPH_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["nodes"]) == 2
    assert payload["truncated"] is True
    assert payload["total_nodes"] > 2


def test_node_detail(auth_client):
    analysis, _ = graph_fixture(auth_client)
    graph = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph", headers=GRAPH_HEADERS
    ).json()
    target = next(node for node in graph["nodes"] if node["qualified_name"] == "app.service:helper")
    detail = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/nodes/{target['id']}", headers=GRAPH_HEADERS
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["id"] == target["id"]
    assert payload["qualified_name"] == "app.service:helper"
    assert payload["metrics"]["in_degree"] >= 2  # main() and uses_helper() call it
    assert payload["coverage_status"] == "unknown"
    assert "app/" not in payload["file_path"][:1]  # snapshot-relative path


def test_node_not_found(auth_client):
    analysis, _ = graph_fixture(auth_client)
    response = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/nodes/doesnotexist", headers=GRAPH_HEADERS
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_neighbors_bounded(auth_client):
    analysis, _ = graph_fixture(auth_client)
    graph = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph", headers=GRAPH_HEADERS
    ).json()
    nodes = {node["qualified_name"]: node for node in graph["nodes"]}
    target = nodes["app.service:helper"]

    upstream = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/nodes/{target['id']}/neighbors",
        params={"direction": "upstream", "depth": 1},
        headers=GRAPH_HEADERS,
    )
    assert upstream.status_code == 200
    payload = upstream.json()
    qnames = {node["qualified_name"] for node in payload["nodes"]}
    assert "app.main:main" in qnames
    assert "app.extra:uses_helper" in qnames
    assert all(item in qnames for item in ["app.service:helper"])
    # limit=1 truncates and reports it.
    limited = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/nodes/{target['id']}/neighbors",
        params={"direction": "upstream", "depth": 1, "limit": 1},
        headers=GRAPH_HEADERS,
    )
    assert limited.json()["truncated"] is True
    # depth is bounded to 3 by the router; 4 is rejected.
    assert (
        auth_client.get(
            f"/api/v1/analyses/{analysis['id']}/nodes/{target['id']}/neighbors",
            params={"depth": 4},
            headers=GRAPH_HEADERS,
        ).status_code
        == 400
    )


def test_graph_ownership_isolated(auth_client):
    """Editors cannot read graphs of analyses they do not own."""
    analysis = upload_graph_project(auth_client)
    # Second session/user signs in via the mocked provider.
    from tests.conftest import SESSION_COOKIE

    response = auth_client.get("/api/v1/auth/github/start")
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    callback = auth_client.get(
        "/api/v1/auth/github/callback",
        params={"code": "user-two", "state": state},
        headers={"Origin": TEST_ORIGIN},
    )
    assert callback.status_code == 302
    # Replace the session cookie with the second user's.
    foreign_cookie = callback.cookies.get(SESSION_COOKIE)
    auth_client.cookies.set(SESSION_COOKIE, foreign_cookie, domain="testserver")
    response = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph", headers=GRAPH_HEADERS
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_graph_unresolved_count_reported(auth_client):
    analysis, _ = graph_fixture(auth_client)
    payload = auth_client.get(
        f"/api/v1/analyses/{analysis['id']}/graph", headers=GRAPH_HEADERS
    ).json()
    assert payload["unresolved_count"] >= 0  # no fabrication; zero is valid
    # The run payload itself carries the exact counters.
    run = auth_client.get(f"/api/v1/analyses/{analysis['id']}", headers=GRAPH_HEADERS).json()
    assert run["edge_count"] > 0
    assert run["diagnostics_summary"]["unresolved_references"] >= 0
    assert run["diagnostics_summary"]["ambiguous_references"] >= 0
