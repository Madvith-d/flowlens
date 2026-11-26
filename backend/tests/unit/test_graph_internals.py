"""Graph internals unit tests (Phase 5A).

Focuses on the riskiest pure pieces: cycle-safe reachability (SCC
condensation), bounded neighborhoods, and deterministic behavior on
hand-built dependency graphs. View collapse and API behavior are covered by
the integration suite.
"""

import networkx as nx

from app.services.analysis.graph import AnalysisGraphService


def service(settings) -> AnalysisGraphService:
    return AnalysisGraphService(
        settings=settings,
        project_repo=None,
        snapshot_repo=None,
        analysis_repo=None,
        symbol_repo=None,
        edge_repo=None,
    )


def test_reachable_counts_on_dag(settings):
    # a → b → c; a → c
    graph = nx.DiGraph([("a", "b"), ("b", "c"), ("a", "c")])
    downstream, upstream = AnalysisGraphService._reachable_maps(graph)
    assert downstream["a"] == 2  # b and c
    assert downstream["b"] == 1
    assert downstream["c"] == 0
    assert upstream["a"] == 0
    assert upstream["c"] == 2


def test_reachable_counts_with_cycle_branch(settings):
    # a → b → c → b forms a cycle, plus d → a: counting must terminate.
    graph = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "b"), ("d", "a")])
    downstream, upstream = AnalysisGraphService._reachable_maps(graph)
    # From a: b and c are reachable (a itself excluded).
    assert downstream["a"] == 2
    # Upstream of b: a and d directly, and c via the c → b edge.
    assert upstream["b"] == 3


def test_reachable_counts_on_pure_cycle(settings):
    # Pure cycle a → b → c → a: both directions reach the other two.
    graph = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])
    downstream, upstream = AnalysisGraphService._reachable_maps(graph)
    assert downstream["a"] == 2
    assert upstream["a"] == 2


def test_reachable_counts_empty_graph(settings):
    downstream, upstream = AnalysisGraphService._reachable_maps(nx.DiGraph())
    assert downstream == {} and upstream == {}


def test_neighborhood_bounded_and_deterministic(settings):
    graph = nx.DiGraph([("n", "c2"), ("n", "c1"), ("c1", "d1"), ("d1", "n")])
    svc = service(settings)
    selected = svc._neighborhood(graph, "n", "downstream", 2)
    assert set(selected) == {"c1", "c2", "d1"}
    assert selected == sorted(selected)
    # depth 1 only.
    assert set(svc._neighborhood(graph, "n", "downstream", 1)) == {"c1", "c2"}
    # upstream of n: d1, then c1 through d1 (c1 → d1 → n).
    assert set(svc._neighborhood(graph, "n", "upstream", 3)) == {"d1", "c1"}
    assert set(svc._neighborhood(graph, "n", "upstream", 1)) == {"d1"}
