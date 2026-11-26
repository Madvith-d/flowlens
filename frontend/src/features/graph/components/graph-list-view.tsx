"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
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
  onSelectNode,
  onSelectEdge,
}: {
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
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
                  <th scope="col" className="py-2 font-medium">File</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => {
                  const isSelected = node.id === selectedNodeId;
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
                      <td className="py-2 align-top text-xs">
                        {node.file_path}
                        {node.location ? ` · lines ${node.location.start_line}–${node.location.end_line}` : ""}
                      </td>
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
