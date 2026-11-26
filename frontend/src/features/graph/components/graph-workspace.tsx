"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Network, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/lib/use-async";
import { getGraph, getNode, getNodeNeighbors, graphLoadError } from "@/features/graph/graph-service";
import {
  DEFAULT_GRAPH_FILTERS,
  GraphFilters as GraphFilterControls,
  type GraphFilterState,
} from "@/features/graph/components/graph-filters";
import { GraphCanvas } from "@/features/graph/components/graph-canvas";
import { GraphLegend } from "@/features/graph/components/graph-legend";
import { GraphListView } from "@/features/graph/components/graph-list-view";
import { GraphSearch } from "@/features/graph/components/graph-search";
import {
  EdgeDetailsPanel,
  NodeDetailsPanel,
} from "@/features/graph/components/node-details-panel";
import type {
  GraphEdge,
  GraphNode,
  GraphResponse,
  ImpactDirection,
} from "@/types/api";

/**
 * Interactive dependency graph workspace (Phase 5B).
 *
 * Everything rendered comes from the graph endpoint group in the contract:
 * the filtered graph, node detail, and bounded neighbor expansion. The base
 * graph is always a bounded server response (`truncated` respected); neighbor
 * expansions are merged additively into the visible graph. No edge, metric,
 * or neighbor is invented client-side.
 */
export function GraphWorkspace({
  projectId,
  analysisId,
  projectName,
}: {
  projectId: string;
  analysisId: string;
  projectName: string;
}) {
  const [filters, setFilters] = React.useState<GraphFilterState>(DEFAULT_GRAPH_FILTERS);

  // Additive neighbor-expansion data merged on top of the server-filtered
  // base graph. Reset whenever the base request changes.
  const [extraNodes, setExtraNodes] = React.useState<GraphNode[]>([]);
  const [extraEdges, setExtraEdges] = React.useState<GraphEdge[]>([]);
  const [expandedTruncated, setExpandedTruncated] = React.useState(false);

  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = React.useState<string | null>(null);
  const [displayMode, setDisplayMode] = React.useState<"canvas" | "table">("canvas");

  const filterKey = [
    filters.view,
    [...filters.nodeKinds].sort().join(","),
    [...filters.edgeKinds].sort().join(","),
    filters.limit,
  ].join("|");

  const base = useAsync(
    async () => {
      try {
        return await getGraph(analysisId, {
          view: filters.view,
          nodeKinds: filters.nodeKinds,
          edgeKinds: filters.edgeKinds,
          limit: filters.limit,
        });
      } catch (cause) {
        // Wrap so `useAsync` surfaces the graph-specific message
        // (e.g. ANALYSIS_NOT_READY) instead of the generic one.
        throw new Error(graphLoadError(cause));
      }
    },
    // Refetch is driven by `filterKey` (useAsync ignores loader identity).
    [analysisId, filterKey]
  );

  // A new base request invalidates merged expansions and the selection.
  React.useEffect(() => {
    setExtraNodes([]);
    setExtraEdges([]);
    setExpandedTruncated(false);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, [analysisId, filterKey]);

  const mergeGraphResponse = React.useCallback((response: GraphResponse) => {
    setExtraNodes((current) => {
      const seen = new Set(current.map((node) => node.id));
      const additions = response.nodes.filter((node) => !seen.has(node.id));
      return additions.length > 0 ? [...current, ...additions] : current;
    });
    setExtraEdges((current) => {
      const seen = new Set(current.map((edge) => edge.id));
      const additions = response.edges.filter((edge) => !seen.has(edge.id));
      return additions.length > 0 ? [...current, ...additions] : current;
    });
  }, []);

  const mergeNode = React.useCallback((node: GraphNode) => {
    setExtraNodes((current) => {
      if (current.some((item) => item.id === node.id)) return current;
      return [...current, node];
    });
  }, []);

  // ---- merged visible graph -------------------------------------------------
  const visibleNodes = React.useMemo(() => {
    const seen = new Set<string>();
    const merged: GraphNode[] = [];
    for (const node of base.data?.nodes ?? []) {
      seen.add(node.id);
      merged.push(node);
    }
    for (const node of extraNodes) {
      if (!seen.has(node.id)) merged.push(node);
    }
    return merged;
  }, [base.data, extraNodes]);

  const visibleEdges = React.useMemo(() => {
    const seen = new Set<string>();
    const merged: GraphEdge[] = [];
    for (const edge of base.data?.edges ?? []) {
      seen.add(edge.id);
      merged.push(edge);
    }
    for (const edge of extraEdges) {
      if (!seen.has(edge.id)) merged.push(edge);
    }
    return merged;
  }, [base.data, extraEdges]);

  const nodeById = React.useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of visibleNodes) map.set(node.id, node);
    return map;
  }, [visibleNodes]);

  // ---- selection -------------------------------------------------------------
  const selectNode = React.useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) setSelectedEdgeId(null);
  }, []);

  const selectEdge = React.useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    if (edgeId) setSelectedNodeId(null);
  }, []);

  // Fresh node detail from `GET /nodes/{node_id}` for the details panel.
  const [detailNonce, setDetailNonce] = React.useState(0);
  const nodeDetail = useAsync(
    async () => {
      if (!selectedNodeId) return null;
      try {
        return await getNode(analysisId, selectedNodeId);
      } catch (cause) {
        throw new Error(graphLoadError(cause));
      }
    },
    [selectedNodeId, detailNonce]
  );

  // Merge the fresh detail node so a picked symbol is always visible in the
  // graph even when it is outside the current server-filtered base graph.
  React.useEffect(() => {
    if (nodeDetail.data) mergeNode(nodeDetail.data);
  }, [nodeDetail.data, mergeNode]);

  // On selection, fetch 1-hop neighbors so callers/callees exist regardless
  // of what the filtered base graph included.
  const neighbors = useAsync(
    () =>
      selectedNodeId
        ? getNodeNeighbors(analysisId, selectedNodeId, { depth: 1, direction: "both" })
        : Promise.resolve(null as GraphResponse | null),
    [selectedNodeId]
  );

  React.useEffect(() => {
    if (neighbors.data) {
      mergeGraphResponse(neighbors.data);
      if (neighbors.data.truncated) setExpandedTruncated(true);
    }
  }, [neighbors.data, mergeGraphResponse]);

  // ---- manual expansion controls ----------------------------------------------
  const [expandDepth, setExpandDepth] = React.useState(1);
  const [expandDirection, setExpandDirection] = React.useState<ImpactDirection>("both");
  const [expandBusy, setExpandBusy] = React.useState(false);
  const [expandError, setExpandError] = React.useState<string | null>(null);

  const expandNeighbors = async () => {
    if (!selectedNodeId) return;
    setExpandBusy(true);
    setExpandError(null);
    try {
      const response = await getNodeNeighbors(analysisId, selectedNodeId, {
        depth: expandDepth,
        direction: expandDirection,
      });
      // The new expansion replaces the previous truncation note honestly.
      setExpandedTruncated(response.truncated);
      const addedNodes = response.nodes.length;
      const addedEdges = response.edges.length;
      mergeGraphResponse(response);
      toast.success("Neighborhood expanded", {
        description: `Merged ${addedNodes} node${addedNodes === 1 ? "" : "s"} and ${addedEdges} edge${addedEdges === 1 ? "" : "s"} into the visible graph.`,
      });
    } catch (cause) {
      setExpandError(graphLoadError(cause));
    } finally {
      setExpandBusy(false);
    }
  };

  const baseGraph = base.data;
  const selectedEdge = selectedEdgeId
    ? visibleEdges.find((edge) => edge.id === selectedEdgeId) ?? null
    : null;

  const totalNodes = baseGraph?.total_nodes;
  const visibleNodeCount = visibleNodes.length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={`/projects/${projectId}/workspace`}>
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to workspace
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="-mr-2">
          <Link href="/dashboard">All projects</Link>
        </Button>
      </div>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          <Network aria-hidden="true" className="mr-2 inline size-5" />
          Dependency graph — {projectName}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Statically inferred relationships from the completed analysis.{" "}
          <code className="text-xs" title={analysisId}>
            analysis {analysisId.slice(0, 8)}
          </code>
        </p>
      </div>

      <GraphFilterControls filters={filters} onChange={setFilters} />

      <GraphSearch analysisId={analysisId} onPick={(symbolId) => selectNode(symbolId)} />

      {/* Base-graph truncation and unresolved-reference notices (server truth). */}
      {baseGraph?.truncated ? (
        <Alert>
          <TriangleAlert aria-hidden="true" className="size-4" />
          <AlertTitle>Partial graph</AlertTitle>
          <AlertDescription>
            The server limited this result
            {typeof totalNodes === "number"
              ? ` — showing ${visibleNodeCount} of ${totalNodes} nodes.`
              : "."}{" "}
            Narrow the filters, lower the node limit, or expand specific nodes instead of
            requesting the whole graph.
          </AlertDescription>
        </Alert>
      ) : null}
      {typeof baseGraph?.unresolved_count === "number" && baseGraph.unresolved_count > 0 ? (
        <p className="text-sm text-muted-foreground">
          {baseGraph.unresolved_count} unresolved or ambiguous reference
          {baseGraph.unresolved_count === 1 ? "" : "s"} were recorded in diagnostics — they are
          shown as diagnostics, not as invented edges.
        </p>
      ) : null}

      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Graph display mode</legend>
        <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm has-[:checked]:bg-accent">
          <input
            type="radio"
            name="graph-display-mode"
            checked={displayMode === "canvas"}
            onChange={() => setDisplayMode("canvas")}
          />
          Canvas
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm has-[:checked]:bg-accent">
          <input
            type="radio"
            name="graph-display-mode"
            checked={displayMode === "table"}
            onChange={() => setDisplayMode("table")}
          />
          Table (accessible list view)
        </label>
      </fieldset>

      {base.loading ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading dependency graph">
          <Skeleton className="h-[420px] w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : base.error ? (
        <ErrorState
          title="Could not load the dependency graph"
          message={base.error ?? "The dependency graph could not be loaded."}
          onRetry={base.reload}
        />
      ) : !baseGraph ? null : baseGraph.nodes.length === 0 ? (
        <EmptyState
          title="No nodes in this graph view"
          description="The analysis has no nodes matching the current view and kind filters. Try a different view level, clear the kind filters, or widen the node limit."
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {visibleNodeCount} visible node{visibleNodeCount === 1 ? "" : "s"} ·{" "}
            {visibleEdges.length} visible edge{visibleEdges.length === 1 ? "" : "s"}
          </p>

          {displayMode === "canvas" ? (
            <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
              <GraphCanvas
                nodes={visibleNodes}
                edges={visibleEdges}
                selectedNodeId={selectedNodeId}
                selectedEdgeId={selectedEdgeId}
                onSelectNode={selectNode}
                onSelectEdge={selectEdge}
              />
              <GraphLegend />
            </div>
          ) : (
            <GraphListView
              nodes={visibleNodes}
              edges={visibleEdges}
              selectedNodeId={selectedNodeId}
              selectedEdgeId={selectedEdgeId}
              onSelectNode={(id) => selectNode(id)}
              onSelectEdge={(id) => selectEdge(id)}
            />
          )}
        </>
      )}

      {/* Details: node when a node is selected, edge when an edge is selected. */}
      {selectedNodeId ? (
        <>
          <NodeDetailsPanel
            node={nodeDetail.data}
            loading={nodeDetail.loading}
            loadError={nodeDetail.error}
            onRetry={() => {
              setDetailNonce((nonce) => nonce + 1);
            }}
            edges={visibleEdges}
            nodeById={nodeById}
            expandedTruncated={expandedTruncated}
            expandBusy={expandBusy}
            expandError={expandError}
            onExpand={() => void expandNeighbors()}
            expandDepth={expandDepth}
            expandDirection={expandDirection}
            onExpandDepthChange={setExpandDepth}
            onExpandDirectionChange={setExpandDirection}
            onSelectNode={(nodeId) => selectNode(nodeId)}
            onSelectEdge={(edgeId) => selectEdge(edgeId)}
          />
          {neighbors.error ? (
            <Card role="alert" className="border-destructive/40">
              <CardHeader>
                <CardTitle className="text-sm text-destructive">
                  Could not load this node&apos;s direct neighbors
                </CardTitle>
                <CardDescription>
                  {neighbors.error} The graph itself is unaffected; callers/callees lists
                  below reflect the currently merged graph data only.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" size="sm" onClick={neighbors.reload}>
                  Try again
                </Button>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : selectedEdge ? (
        <EdgeDetailsPanel
          edge={selectedEdge}
          nodeById={nodeById}
          onSelectNode={(nodeId) => selectNode(nodeId)}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          Select a node (search above, click the canvas, or pick a table row) to inspect its
          relationships, metrics, and edge evidence.
        </p>
      )}
    </div>
  );
}
