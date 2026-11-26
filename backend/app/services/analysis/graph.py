"""Dependency graph store and query service (Phase 5A).

Builds a per-analysis directed graph from stored symbols and dependency edges
using NetworkX and serves bounded, deterministic graph views:

* ``function`` view — every symbol is a node (default).
* ``class`` view — classes and modules are nodes; methods/functions collapse
  onto their nearest enclosing class (module-level functions onto their
  module).
* ``module`` view — modules are nodes; every symbol collapses onto its module.

Only dependency edges (CALLS / IMPORTS / INHERITS / REFERENCES) drive
traversals and metrics. ``CONTAINS`` is structural, derived here from
``Symbol.parent_id``, never stored in ``dependency_edges`` and never treated as
a dependency.

All results are deterministic (stable ordering by source location and ID),
``truncated`` is reported whenever a server-side bound is hit, and
reachability metrics are computed only while the graph stays within the
configured node budget — otherwise they are omitted rather than estimated.
"""

import hashlib
import json
import logging
from dataclasses import dataclass

import networkx as nx

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.analysis import DependencyEdge, Symbol
from app.models.projects import AnalysisRun
from app.models.user import User
from app.repositories.analysis import (
    AnalysisRepository,
    DependencyEdgeRepository,
    SymbolRepository,
)
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.analysis.resolver import (
    _CONFIDENCE_RANK,  # deterministic confidence ranking (module-private)
)

logger = logging.getLogger("flowlens.graph")

GRAPH_VIEWS = ("module", "class", "function")
NODE_KINDS = ("module", "class", "function", "method")
DEPENDENCY_KIND_SET = {"CALLS", "IMPORTS", "INHERITS", "REFERENCES"}
EDGE_KIND_SET = {"CALLS", "IMPORTS", "INHERITS", "REFERENCES", "CONTAINS"}
NEIGHBOR_LIMIT_MAX = 500
NEIGHBOR_DEPTH_MAX = 3

ANALYSIS_NOT_READY = ApiError(
    status_code=409,
    code="ANALYSIS_NOT_READY",
    message="Analysis has not completed; the graph is not available.",
)
ANALYSIS_NOT_FOUND = ApiError(
    status_code=404,
    code="ANALYSIS_NOT_FOUND",
    message="Analysis not found.",
)
INVALID_GRAPH_QUERY = ApiError(
    status_code=400,
    code="VALIDATION_ERROR",
    message="Invalid graph query.",
)
NODE_NOT_FOUND = ApiError(
    status_code=404,
    code="NOT_FOUND",
    message="Node not found in this analysis.",
)


@dataclass(frozen=True)
class _StoredEdge:
    source_id: str
    target_id: str
    kind: str
    confidence: str
    resolver: str
    evidence: tuple[dict, ...]


def view_edge_id(analysis_id: str, source_id: str, target_id: str, kind: str) -> str:
    """Stable response edge ID shared by graph and impact payloads.

    Path edge IDs in impact results must match the edge IDs the graph API
    exposes for the same (source, target, kind), so clients can correlate
    them; both payload layers use this one function.
    """
    return hashlib.sha256(
        f"{analysis_id}|graph|{source_id}|{target_id}|{kind}".encode("utf-8")
    ).hexdigest()[:40]


class AnalysisGraphService:
    """Reads one completed analysis and serves bounded graph queries."""

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

    # ----------------------------------------------------------------- guard
    def _owned_run(self, user: User, analysis_id: str) -> AnalysisRun:
        run = self._analyses.get(analysis_id)
        if run is None:
            raise ANALYSIS_NOT_FOUND
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise ANALYSIS_NOT_FOUND
        if run.state not in ("completed", "completed_with_warnings"):
            raise ANALYSIS_NOT_READY
        return run

    # -------------------------------------------------------------- payloads
    def graph(
        self,
        user: User,
        analysis_id: str,
        *,
        view: str,
        node_kinds: list[str],
        edge_kinds: list[str],
        limit: int,
    ) -> dict:
        run = self._owned_run(user, analysis_id)
        self._validate_filters(view, node_kinds, edge_kinds)
        symbols = self._symbols.list_for_analysis(run.id)
        stored = self._stored_edges(run.id)
        return self._build_response(
            run, symbols, stored, view, node_kinds, edge_kinds, limit, seeds=None, direction="both", depth=1
        )

    def node(self, user: User, analysis_id: str, node_id: str) -> dict:
        run = self._owned_run(user, analysis_id)
        symbols = self._symbols.list_for_analysis(run.id)
        by_id = {symbol.id: symbol for symbol in symbols}
        target = by_id.get(node_id)
        if target is None:
            raise NODE_NOT_FOUND
        stored = self._stored_edges(run.id)
        graph = self._dependency_nx(symbols, stored)
        metrics = self._metrics_for(graph, node_id)
        return self._node_payload(target, metrics)

    def neighbors(
        self,
        user: User,
        analysis_id: str,
        node_id: str,
        *,
        depth: int,
        direction: str,
        limit: int,
    ) -> dict:
        run = self._owned_run(user, analysis_id)
        symbols = self._symbols.list_for_analysis(run.id)
        by_id = {symbol.id: symbol for symbol in symbols}
        if node_id not in by_id:
            raise NODE_NOT_FOUND
        if direction not in ("upstream", "downstream", "both"):
            raise INVALID_GRAPH_QUERY
        depth = max(1, min(int(depth), NEIGHBOR_DEPTH_MAX))
        limit = max(1, min(int(limit), NEIGHBOR_LIMIT_MAX))
        stored = self._stored_edges(run.id)
        graph = self._dependency_nx(symbols, stored)
        selected = self._neighborhood(graph, node_id, direction, depth)
        truncated = len(selected) > limit
        selected = set(sorted(selected)[:limit])
        selected.add(node_id)
        selected_symbols = [by_id[n] for n in selected]
        return self._build_response(
            run,
            selected_symbols,
            stored,
            view="function",
            node_kinds=[],
            edge_kinds=[],
            limit=max(limit + 1, len(selected_symbols)),
            seeds={node_id},
            direction=direction,
            depth=depth,
            truncated=truncated,
        )

    # ------------------------------------------------------------ validation
    def _validate_filters(self, view: str, node_kinds: list[str], edge_kinds: list[str]) -> None:
        if view not in GRAPH_VIEWS:
            raise INVALID_GRAPH_QUERY
        for kind in node_kinds:
            if kind not in NODE_KINDS:
                raise INVALID_GRAPH_QUERY
        for kind in edge_kinds:
            if kind not in EDGE_KIND_SET:
                raise INVALID_GRAPH_QUERY

    # -------------------------------------------------------------- internals
    def _stored_edges(self, analysis_id: str) -> list[_StoredEdge]:
        result: list[_StoredEdge] = []
        for row in self._edges.list_for_analysis(analysis_id):
            result.append(
                _StoredEdge(
                    source_id=row.source_id,
                    target_id=row.target_id,
                    kind=row.kind,
                    confidence=row.confidence,
                    resolver=row.resolver,
                    evidence=tuple(json.loads(row.evidence or "[]")),
                )
            )
        return result

    def _representative(self, symbol: Symbol, symbols_by_id: dict[str, Symbol], view: str, module_ids: dict[str, str]) -> Symbol:
        """Node a symbol collapses onto for the requested view."""
        if view == "function":
            return symbol
        if view == "module":
            module_id = module_ids.get(symbol.file_path)
            return symbols_by_id.get(module_id, symbol) if module_id else symbol
        # class view: nearest class ancestor, else the module node.
        current = symbol
        if symbol.kind == "class":
            return symbol
        seen: set[str] = {symbol.id}
        while current.parent_id and current.parent_id not in seen:
            seen.add(current.parent_id)
            parent = symbols_by_id.get(current.parent_id)
            if parent is None:
                break
            if parent.kind == "class":
                return parent
            current = parent
        module_id = module_ids.get(symbol.file_path)
        return symbols_by_id.get(module_id, symbol) if module_id else symbol

    def _build_response(
        self,
        run: AnalysisRun,
        symbols: list[Symbol],
        stored: list[_StoredEdge],
        view: str,
        node_kinds: list[str],
        edge_kinds: list[str],
        limit: int,
        *,
        seeds: set[str] | None,
        direction: str,
        depth: int,
        truncated: bool = False,
    ) -> dict:
        symbols_by_id = {symbol.id: symbol for symbol in symbols}
        module_ids = self._module_ids(symbols)
        view_of = {symbol.id: self._representative(symbol, symbols_by_id, view, module_ids) for symbol in symbols}

        # Collect representative nodes deterministically.
        reps: dict[str, Symbol] = {}
        for symbol in symbols:
            representative = view_of[symbol.id]
            if node_kinds and representative.kind not in node_kinds:
                continue
            reps[representative.id] = representative
        ordered_reps = sorted(
            reps.values(),
            key=lambda s: (s.file_path, s.start_line, s.start_column, s.qualified_name, s.id),
        )
        total_nodes = len(ordered_reps)
        if seeds is None and limit < total_nodes:
            truncated = True
            ordered_reps = ordered_reps[:limit]
        elif seeds is not None and limit < total_nodes:
            truncated = True
            keep = {s.id for s in ordered_reps[:limit]}
            ordered_reps = [s for s in ordered_reps if s.id in keep]
        served_ids = {symbol.id for symbol in ordered_reps}

        # View-collapsed edges (dependency kinds + derived CONTAINS).
        collapsed: dict[tuple[str, str, str], dict] = {}
        for edge in stored:
            if edge_kinds and edge.kind not in edge_kinds:
                continue
            source_rep = view_of.get(edge.source_id)
            target_rep = view_of.get(edge.target_id)
            if source_rep is None or target_rep is None or source_rep.id == target_rep.id:
                continue
            if source_rep.id not in served_ids or target_rep.id not in served_ids:
                continue
            self._merge_edge(collapsed, (source_rep.id, target_rep.id, edge.kind), edge)
        if not edge_kinds or "CONTAINS" in edge_kinds:
            for symbol in symbols:
                if not symbol.parent_id or symbol.id not in served_ids:
                    continue
                parent_rep = view_of.get(symbol.parent_id)
                if parent_rep is None or parent_rep.id not in served_ids or parent_rep.id == symbol.id:
                    continue
                key = (parent_rep.id, symbol.id, "CONTAINS")
                if key not in collapsed:
                    collapsed[key] = {
                        "kind": "CONTAINS",
                        "confidence": "high",
                        "resolver": "structural",
                        "evidence": [
                            {
                                "file_path": symbol.file_path,
                                "line": symbol.start_line,
                                "column": symbol.start_column,
                                "expression": f"{parent_rep.qualified_name} contains {symbol.qualified_name}",
                            }
                        ],
                    }

        # Metrics on the filtered, collapsed dependency graph.
        dependency_nx = self._collapsed_dependency_nx(collapsed, served_ids)
        metrics = self._metrics_map(dependency_nx, served_ids)

        node_payloads = [self._node_payload(symbol, metrics.get(symbol.id)) for symbol in ordered_reps]
        ordered_edges = []
        total_edges = len(collapsed)
        for (source_id, target_id, kind) in sorted(collapsed):
            if len(ordered_edges) >= self._settings.graph_max_edges_per_response:
                truncated = True
                break
            entry = collapsed[(source_id, target_id, kind)]
            ordered_edges.append(
                {
                    "id": self._view_edge_id(run.id, source_id, target_id, kind),
                    "source": source_id,
                    "target": target_id,
                    "kind": kind,
                    "confidence": entry["confidence"],
                    "resolver": entry["resolver"],
                    "evidence": entry["evidence"][: self._settings.analysis_max_evidence_per_edge],
                }
            )

        response = {
            "analysis_id": run.id,
            "view": view,
            "nodes": node_payloads,
            "edges": ordered_edges,
            "truncated": truncated,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "unresolved_count": run.unresolved_reference_count + run.ambiguous_reference_count,
        }
        if seeds is not None:
            response["query"] = {
                "node_id": next(iter(seeds)) if seeds else None,
                "direction": direction,
                "depth": depth,
            }
        return response

    @staticmethod
    def _module_ids(symbols: list[Symbol]) -> dict[str, str]:
        """file_path → module symbol id (module nodes exist for every file)."""
        return {s.file_path: s.id for s in symbols if s.kind == "module"}

    def _merge_edge(self, collapsed: dict, key: tuple[str, str, str], edge: _StoredEdge) -> None:
        entry = collapsed.get(key)
        if entry is None:
            collapsed[key] = {
                "kind": edge.kind,
                "confidence": edge.confidence,
                "resolver": edge.resolver,
                "evidence": list(edge.evidence),
            }
            return
        if (_CONFIDENCE_RANK.get(edge.confidence, 99), edge.resolver) < (
            _CONFIDENCE_RANK.get(entry["confidence"], 99),
            entry["resolver"],
        ):
            entry["confidence"] = edge.confidence
            entry["resolver"] = edge.resolver
        for item in edge.evidence:
            if len(entry["evidence"]) >= self._settings.analysis_max_evidence_per_edge:
                break
            entry["evidence"].append(item)

    # --------------------------------------------------------------- networkx
    @staticmethod
    def _dependency_nx(symbols: list[Symbol], stored: list[_StoredEdge]) -> nx.DiGraph:
        """Symbol-level dependency graph (no CONTAINS) for node detail."""
        graph = nx.DiGraph()
        for symbol in symbols:
            graph.add_node(symbol.id)
        for edge in stored:
            if edge.kind in DEPENDENCY_KIND_SET:
                graph.add_edge(edge.source_id, edge.target_id)
        return graph

    @staticmethod
    def _collapsed_dependency_nx(collapsed: dict, served_ids: set[str]) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node_id in served_ids:
            graph.add_node(node_id)
        for (source_id, target_id, kind) in collapsed:
            if kind in DEPENDENCY_KIND_SET:
                graph.add_edge(source_id, target_id)
        return graph

    def _metrics_map(self, graph: nx.DiGraph, served_ids: set[str]) -> dict[str, dict]:
        """in/out degree plus reachability while inside the metrics budget."""
        if len(graph) > self._settings.graph_metrics_max_nodes:
            return {
                node: {"in_degree": int(graph.in_degree(node)), "out_degree": int(graph.out_degree(node))}
                for node in served_ids
            }
        downstream, upstream = self._reachable_maps(graph)
        metrics: dict[str, dict] = {}
        for node in served_ids:
            metrics[node] = {
                "in_degree": int(graph.in_degree(node)),
                "out_degree": int(graph.out_degree(node)),
                "upstream_reachable": upstream.get(node, 0),
                "downstream_reachable": downstream.get(node, 0),
            }
        return metrics

    def _metrics_for(self, graph: nx.DiGraph, node_id: str) -> dict:
        """Metrics for a single node (node detail path)."""
        if len(graph) > self._settings.graph_metrics_max_nodes:
            return {"in_degree": int(graph.in_degree(node_id)), "out_degree": int(graph.out_degree(node_id))}
        downstream, upstream = self._reachable_maps(graph)
        return {
            "in_degree": int(graph.in_degree(node_id)),
            "out_degree": int(graph.out_degree(node_id)),
            "upstream_reachable": upstream.get(node_id, 0),
            "downstream_reachable": downstream.get(node_id, 0),
        }

    @staticmethod
    def _reachable_maps(graph: nx.DiGraph) -> tuple[dict[str, int], dict[str, int]]:
        """Exact reachable counts via SCC condensation; cycle-safe and bounded.

        Uses one condensation of the dependency graph and memoized unions over
        the resulting DAG, so all nodes are answered in O(V + E + result) and
        cycles can never loop the computation.
        """
        nodes = list(graph.nodes())
        if not nodes:
            return {}, {}
        condensed = nx.condensation(graph)
        sizes = {comp: len(condensed.nodes[comp]["members"]) for comp in condensed.nodes()}
        downstream_comp: dict[int, frozenset[int]] = {}
        for comp in reversed(list(nx.topological_sort(condensed))):
            reachable = {comp}
            for successor in condensed.successors(comp):
                reachable |= downstream_comp[successor]
            downstream_comp[comp] = frozenset(reachable)
        comp_of = {}
        for comp, members in condensed.nodes(data="members"):
            for member in members:
                comp_of[member] = comp
        downstream: dict[str, int] = {}
        upstream: dict[str, int] = {}
        for node in nodes:
            comp = comp_of[node]
            count = sum(sizes[item] for item in downstream_comp[comp])
            downstream[node] = count - 1 if count > 0 else 0  # exclude the node itself
        # Upstream: same DP on the reversed condensation.
        upstream_comp: dict[int, frozenset[int]] = {}
        condensed_reverse = condensed.reverse(copy=True)
        for comp in reversed(list(nx.topological_sort(condensed_reverse))):
            reachable = {comp}
            for successor in condensed_reverse.successors(comp):
                reachable |= upstream_comp[successor]
            upstream_comp[comp] = frozenset(reachable)
        for node in nodes:
            comp = comp_of[node]
            count = sum(sizes[item] for item in upstream_comp[comp])
            upstream[node] = count - 1 if count > 0 else 0
        return downstream, upstream

    def _neighborhood(
        self,
        graph: nx.DiGraph,
        node_id: str,
        direction: str,
        depth: int,
    ) -> list[str]:
        """Deterministic BFS (sorted frontiers, visited-set cycle protection)."""
        visited: set[str] = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier:
                if direction in ("downstream", "both"):
                    next_frontier.update(graph.successors(current))
                if direction in ("upstream", "both"):
                    next_frontier.update(graph.predecessors(current))
            next_frontier -= visited
            if not next_frontier:
                break
            visited |= next_frontier
            frontier = next_frontier
        visited.discard(node_id)
        return sorted(visited)

    # -------------------------------------------------------------- payloads
    def _node_payload(self, symbol: Symbol, metrics: dict | None) -> dict:
        from app.schemas.serializers import symbol_view

        payload = symbol_view(symbol)
        payload["metrics"] = metrics or {}
        payload["coverage_status"] = "unknown"  # coverage lands in Phase 7A
        return payload

    _view_edge_id = staticmethod(view_edge_id)
