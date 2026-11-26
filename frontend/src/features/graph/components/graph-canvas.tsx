"use client";

import * as React from "react";
import type cytoscape from "cytoscape";
import { Maximize, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { GraphEdge, GraphNode } from "@/types/api";

/**
 * Cytoscape.js canvas — the sole MVP graph renderer.
 *
 * - Renders exactly the nodes/edges provided (server-filtered and bounded);
 *   it never filters, infers layouts of meaning, or invents data.
 * - Cytoscape is imported dynamically inside the effect so server-side
 *   prerendering never touches browser-only rendering APIs.
 * - Node kind is encoded with shape *and* color *and* a label; legend and the
 *   table alternative carry the same meaning in text (never color-only).
 */
export function GraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId,
  impactTargets,
  impactDirect,
  impactIndirect,
  impactPathEdges,
  onSelectNode,
  onSelectEdge,
}: {
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Impact-target node IDs to outline (from a real impact result). */
  impactTargets?: readonly string[];
  /** Directly impacted node IDs (hop distance 1). */
  impactDirect?: readonly string[];
  /** Indirectly (transitively) impacted node IDs. */
  impactIndirect?: readonly string[];
  /** Edge IDs of the focused representative paths. */
  impactPathEdges?: readonly string[];
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
}) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const cyRef = React.useRef<cytoscape.Core | null>(null);
  const [ready, setReady] = React.useState(false);
  const [renderError, setRenderError] = React.useState<string | null>(null);

  // Latest callbacks in refs: cytoscape event handlers must not go stale.
  const selectNodeRef = React.useRef(onSelectNode);
  selectNodeRef.current = onSelectNode;
  const selectEdgeRef = React.useRef(onSelectEdge);
  selectEdgeRef.current = onSelectEdge;

  // ---- create / destroy instance ------------------------------------------
  React.useEffect(() => {
    let disposed = false;
    let instance: cytoscape.Core | null = null;

    import("cytoscape")
      .then((module) => {
        if (disposed || !containerRef.current) return;
        instance = module.default({
          container: containerRef.current,
          elements: [],
          style: NODE_AND_EDGE_STYLES,
          layout: { name: "grid" },
          wheelSensitivity: 0.2,
        });

        instance.on("select", "node", (event) => {
          selectNodeRef.current(event.target.id());
        });
        instance.on("select", "edge", (event) => {
          selectEdgeRef.current(event.target.id());
        });
        // Clicking empty canvas background clears the selection.
        instance.on("click", (event) => {
          if (event.target === instance) {
            selectNodeRef.current(null);
            selectEdgeRef.current(null);
          }
        });

        cyRef.current = instance;
        setReady(true);
      })
      .catch(() => {
        if (!disposed) {
          setRenderError("The graph renderer could not start. Use the table view instead.");
        }
      });

    return () => {
      disposed = true;
      instance?.destroy();
      cyRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- sync graph data ------------------------------------------------------
  const nodeSignature = React.useMemo(
    () => nodes.map((node) => node.id).join(",") + `#${nodes.length}`,
    [nodes]
  );
  const edgeSignature = React.useMemo(
    () => edges.map((edge) => edge.id).join(",") + `#${edges.length}`,
    [edges]
  );

  React.useEffect(() => {
    const cy = cyRef.current;
    if (!ready || !cy) return;

    cy.elements().remove();
    cy.add([
      ...nodes.map((node) => ({
        group: "nodes" as const,
        data: {
          id: node.id,
          label: node.name,
          kind: node.kind,
          qualifiedName: node.qualified_name,
        },
      })),
      ...edges.map((edge) => ({
        group: "edges" as const,
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          kind: edge.kind,
          confidence: edge.confidence,
        },
      })),
    ]);
    // Deterministic layout then fit-to-view on data changes.
    cy.layout({ name: "cose", animate: false }).run();
    cy.fit(undefined, 48);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, nodeSignature, edgeSignature]);

  // ---- sync selection + impact highlighting ---------------------------------
  React.useEffect(() => {
    const cy = cyRef.current;
    if (!ready || !cy) return;
    const impactClasses = ["impact-target", "impact-direct", "impact-indirect", "impact-path"];
    // Cytoscape takes space-separated class names here.
    cy.elements().removeClass(["highlight", ...impactClasses].join(" "));
    if (selectedNodeId) {
      cy.getElementById(selectedNodeId).addClass("highlight");
    }
    if (selectedEdgeId) {
      cy.getElementById(selectedEdgeId).addClass("highlight");
    }
    // Impact classes come from real impact results and simply outline the
    // affected elements; ids absent from the canvas are ignored.
    for (const nodeId of impactTargets ?? []) {
      cy.getElementById(nodeId).addClass("impact-target");
    }
    for (const nodeId of impactDirect ?? []) {
      cy.getElementById(nodeId).addClass("impact-direct");
    }
    for (const nodeId of impactIndirect ?? []) {
      cy.getElementById(nodeId).addClass("impact-indirect");
    }
    for (const edgeId of impactPathEdges ?? []) {
      cy.getElementById(edgeId).addClass("impact-path");
    }
  }, [
    ready,
    selectedNodeId,
    selectedEdgeId,
    impactTargets,
    impactDirect,
    impactIndirect,
    impactPathEdges,
  ]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    const level = Math.max(cy.minZoom() ?? 1e-2, Math.min(cy.maxZoom() ?? 1e2, cy.zoom() * factor));
    cy.zoom(level);
  };

  const fitToView = () => cyRef.current?.fit(undefined, 48);
  const resetLayout = () => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.layout({ name: "cose", animate: false }).run();
    cy.fit(undefined, 48);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => zoomBy(1.25)}>
          <ZoomIn aria-hidden="true" className="size-4" /> Zoom in
        </Button>
        <Button variant="outline" size="sm" onClick={() => zoomBy(0.8)}>
          <ZoomOut aria-hidden="true" className="size-4" /> Zoom out
        </Button>
        <Button variant="outline" size="sm" onClick={fitToView}>
          <Maximize aria-hidden="true" className="size-4" /> Fit to view
        </Button>
        <Button variant="outline" size="sm" onClick={resetLayout}>
          <RotateCcw aria-hidden="true" className="size-4" /> Reset layout
        </Button>
      </div>
      <div
        ref={containerRef}
        role="img"
        aria-label="Interactive dependency graph canvas. The table view lists the same nodes and relationships."
        className="h-[520px] w-full rounded-md border bg-background"
      />
      {renderError ? (
        <p role="alert" className="text-sm text-destructive">
          {renderError}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Drag to pan, scroll to zoom, click a node or edge to inspect it. Canvas
          interactions are duplicated in the table view.
        </p>
      )}
    </div>
  );
}

/**
 * Cytoscape styles. Node kind uses shape + color + label (legend mirrors the
 * same mapping in text). Low-confidence edges are dashed; `CONTAINS` is
 * structural and rendered with square arrows so dependency edges (triangle
 * arrows) stay visually distinct.
 */
const NODE_AND_EDGE_STYLES: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": 10,
      "text-valign": "bottom",
      "text-margin-y": 6,
      color: "#334155",
      "background-color": "#94a3b8",
      width: 26,
      height: 26,
    },
  },
  {
    selector: "node[kind = 'module']",
    style: { shape: "round-rectangle", "background-color": "#64748b" },
  },
  {
    selector: "node[kind = 'class']",
    style: { shape: "ellipse", "background-color": "#7c3aed" },
  },
  {
    selector: "node[kind = 'function']",
    style: { shape: "diamond", "background-color": "#0e7490" },
  },
  {
    selector: "node[kind = 'method']",
    style: { shape: "round-tag", "background-color": "#b45309" },
  },
  {
    selector: "node.highlight",
    style: {
      "border-width": 3,
      "border-color": "#2563eb",
      "border-style": "solid",
    },
  },
  {
    selector: "edge",
    style: {
      width: 2,
      "line-color": "#94a3b8",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      "curve-style": "bezier",
    },
  },
  {
    selector: "edge[kind = 'CONTAINS']",
    style: { "line-color": "#cbd5e1", "target-arrow-shape": "square" },
  },
  {
    selector: "edge[confidence = 'low']",
    style: { "line-style": "dashed" },
  },
  {
    selector: "edge.highlight",
    style: { width: 4, "line-color": "#2563eb" },
  },
  // Impact highlighting (Phase 6B): target/direct/indirect get distinct
  // border styles + colors, restated as text in the legend and the table
  // view — never color alone.
  {
    selector: "node.impact-target",
    style: {
      "border-width": 3,
      "border-color": "#1d4ed8",
      "border-style": "solid",
    },
  },
  {
    selector: "node.impact-direct",
    style: {
      "border-width": 3,
      "border-color": "#15803d",
      "border-style": "solid",
    },
  },
  {
    selector: "node.impact-indirect",
    style: {
      "border-width": 3,
      "border-color": "#b45309",
      "border-style": "dashed",
    },
  },
  {
    selector: "edge.impact-path",
    style: { width: 4, "line-color": "#0e7490" },
  },
];
