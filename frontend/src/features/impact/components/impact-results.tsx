"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ImpactResult } from "@/types/api";

/**
 * Impacted-symbol list (accessible table view of the impact result).
 * Every row shows direct/indirect, minimum hop distance, and per-target
 * attribution as text — status is never carried by color alone. Selecting
 * a row asks the graph workspace to select the node (node detail + 1-hop
 * neighbors are fetched there) and to show its representative paths.
 */
export function ImpactResults({
  result,
  focusNodeId,
  onSelectImpacted,
}: {
  result: ImpactResult;
  focusNodeId: string | null;
  onSelectImpacted: (nodeId: string) => void;
}) {
  const targetNames = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const target of result.targets) map.set(target.node_id, target.qualified_name);
    return map;
  }, [result.targets]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Impacted symbols</CardTitle>
        <CardDescription>
          {result.impacted.length} impacted symbol{result.impacted.length === 1 ? "" : "s"} within{" "}
          {result.max_depth ?? "the requested"} hop
          {(result.max_depth ?? 2) === 1 ? "" : "s"} (direction: {result.direction}). Select a
          row to inspect its representative path in the graph.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Impacted symbols with direct or indirect status and hop distance
            </caption>
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">Symbol</th>
                <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
                <th scope="col" className="py-2 pr-4 font-medium">Impact</th>
                <th scope="col" className="py-2 pr-4 font-medium">Min hops</th>
                <th scope="col" className="py-2 pr-4 font-medium">Attributed to</th>
                <th scope="col" className="py-2 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {result.impacted.map((impacted) => {
                const isFocused = impacted.node_id === focusNodeId;
                return (
                  <tr
                    key={impacted.node_id}
                    aria-selected={isFocused}
                    tabIndex={0}
                    className={`cursor-pointer border-b transition-colors hover:bg-muted/50 ${isFocused ? "bg-accent" : ""}`}
                    onClick={() => onSelectImpacted(impacted.node_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectImpacted(impacted.node_id);
                      }
                    }}
                  >
                    <td className="py-2 pr-4 align-top">
                      <code className="text-xs">{impacted.qualified_name}</code>
                    </td>
                    <td className="py-2 pr-4 align-top">{impacted.kind}</td>
                    <td className="py-2 pr-4 align-top">
                      {impacted.direct ? (
                        <Badge variant="success">direct</Badge>
                      ) : (
                        <Badge variant="secondary">indirect</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4 align-top tabular-nums">
                      {impacted.min_hops} hop{impacted.min_hops === 1 ? "" : "s"}
                    </td>
                    <td className="py-2 pr-4 align-top text-xs">
                      {impacted.attributed_to
                        .map((id) => targetNames.get(id) ?? id)
                        .join(", ")}
                    </td>
                    <td className="py-2 align-top">
                      <Button
                        variant={isFocused ? "outline" : "ghost"}
                        size="sm"
                        tabIndex={-1}
                        aria-pressed={isFocused}
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectImpacted(impacted.node_id);
                        }}
                      >
                        {isFocused ? "Selected" : "Select in graph"}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
