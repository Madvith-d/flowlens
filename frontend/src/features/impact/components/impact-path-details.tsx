"use client";

import * as React from "react";
import { ArrowRight, Hammer } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { GraphEdge, GraphNode, ImpactPath } from "@/types/api";

/**
 * Representative paths between the focused impacted node and a target.
 *
 * The impact API returns each path as an ordered sequence of edge IDs; the
 * contract offers no fetch-edges-by-ID endpoint, so this component resolves
 * edge IDs against the *currently visible* graph edges for display. Edges
 * outside the visible graph are shown as edge IDs with an honest note —
 * they are never reconstructed, guessed, or hidden.
 */
export function ImpactPathDetails({
  focusQualifiedName,
  focusNodeId,
  paths,
  targetNodeIds,
  edgeById,
  nodeById,
  onSelectEdge,
}: {
  focusQualifiedName: string;
  focusNodeId: string;
  paths: readonly ImpactPath[];
  targetNodeIds: readonly string[];
  edgeById: ReadonlyMap<string, GraphEdge>;
  nodeById: ReadonlyMap<string, GraphNode>;
  onSelectEdge: (edgeId: string) => void;
}) {
  const nodeName = (nodeId: string) => nodeById.get(nodeId)?.qualified_name ?? nodeId;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Hammer aria-hidden="true" className="mr-2 inline size-4" />
          Representative paths — {focusQualifiedName}
        </CardTitle>
        <CardDescription>
          Shortest-hop path{paths.length === 1 ? "" : "s"} returned by the impact analysis. Nodes
          and edges shown here resolve against the currently visible graph; edges outside the
          visible graph appear as bare edge IDs. A static path is not proof that this route
          executes at runtime.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {paths.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            The backend returned no representative path for this symbol — it may be impacted only
            through a route the path selector did not represent.
          </p>
        ) : (
          paths.map((path, pathIndex) => {
            const resolved = path.edges.map((edgeId) => edgeById.get(edgeId) ?? null);
            const first = resolved.find((edge): edge is GraphEdge => edge !== null);
            const last = [...resolved].reverse().find((edge): edge is GraphEdge => edge !== null);

            // Orientation is only stated when it can be read off resolved
            // endpoints: downstream paths run target → impacted, upstream
            // paths run impacted → target. Never inferred otherwise.
            let orientation: "impacted → target" | "target → impacted" | null = null;
            if (first && last) {
              if (first.source === focusNodeId) orientation = "impacted → target";
              else if (last.target === focusNodeId) orientation = "target → impacted";
            }

            return (
              <div
                key={pathIndex}
                className="rounded-md border p-3"
                aria-label={`Representative path ${pathIndex + 1}`}
              >
                <p className="mb-2 text-sm font-medium">
                  Path {pathIndex + 1} — {path.edges.length} edge
                  {path.edges.length === 1 ? "" : "s"}
                  {orientation ? ` · runs ${orientation}` : ""}
                </p>
                <ol className="space-y-1.5">
                  {path.edges.map((edgeId, edgeIndex) => {
                    const edge = edgeById.get(edgeId);
                    if (!edge) {
                      return (
                        <li
                          key={`${edgeId}-${edgeIndex}`}
                          className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
                        >
                          <span className="tabular-nums text-xs">{edgeIndex + 1}.</span>
                          <code className="text-xs">edge {edgeId}</code>
                          <Badge variant="outline">not in the visible graph</Badge>
                          <span className="text-xs">
                            Expand the neighborhood or widen the graph view to inspect this edge.
                          </span>
                        </li>
                      );
                    }
                    const evidence = edge.evidence[0];
                    return (
                      <li
                        key={`${edgeId}-${edgeIndex}`}
                        className="flex flex-wrap items-center gap-2 text-sm"
                      >
                        <span className="tabular-nums text-xs text-muted-foreground">
                          {edgeIndex + 1}.
                        </span>
                        <code className="text-xs">{nodeName(edge.source)}</code>
                        <ArrowRight aria-hidden="true" className="size-3 shrink-0" />
                        <code className="text-xs">{nodeName(edge.target)}</code>
                        <Badge variant={edge.kind === "CONTAINS" ? "outline" : "secondary"}>
                          {edge.kind}
                        </Badge>
                        <Badge variant={edge.confidence === "low" ? "warning" : "secondary"}>
                          {edge.confidence} confidence
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-auto px-2 py-1 text-xs"
                          title={`Evidence: ${evidence ? `${evidence.file_path}:${evidence.line}${evidence.column ? `:${evidence.column}` : ""}` : "no evidence location on this edge"}`}
                          onClick={() => onSelectEdge(edge.id)}
                        >
                          evidence:{" "}
                          {evidence
                            ? `${evidence.file_path}:${evidence.line}`
                            : "none reported"}
                        </Button>
                        {targetNodeIds.includes(edge.target) ? (
                          <span className="text-xs text-muted-foreground">→ reaches a target</span>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
