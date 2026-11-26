"use client";

import * as React from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { EdgeKind, GraphView, NodeKind } from "@/types/api";

/**
 * Graph filter controls. Everything maps 1:1 to documented query parameters
 * of `GET /api/v1/analyses/{analysis_id}/graph` — the server applies the
 * filtering; the client never trims or hides server results itself.
 *
 * The default sends no node/edge kind filters (backend default: all kinds).
 */

const NODE_KIND_OPTIONS: ReadonlyArray<NodeKind> = ["module", "class", "function", "method"];
const EDGE_KIND_OPTIONS: ReadonlyArray<EdgeKind> = ["CALLS", "IMPORTS", "INHERITS", "REFERENCES", "CONTAINS"];
const VIEW_OPTIONS: ReadonlyArray<{ value: GraphView; label: string; description: string }> = [
  { value: "module", label: "File / module", description: "Module-level nodes" },
  { value: "class", label: "Class", description: "Classes and their relations" },
  { value: "function", label: "Function / method", description: "Functions and methods (contract default)" },
];
const LIMIT_OPTIONS = [100, 500, 1000, 2000] as const;

export interface GraphFilterState {
  view: GraphView;
  nodeKinds: readonly NodeKind[];
  edgeKinds: readonly EdgeKind[];
  limit: number;
}

export const DEFAULT_GRAPH_FILTERS: GraphFilterState = {
  view: "function",
  nodeKinds: [],
  edgeKinds: [],
  limit: 500,
};

export function GraphFilters({
  filters,
  onChange,
}: {
  filters: GraphFilterState;
  onChange: (next: GraphFilterState) => void;
}) {
  const toggleKind = <T extends string>(list: readonly T[], kind: T): readonly T[] =>
    list.includes(kind) ? list.filter((item) => item !== kind) : [...list, kind];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Graph filters</CardTitle>
        <CardDescription>
          Filters are applied by the backend; results stay bounded by its limits.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset>
          <legend className="text-sm font-medium">View level</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {VIEW_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm has-[:checked]:bg-accent"
              >
                <input
                  type="radio"
                  name="graph-view"
                  value={option.value}
                  checked={filters.view === option.value}
                  onChange={() => onChange({ ...filters, view: option.value })}
                />
                <span title={option.description}>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-medium">Node kinds</legend>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
            {NODE_KIND_OPTIONS.map((kind) => (
              <label key={kind} className="flex cursor-pointer items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={filters.nodeKinds.includes(kind)}
                  onChange={() =>
                    onChange({ ...filters, nodeKinds: toggleKind(filters.nodeKinds, kind) })
                  }
                />
                {kind}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Unchecked everywhere means all kinds (backend default).
          </p>
        </fieldset>

        <fieldset>
          <legend className="text-sm font-medium">Edge kinds</legend>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
            {EDGE_KIND_OPTIONS.map((kind) => (
              <label
                key={kind}
                className="flex cursor-pointer items-center gap-1.5 text-sm"
                title={
                  kind === "CONTAINS"
                    ? "Structural containment, not a dependency"
                    : `Include ${kind} edges`
                }
              >
                <input
                  type="checkbox"
                  checked={filters.edgeKinds.includes(kind)}
                  onChange={() =>
                    onChange({ ...filters, edgeKinds: toggleKind(filters.edgeKinds, kind) })
                  }
                />
                {kind}
                {kind === "CONTAINS" ? (
                  <span className="text-xs text-muted-foreground">(structural)</span>
                ) : null}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="max-w-48">
          <label htmlFor="graph-limit" className="text-sm font-medium">
            Node limit
          </label>
          <select
            id="graph-limit"
            className="mt-1 h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            value={filters.limit}
            onChange={(event) => onChange({ ...filters, limit: Number(event.target.value) })}
          >
            {LIMIT_OPTIONS.map((limit) => (
              <option key={limit} value={limit}>
                up to {limit} nodes
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            The server may still return fewer nodes; it flags truncation honestly.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
