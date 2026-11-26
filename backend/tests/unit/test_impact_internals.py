"""Impact internals unit tests (Phase 6A).

BFS traversal (distance, depth cap, cycle safety, determinism), path
reconstruction, and the risk scorer's factor model / renormalization rules.
"""

from app.services.analysis.impact import (
    _path_from_target,
    _path_toward_target,
    _traverse,
)
from app.services.analysis.risk import compute_risk

GRAPH = {
    # downstream chain: t → a → b, cycle b → a, side edge t → c
    "t": ["a", "c"],
    "a": ["b"],
    "b": ["a"],
    "c": [],
}
EDGE = lambda u, v: f"e:{u}->{v}"  # noqa: E731


def test_traverse_distances_and_order():
    distance, parents = _traverse("t", successors=lambda n: GRAPH[n], edge_id=EDGE, max_depth=5)
    assert distance == {"t": 0, "a": 1, "c": 1, "b": 2}
    assert parents["a"] == ("t", "e:t->a")
    assert parents["b"] == ("a", "e:a->b")
    # Cycle safety: a is settled at distance 1 even though b → a cycles back.
    assert distance["a"] == 1 and len(distance) == 4


def test_traverse_depth_cap():
    distance, _parents = _traverse("t", successors=lambda n: GRAPH[n], edge_id=EDGE, max_depth=1)
    assert "b" not in distance  # b is 2 hops away; capped out
    assert distance["a"] == 1


def test_traverse_deterministic():
    first = _traverse("t", successors=lambda n: GRAPH[n], edge_id=EDGE, max_depth=5)
    second = _traverse("t", successors=lambda n: GRAPH[n], edge_id=EDGE, max_depth=5)
    assert first == second


def test_path_reconstruction_both_orientations():
    distance, parents = _traverse("t", successors=lambda n: GRAPH[n], edge_id=EDGE, max_depth=5)
    assert _path_from_target(parents, "b", "t") == ["e:t->a", "e:a->b"]
    assert _path_from_target(parents, "a", "t") == ["e:t->a"]


def test_path_toward_target_upstream():
    # Upstream orientation: in_neighbors map, and the edge connects
    # neighbor → current (mirroring the service's reversed edge lookup).
    in_graph = {"t": ["b"], "b": ["t", "s"], "s": [], "a": ["t"]}
    distance, parents = _traverse(
        "t",
        successors=lambda n: in_graph[n],
        edge_id=lambda source, target: f"e:{target}->{source}",
        max_depth=3,
    )
    # s is upstream of t via s → b → t: from s, walk toward t.
    assert distance["b"] == 1 and distance["s"] == 2
    assert _path_toward_target(parents, "s", "t") == ["e:s->b", "e:b->t"]


def test_risk_score_shape_and_bounds():
    risk = compute_risk(
        version="1",
        weights={
            "upstream_reachable_dependents": 0.35,
            "in_degree_centrality": 0.20,
            "downstream_breadth": 0.15,
            "public_entry_point": 0.15,
            "coverage_deficiency": 0.15,
        },
        normalization_cap=100,
        upstream_union_size=50,
        downstream_union_size=10,
        max_target_in_degree=3,
        graph_max_in_degree=4,
        public_entry_fraction=1.0,
        coverage_present=False,
    )
    assert 0 <= risk["score"] <= 100
    assert risk["coverage_included"] is False
    assert risk["version"] == "1"
    keys = [f["key"] for f in risk["factors"]]
    assert keys == [
        "upstream_reachable_dependents",
        "in_degree_centrality",
        "downstream_breadth",
        "public_entry_point",
        "coverage_deficiency",
    ]
    # Coverage factor excluded, remaining four weights renormalized to 1.
    included = [f for f in risk["factors"] if f["included"]]
    excluded = [f for f in risk["factors"] if not f["included"]]
    assert {f["key"] for f in excluded} == {"coverage_deficiency"}
    # Weights are reported at 4 decimals; the sum is 1 up to that rounding.
    assert abs(sum(f["weight"] for f in included) - 1.0) < 0.001
    # Deterministic.
    again = compute_risk(
        version="1",
        weights={
            "upstream_reachable_dependents": 0.35,
            "in_degree_centrality": 0.20,
            "downstream_breadth": 0.15,
            "public_entry_point": 0.15,
            "coverage_deficiency": 0.15,
        },
        normalization_cap=100,
        upstream_union_size=50,
        downstream_union_size=10,
        max_target_in_degree=3,
        graph_max_in_degree=4,
        public_entry_fraction=1.0,
        coverage_present=False,
    )
    assert again == risk
    # Honest caveats: never called a failure probability.
    joined = " ".join(risk["caveats"])
    assert "NOT a probability of failure" in joined
    assert "coverage" in joined


def test_risk_score_values_computed():
    weights = {
        "upstream_reachable_dependents": 0.35,
        "in_degree_centrality": 0.20,
        "downstream_breadth": 0.15,
        "public_entry_point": 0.15,
        "coverage_deficiency": 0.15,
    }
    risk = compute_risk(
        version="1",
        weights=weights,
        normalization_cap=100,
        upstream_union_size=100,  # normalized 1.0 → 0.35 * 1 = 0.35
        downstream_union_size=0,
        max_target_in_degree=4,
        graph_max_in_degree=4,  # normalized 1.0 → 0.20 * 1 = 0.20
        public_entry_fraction=1.0,  # 0.15 * 1 = 0.15
        coverage_present=False,
    )
    # Renormalized applied weights: upstream 0.35/0.85 ≈ 0.4118 (normalized
    # 1.0), in-degree 0.2353 (1.0), downstream 0.1765 (0), entry 0.1765 (1.0).
    upstream = next(f for f in risk["factors"] if f["key"] == "upstream_reachable_dependents")
    assert upstream["normalized_value"] == 1.0
    assert upstream["weight"] == 0.4118
    assert risk["score"] == 82  # 0.4118 + 0.2353 + 0 + 0.1765 ≈ 0.8235


def test_risk_excludes_reachability_when_unbudgeted():
    weights = {
        "upstream_reachable_dependents": 0.35,
        "in_degree_centrality": 0.20,
        "downstream_breadth": 0.15,
        "public_entry_point": 0.15,
        "coverage_deficiency": 0.15,
    }
    risk = compute_risk(
        version="1",
        weights=weights,
        normalization_cap=100,
        upstream_union_size=None,  # metrics budget exceeded
        downstream_union_size=None,
        max_target_in_degree=None,
        graph_max_in_degree=4,
        public_entry_fraction=0.5,
        coverage_present=False,
    )
    included_keys = {f["key"] for f in risk["factors"] if f["included"]}
    assert included_keys == {"public_entry_point"}
    joined = " ".join(risk["caveats"])
    assert "metrics node budget" in joined
    assert abs(next(f for f in risk["factors"] if f["included"])["weight"] - 1.0) < 1e-9
    assert 0 <= risk["score"] <= 100


def test_risk_with_coverage_included():
    weights = {
        "upstream_reachable_dependents": 0.35,
        "in_degree_centrality": 0.20,
        "downstream_breadth": 0.15,
        "public_entry_point": 0.15,
        "coverage_deficiency": 0.15,
    }
    risk = compute_risk(
        version="1",
        weights=weights,
        normalization_cap=100,
        upstream_union_size=10,
        downstream_union_size=10,
        max_target_in_degree=2,
        graph_max_in_degree=4,
        public_entry_fraction=0.0,
        coverage_present=True,
        coverage_deficiency=0.5,
    )
    coverage = next(f for f in risk["factors"] if f["key"] == "coverage_deficiency")
    assert coverage["included"] is True and coverage["normalized_value"] == 0.5
    assert risk["coverage_included"] is True
    assert abs(sum(f["weight"] for f in risk["factors"] if f["included"]) - 1.0) < 1e-6
