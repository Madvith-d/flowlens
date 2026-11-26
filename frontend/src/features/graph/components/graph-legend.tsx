import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Graph legend. Encodes every visual distinction in text next to a swatch —
 * status is never carried by color alone. Node kind colors/shapes mirror
 * `graph-canvas.tsx`.
 */
export function GraphLegend() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Legend</CardTitle>
        <CardDescription>What the canvas symbols and lines mean.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="mb-1.5 text-sm font-medium">Node kinds</p>
          <ul className="space-y-1 text-sm">
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block size-3 rounded bg-[#64748b]" />
              module — file/module level
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block size-3 rounded-full bg-[#7c3aed]" />
              class
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block size-3 rotate-45 bg-[#0e7490]" />
              function
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block size-3 rounded-r-full rounded-l-sm bg-[#b45309]" />
              method
            </li>
          </ul>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Edges</p>
          <ul className="space-y-1 text-sm">
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block h-0.5 w-6 bg-[#94a3b8]" />
              dependency edge — CALLS, IMPORTS, INHERITS, REFERENCES (arrow points to the dependency)
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block h-0.5 w-6 bg-[#cbd5e1]" />
              CONTAINS — structural containment, not a dependency
            </li>
            <li className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-block h-0.5 w-6 border-t-2 border-dashed border-[#94a3b8]"
              />
              low-confidence resolution (see the details panel for evidence)
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block h-1 w-6 rounded bg-[#2563eb]" />
              selected node or edge
            </li>
          </ul>
        </div>
        <p className="text-xs text-muted-foreground">
          Edges are statically inferred and some may be ambiguous or unresolved —
          FlowLens shows this uncertainty instead of inventing relationships.
        </p>
      </CardContent>
    </Card>
  );
}
