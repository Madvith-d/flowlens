"""Impact analysis service (Phase 6A).

BFS traversal over the stored dependency graph with visited-set cycle
protection, shortest-hop distances, direct-vs-indirect classification,
representative shortest paths (ordered edge IDs, always valid edge sequences),
per-target attribution, multi-target deduplication, and a configurable depth.

Directions (contract semantics):

* ``downstream`` — nodes the targets (transitively) depend on: the BFS
  follows outgoing edges; each reported path is ordered target → impacted.
* ``upstream`` — callers/dependents of the targets: the BFS follows incoming
  edges; each reported path is ordered impacted → target.
* ``both`` — the union; each impacted node reports at most one
  representative path per orientation (chosen deterministically by
  shortest distance, then target ID).

Traversal only follows real stored dependency edges (CALLS / IMPORTS /
INHERITS / REFERENCES); ``CONTAINS`` is structural and never traversed.
Unresolved or ambiguous references are outside the graph by construction and
are disclosed through warnings rather than guessed.
"""

import logging

import networkx as nx

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.user import User
from app.repositories.analysis import (
    AnalysisRepository,
    DependencyEdgeRepository,
    SymbolRepository,
)
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.analysis.graph import (
    ANALYSIS_NOT_FOUND,
    ANALYSIS_NOT_READY,
    NODE_NOT_FOUND,
    view_edge_id,
)
from app.services.analysis.risk import compute_risk

logger = logging.getLogger("flowlens.impact")

DIRECTIONS = ("upstream", "downstream", "both")
MAX_TARGETS = 10
MAX_DEPTH = 10
# Kind priority when a node pair is connected by more than one edge kind.
_EDGE_KIND_PRIORITY = ("CALLS", "INHERITS", "IMPORTS", "REFERENCES")

INVALID_IMPACT_QUERY = ApiError(
    status_code=400,
    code="VALIDATION_ERROR",
    message="Invalid impact request.",
)


def _traverse(
    start: str,
    *,
    successors,
    edge_id,
    max_depth: int,
):
    """Deterministic BFS; returns (distance map, parent map).

    ``parent[node] = (hop_toward_start, edge_id)`` — the second element is the
    real stored dependency edge connecting node and the next hop toward the
    start node; paths reconstructed from it are always valid edge sequences.
    Visited-set protection makes cycles safe.
    """
    distance = {start: 0}
    parents: dict[str, tuple[str, str] | None] = {start: None}
    frontier = [start]
    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for neighbor in successors(current):
                if neighbor in distance:
                    continue
                distance[neighbor] = depth
                parents[neighbor] = (current, edge_id(current, neighbor))
                next_frontier.append(neighbor)
        if not next_frontier:
            break
        frontier = next_frontier
    return distance, parents


def _path_toward_target(parents: dict, node: str, start: str) -> list[str]:
    """Reconstruct a path ordered node → start (upstream orientation)."""
    edges: list[str] = []
    current = node
    while current != start:
        next_hop, edge_id = parents[current]
        edges.append(edge_id)
        current = next_hop
    return edges


def _path_from_target(parents: dict, node: str, start: str) -> list[str]:
    """Reconstruct a path ordered start → node (downstream orientation)."""
    edges: list[str] = []
    current = node
    while current != start:
        previous_hop, edge_id = parents[current]
        edges.append(edge_id)
        current = previous_hop
    return list(reversed(edges))


class ImpactService:
    """Impact queries over one completed analysis' dependency graph."""

    def __init__(
        self,
        settings: Settings,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        analysis_repo: AnalysisRepository,
        symbol_repo: SymbolRepository,
        edge_repo: DependencyEdgeRepository,
    ) -> None:
        self._settings = settings
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._analyses = analysis_repo
        self._symbols = symbol_repo
        self._edges = edge_repo

    # ------------------------------------------------------------------ guard
    def _owned_run(self, user: User, analysis_id: str):
        run = self._analyses.get(analysis_id)
        if run is None:
            raise ANALYSIS_NOT_FOUND
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise ANALYSIS_NOT_FOUND
        if run.state not in ("completed", "completed_with_warnings"):
            raise ANALYSIS_NOT_READY
        return run

    # ---------------------------------------------------------------- public
    def impact(
        self,
        user: User,
        analysis_id: str,
        *,
        target_ids: list[str],
        direction: str,
        max_depth: int,
    ) -> dict:
        run = self._owned_run(user, analysis_id)
        # De-duplicate request targets; keep original order out of the answer.
        unique_targets = sorted(set(target_ids))
        if not (1 <= len(unique_targets) <= MAX_TARGETS):
            raise INVALID_IMPACT_QUERY
        if direction not in DIRECTIONS:
            raise INVALID_IMPACT_QUERY
        if not (1 <= max_depth <= MAX_DEPTH):
            raise INVALID_IMPACT_QUERY

        symbols = self._symbols.list_for_analysis(run.id)
        by_id = {symbol.id: symbol for symbol in symbols}
        missing = [tid for tid in unique_targets if tid not in by_id]
        if missing:
            raise ApiError(
                status_code=404,
                code="NOT_FOUND",
                message="Target symbol not found in this analysis.",
                details={"missing_target_ids": missing[:10]},
            )
        target_symbols = [by_id[tid] for tid in unique_targets]
        target_set = set(unique_targets)

        edge_rows = self._edges.list_for_analysis(run.id)
        out_neighbors, in_neighbors, edge_of = self._adjacency(symbols, by_id, edge_rows, run.id)

        orientations = ("downstream",) if direction == "downstream" else ("upstream",) if direction == "upstream" else ("upstream", "downstream")
        runs: dict[tuple[str, str], tuple[dict, dict]] = {}
        for target_id in unique_targets:
            for orientation in orientations:
                if orientation == "downstream":
                    distance, parents = _traverse(
                        target_id,
                        successors=lambda node: out_neighbors[node],
                        edge_id=lambda source, target: edge_of.get((source, target), ""),
                        max_depth=max_depth,
                    )
                else:
                    distance, parents = _traverse(
                        target_id,
                        successors=lambda node: in_neighbors[node],
                        edge_id=lambda source, target: edge_of.get((target, source), ""),
                        max_depth=max_depth,
                    )
                runs[(target_id, orientation)] = (distance, parents)

        impacted: dict[str, dict] = {}
        for (target_id, orientation), (distance, _parents) in runs.items():
            for node, hops in distance.items():
                if node in target_set:
                    continue  # the targets themselves are never "impacted"
                record = impacted.setdefault(
                    node, {"min_hops": hops, "attributed": set(), "paths": {}}
                )
                record["min_hops"] = min(record["min_hops"], hops)
                record["attributed"].add(target_id)
                record["paths"][(target_id, orientation)] = hops

        warnings: list[str] = []
        ordered = sorted(
            impacted, key=lambda node: (impacted[node]["min_hops"], by_id[node].qualified_name, node)
        )
        truncated = False
        cap = self._settings.impact_max_impacted_nodes
        if len(ordered) > cap:
            truncated = True
            warnings.append(
                f"Impacted node list truncated to the configured bound of {cap};"
                " distance counters for the remaining nodes are not reported."
            )
            ordered = ordered[:cap]

        impacted_payload = []
        for node in ordered:
            record = impacted[node]
            payload_paths = []
            for orientation in orientations:
                candidates = {
                    target_id: hops
                    for (target_id, ori), hops in record["paths"].items()
                    if ori == orientation
                }
                if not candidates:
                    continue
                best_target = sorted(candidates, key=lambda t: (candidates[t], t))[0]
                _distance, parents = runs[(best_target, orientation)]
                if orientation == "downstream":
                    edges = _path_from_target(parents, node, best_target)
                else:
                    edges = _path_toward_target(parents, node, best_target)
                if edges:
                    payload_paths.append({"edges": edges})
            symbol = by_id[node]
            impacted_payload.append(
                {
                    "node_id": node,
                    "kind": symbol.kind,
                    "qualified_name": symbol.qualified_name,
                    "direct": record["min_hops"] == 1,
                    "min_hops": record["min_hops"],
                    "paths": payload_paths,
                    "attributed_to": sorted(record["attributed"]),
                }
            )

        risk, risk_warnings = self._risk_payload(by_id, target_symbols, run, edge_rows)
        warnings.extend(risk_warnings)
        unresolved = run.unresolved_reference_count + run.ambiguous_reference_count
        if unresolved:
            warnings.append(
                f"{unresolved} unresolved or ambiguous reference(s) in this analysis"
                " are excluded from the dependency graph and from this impact result."
            )

        return {
            "analysis_id": run.id,
            "targets": [
                {"node_id": symbol.id, "qualified_name": symbol.qualified_name}
                for symbol in target_symbols
            ],
            "direction": direction,
            "max_depth": max_depth,
            "impacted": impacted_payload,
            "truncated": truncated,
            "risk": risk,
            "warnings": warnings,
            "coverage_summary": None,  # coverage attaches in Phase 7A
        }

    # --------------------------------------------------------------- internals
    def _adjacency(self, symbols, by_id: dict, edge_rows, run_id: str):
        """Deterministic successor/predecessor lists plus per-pair edge IDs.

        When a pair is connected by several edge kinds, the representative
        edge follows the priority CALLS > INHERITS > IMPORTS > REFERENCES (and
        its stored ID), so paths are stable across runs.
        """
        out_neighbors: dict[str, list[str]] = {symbol.id: [] for symbol in symbols}
        in_neighbors: dict[str, list[str]] = {symbol.id: [] for symbol in symbols}
        # Pair → representative kind (priority) and the matching response edge
        # ID (same scheme the graph API exposes, so path edge IDs correlate).
        edge_of: dict[tuple[str, str], str] = {}
        edge_kind_of: dict[tuple[str, str], str] = {}
        for row in edge_rows:
            pair = (row.source_id, row.target_id)
            current = edge_kind_of.get(pair)
            if current is None or _EDGE_KIND_PRIORITY.index(row.kind) < _EDGE_KIND_PRIORITY.index(
                current
            ):
                edge_kind_of[pair] = row.kind
                edge_of[pair] = view_edge_id(run_id, row.source_id, row.target_id, row.kind)
            if row.target_id in out_neighbors and row.source_id in out_neighbors:
                if row.target_id not in out_neighbors[row.source_id]:
                    out_neighbors[row.source_id].append(row.target_id)
                if row.source_id not in in_neighbors[row.target_id]:
                    in_neighbors[row.target_id].append(row.source_id)

        def sort_key(node_id: str):
            symbol = by_id.get(node_id)
            return (symbol.qualified_name if symbol else node_id, node_id)

        for node in out_neighbors:
            out_neighbors[node] = sorted(out_neighbors[node], key=sort_key)
        for node in in_neighbors:
            in_neighbors[node] = sorted(in_neighbors[node], key=sort_key)
        return out_neighbors, in_neighbors, edge_of

    def _risk_payload(self, by_id, target_symbols, run, edge_rows) -> tuple[dict, list[str]]:
        """Explainable risk over the targets (see risk.py for the model)."""
        graph = nx.DiGraph()
        graph.add_nodes_from(by_id.keys())
        for row in edge_rows:
            graph.add_edge(row.source_id, row.target_id)

        within_budget = len(graph) <= self._settings.graph_metrics_max_nodes
        if within_budget:
            upstream_union: set[str] = set()
            downstream_union: set[str] = set()
            for symbol in target_symbols:
                upstream_union.update(nx.ancestors(graph, symbol.id))
                downstream_union.update(nx.descendants(graph, symbol.id))
            upstream_size: int | None = len(upstream_union)
            downstream_size: int | None = len(downstream_union)
            max_in_degree: int | None = max(
                (graph.in_degree(symbol.id) for symbol in target_symbols),
                default=0,
            )
        else:
            upstream_size = None
            downstream_size = None
            max_in_degree = None
        graph_max_in_degree = max((int(d) for _, d in graph.in_degree()), default=0)

        public_count = 0
        for symbol in target_symbols:
            if symbol.kind in ("module", "class", "function") and symbol.parent_id is None:
                public_count += 1
            elif symbol.parent_id is not None:
                parent = by_id.get(symbol.parent_id)
                if parent is not None and parent.kind == "module" and symbol.kind in ("class", "function"):
                    public_count += 1
        public_fraction = (public_count / len(target_symbols)) if target_symbols else 0.0

        risk = compute_risk(
            version=self._settings.risk_score_version,
            weights={
                "upstream_reachable_dependents": self._settings.risk_weight_upstream_dependents,
                "in_degree_centrality": self._settings.risk_weight_in_degree,
                "downstream_breadth": self._settings.risk_weight_downstream_breadth,
                "public_entry_point": self._settings.risk_weight_public_entry,
                "coverage_deficiency": self._settings.risk_weight_coverage_deficiency,
            },
            normalization_cap=self._settings.risk_normalization_cap,
            upstream_union_size=upstream_size,
            downstream_union_size=downstream_size,
            max_target_in_degree=max_in_degree,
            graph_max_in_degree=graph_max_in_degree,
            public_entry_fraction=public_fraction,
            coverage_present=False,  # coverage data attaches in Phase 7A
        )
        return risk, []
