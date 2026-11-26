"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { CoverageStatusBadge } from "@/features/coverage/components/coverage-status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { GraphEdge, GraphNode } from "@/types/api";

/**
 * Accessible list/table alternative to the canvas: the same bounded graph
 * data as keyboard-navigable tables with kind text (never color-only).
 * Selecting a row mirrors canvas selection.
 */
export function GraphListView({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId,
  showCoverage,
  impactTargets,
  impactDirect,
  impactIndirect,
  onSelectNode,
  onSelectEdge,
}: {
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Impact target/direct/indirect node IDs from a real impact result. */
  /** Show the coverage column when the graph reports coverage statuses. */
  showCoverage?: boolean;
  impactTargets?: ReadonlySet<string>;
  impactDirect?: ReadonlySet<string>;
  impactIndirect?: ReadonlySet<string>;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
}) {
  const nodeById = React.useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of nodes) map.set(node.id, node);
    return map;
  }, [nodes]);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Nodes</CardTitle>
          <CardDescription>{nodes.length} visible nodes in this graph view.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Graph nodes</caption>
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Name</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Qualified name</th>
                  <th scope="col" className="py-2 pr-4 font-medium">File</th>
                  {showCoverage ? (
                    <th scope="col" className="py-2 pr-4 font-medium">Coverage</th>
                  ) : null}
                  {impactTargets || impactDirect || impactIndirect ? (
                    <th scope="col" className="py-2 font-medium">Impact</th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => {
                  const isSelected = node.id === selectedNodeId;
                  const isImpactTarget = impactTargets?.has(node.id) ?? false;
                  const isDirect = impactDirect?.has(node.id) ?? false;
                  const isIndirect = impactIndirect?.has(node.id) ?? false;
                  return (
                    <tr
                      key={node.id}
                      aria-selected={isSelected}
                      tabIndex={0}
                      className={`cursor-pointer border-b transition-colors hover:bg-muted/50 ${isSelected ? "bg-accent" : ""}`}
                      onClick={() => onSelectNode(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelectNode(node.id);
                        }
                      }}
                    >
                      <td className="py-2 pr-4 align-top">{node.kind}</td>
                      <td className="py-2 pr-4 align-top font-medium">{node.name}</td>
                      <td className="py-2 pr-4 align-top">
                        <code className="text-xs">{node.qualified_name}</code>
                      </td>
                      <td className="py-2 pr-4 align-top text-xs">
                        {node.file_path}
                        {node.location ? ` · lines ${node.location.start_line}–${node.location.end_line}` : ""}
                      </td>
                      {showCoverage ? (
                        <td className="py-2 pr-4 align-top">
                          <CoverageStatusBadge status={node.coverage_status} />
                        </td>
                      ) : null}
                      {impactTargets || impactDirect || impactIndirect ? (
                        <td className="py-2 align-top">
                          {isImpactTarget ? (
                            <Badge>target</Badge>
                          ) : isDirect ? (
                            <Badge variant="success">direct impact</Badge>
                          ) : isIndirect ? (
                            <Badge variant="warning">indirect impact</Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">not impacted</span>
                          )}
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Relationships</CardTitle>
          <CardDescription>{edges.length} visible edges in this graph view.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Graph edges and their evidence</caption>
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
                  <th scope="col" className="py-2 pr-4 font-medium">From → to</th>
                  <th scope="col" className="py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {edges.map((edge) => {
                  const isSelected = edge.id === selectedEdgeId;
                  const source = nodeById.get(edge.source);
                  const target = nodeById.get(edge.target);
                  return (
                    <tr
                      key={edge.id}
                      aria-selected={isSelected}
                      tabIndex={0}
                      className={`cursor-pointer border-b transition-colors hover:bg-muted/50 ${isSelected ? "bg-accent" : ""}`}
                      onClick={() => onSelectEdge(edge.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelectEdge(edge.id);
                        }
                      }}
                    >
                      <td className="py-2 pr-4 align-top">
                        {edge.kind}
                        {edge.kind === "CONTAINS" ? (
                          <span className="text-xs text-muted-foreground"> (structural)</span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-4 align-top">
                        <code className="text-xs">{source?.name ?? edge.source}</code>
                        <span aria-hidden="true"> → </span>
                        <code className="text-xs">{target?.name ?? edge.target}</code>
                      </td>
                      <td className="py-2 align-top">
                        <Badge variant={edge.confidence === "low" ? "warning" : "secondary"}>
                          {edge.confidence}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
