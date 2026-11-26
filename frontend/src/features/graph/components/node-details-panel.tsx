"use client";

import * as React from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Confidence,
  CoverageStatus,
  GraphEdge,
  GraphNode,
  ImpactDirection,
} from "@/types/api";

/**
 * Selected-node details: qualified identity, source location, metrics,
 * coverage status, direct callers/callees with edge evidence, and bounded
 * neighbor expansion. All values come from the graph/node/neighbor endpoints;
 * absent values render as "unknown", never as zero.
 */
export function NodeDetailsPanel({
  node,
  loading,
  loadError,
  edges,
  nodeById,
  onRetry,
  onSelectNode,
  onSelectEdge,
  expandedTruncated,
  expandBusy,
  expandError,
  onExpand,
  expandDepth,
  expandDirection,
  onExpandDepthChange,
  onExpandDirectionChange,
}: {
  /** Fresh detail from `GET /nodes/{node_id}` — null while loading/absent. */
  node: GraphNode | null;
  loading: boolean;
  loadError: string | null;
  /** Current merged edges (base graph + neighbor expansions). */
  edges: readonly GraphEdge[];
  /** Node lookup by ID (merged) for callers/callees names. */
  nodeById: ReadonlyMap<string, GraphNode>;
  onRetry: () => void;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  expandedTruncated: boolean;
  expandBusy: boolean;
  expandError: string | null;
  onExpand: () => void;
  expandDepth: number;
  expandDirection: ImpactDirection;
  onExpandDepthChange: (depth: number) => void;
  onExpandDirectionChange: (direction: ImpactDirection) => void;
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Node details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2" aria-busy="true">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (loadError) {
    return (
      <Card role="alert" className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">Could not load node details</CardTitle>
          <CardDescription>{loadError}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!node) return null;

  const { incoming, outgoing } = incidentEdges(edges, node.id);

  return (
    <Card id="node-details">
      <CardHeader>
        <CardTitle className="font-mono text-base">{node.qualified_name}</CardTitle>
        <CardDescription>
          Selected node — {node.kind} in <code className="text-xs">{node.file_path}</code>
          {node.location ? ` · lines ${node.location.start_line}–${node.location.end_line}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Kind</dt>
          <dd>{node.kind}</dd>
          <dt className="text-muted-foreground">Node ID</dt>
          <dd>
            <code className="text-xs">{node.id}</code>
          </dd>
          <dt className="text-muted-foreground">In-degree / out-degree</dt>
          <dd>
            {node.metrics
              ? `${node.metrics.in_degree} / ${node.metrics.out_degree}`
              : "unknown"}
          </dd>
          {node.metrics ? (
            <>
              <dt className="text-muted-foreground">Reachable upstream / downstream</dt>
              <dd>
                {formatOrUnknown(node.metrics.upstream_reachable)} /{" "}
                {formatOrUnknown(node.metrics.downstream_reachable)}
              </dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Coverage</dt>
          <dd>
            <CoverageBadge status={node.coverage_status} />
          </dd>
        </dl>

        <NeighborList
          title="Direct callers (upstream)"
          emptyNote="No direct callers found in the current graph data."
          pairs={incoming}
          nodeById={nodeById}
          onSelectNode={onSelectNode}
          onSelectEdge={onSelectEdge}
        />
        <NeighborList
          title="Direct callees / dependencies (downstream)"
          emptyNote="No direct dependencies found in the current graph data."
          pairs={outgoing}
          nodeById={nodeById}
          onSelectNode={onSelectNode}
          onSelectEdge={onSelectEdge}
        />

        <fieldset className="space-y-2 rounded-md border p-3">
          <legend className="text-sm font-medium">Expand neighborhood</legend>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label htmlFor="expand-depth" className="text-xs text-muted-foreground">
                Depth
              </label>
              <select
                id="expand-depth"
                className="mt-1 h-9 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                value={expandDepth}
                onChange={(event) => onExpandDepthChange(Number(event.target.value))}
              >
                <option value={1}>1 hop</option>
                <option value={2}>2 hops</option>
                <option value={3}>3 hops</option>
              </select>
            </div>
            <div>
              <label htmlFor="expand-direction" className="text-xs text-muted-foreground">
                Direction
              </label>
              <select
                id="expand-direction"
                className="mt-1 h-9 rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                value={expandDirection}
                onChange={(event) =>
                  onExpandDirectionChange(event.target.value as ImpactDirection)
                }
              >
                <option value="both">both</option>
                <option value="upstream">callers</option>
                <option value="downstream">dependencies</option>
              </select>
            </div>
            <Button size="sm" onClick={onExpand} disabled={expandBusy}>
              {expandBusy ? "Expanding…" : "Expand neighbors"}
            </Button>
          </div>
          {expandError ? (
            <p role="alert" className="text-sm text-destructive">
              {expandError}
            </p>
          ) : null}
          {expandedTruncated ? (
            <p className="text-xs text-muted-foreground">
              The server limited this expansion — try a smaller depth or use upstream/downstream
              only.
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Expansion uses the bounded neighbor endpoint; the server stops at its own limits and
            flags truncation.
          </p>
        </fieldset>
      </CardContent>
    </Card>
  );
}

/** Group incident edges of `nodeId` into upstream (incoming) and outgoing. */
function incidentEdges(edges: readonly GraphEdge[], nodeId: string): {
  incoming: Array<{ edge: GraphEdge; otherId: string }>;
  outgoing: Array<{ edge: GraphEdge; otherId: string }>;
} {
  const incoming: Array<{ edge: GraphEdge; otherId: string }> = [];
  const outgoing: Array<{ edge: GraphEdge; otherId: string }> = [];
  for (const edge of edges) {
    if (edge.target === nodeId) incoming.push({ edge, otherId: edge.source });
    else if (edge.source === nodeId) outgoing.push({ edge, otherId: edge.target });
  }
  return { incoming, outgoing };
}

function NeighborList({
  title,
  emptyNote,
  pairs,
  nodeById,
  onSelectNode,
  onSelectEdge,
}: {
  title: string;
  emptyNote: string;
  pairs: ReadonlyArray<{ edge: GraphEdge; otherId: string }>;
  nodeById: ReadonlyMap<string, GraphNode>;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium">{title}</p>
      {pairs.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyNote}</p>
      ) : (
        <ul className="space-y-1">
          {pairs.map(({ edge, otherId }) => {
            const other = nodeById.get(otherId);
            return (
              <li
                key={edge.id}
                className="flex flex-wrap items-center gap-2 rounded-md border px-2 py-1.5 text-sm"
              >
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-auto justify-start px-1 py-0.5"
                  onClick={() => onSelectNode(otherId)}
                  title={other ? other.qualified_name : otherId}
                >
                  <code className="text-xs">{other?.qualified_name ?? otherId}</code>
                </Button>
                <Badge variant="outline">{edge.kind}</Badge>
                <ConfidenceLabel confidence={edge.confidence} />
                {edge.evidence.length > 0 ? (
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs text-muted-foreground underline-offset-2"
                    onClick={() => onSelectEdge(edge.id)}
                  >
                    evidence: {edge.evidence[0].file_path}:{edge.evidence[0].line}
                    {edge.evidence.length > 1 ? ` (+${edge.evidence.length - 1} more)` : ""}
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">no evidence reported</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Edge details: type, confidence, resolver, and every evidence location. */
export function EdgeDetailsPanel({
  edge,
  nodeById,
  onSelectNode,
}: {
  edge: GraphEdge;
  nodeById: ReadonlyMap<string, GraphNode>;
  onSelectNode: (nodeId: string) => void;
}) {
  const source = nodeById.get(edge.source);
  const target = nodeById.get(edge.target);
  return (
    <Card id="edge-details">
      <CardHeader>
        <CardTitle className="text-base">Edge details</CardTitle>
        <CardDescription>
          {edge.kind}
          {edge.kind === "CONTAINS" ? " — structural containment, not a dependency" : ""} edge
          with {edge.confidence} confidence.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">From</dt>
          <dd>
            <button
              type="button"
              className="font-mono text-xs underline underline-offset-2"
              onClick={() => onSelectNode(edge.source)}
            >
              {source?.qualified_name ?? edge.source}
            </button>
          </dd>
          <dt className="text-muted-foreground">To</dt>
          <dd>
            <button
              type="button"
              className="font-mono text-xs underline underline-offset-2"
              onClick={() => onSelectNode(edge.target)}
            >
              {target?.qualified_name ?? edge.target}
            </button>
          </dd>
          <dt className="text-muted-foreground">Confidence</dt>
          <dd>
            <ConfidenceLabel confidence={edge.confidence} />
          </dd>
          {edge.resolver ? (
            <>
              <dt className="text-muted-foreground">Resolver</dt>
              <dd>
                <code className="text-xs">{edge.resolver}</code>
              </dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Edge ID</dt>
          <dd>
            <code className="text-xs">{edge.id}</code>
          </dd>
        </dl>

        <div>
          <p className="mb-1.5 text-sm font-medium">Source evidence</p>
          {edge.evidence.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              The backend did not report evidence for this edge.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {edge.evidence.map((item, index) => (
                <li key={index} className="rounded-md border px-2 py-1.5 text-sm">
                  <code className="text-xs">
                    {item.file_path}:{item.line}
                    {item.column !== undefined ? `:${item.column}` : ""}
                  </code>
                  {item.expression ? (
                    <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                      {item.expression}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
        <Alert>
          <AlertTitle>Statically inferred</AlertTitle>
          <AlertDescription>
            Static analysis infers edges from source evidence; runtime dispatch may differ.
            Low-confidence edges deserve extra review.
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

function ConfidenceLabel({ confidence }: { confidence: Confidence }) {
  return (
    <Badge variant={confidence === "low" ? "warning" : "secondary"}>
      {confidence} confidence
    </Badge>
  );
}

function CoverageBadge({ status }: { status?: CoverageStatus }) {
  if (!status) {
    return <Badge variant="secondary">unknown</Badge>;
  }
  return (
    <Badge
      variant={
        status === "covered"
          ? "success"
          : status === "uncovered" || status === "partially_covered"
            ? "warning"
            : "secondary"
      }
    >
      {status.replace("_", " ")}
    </Badge>
  );
}

function formatOrUnknown(value: number | undefined): string {
  return typeof value === "number" ? String(value) : "unknown";
}
