"use client";

import * as React from "react";
import { Crosshair, Plus, TriangleAlert, X } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { ImpactPathDetails } from "@/features/impact/components/impact-path-details";
import { ImpactResults } from "@/features/impact/components/impact-results";
import { RiskScoreCard } from "@/features/impact/components/risk-score-card";
import {
  IMPACT_DEFAULT_DEPTH,
  IMPACT_MAX_DEPTH,
  IMPACT_MAX_TARGETS,
  IMPACT_MIN_DEPTH,
  computeImpact,
  impactRunError,
  type ImpactHighlight,
} from "@/features/impact/impact-service";
import type { GraphEdge, GraphNode, ImpactDirection, ImpactResult } from "@/types/api";

/**
 * Impact simulation panel (Phase 6B).
 *
 * Target selection comes from the graph (node selection and symbol search
 * live in the workspace). Direction and depth map 1:1 to the frozen
 * `POST /api/v1/analyses/{analysis_id}/impact` request; results — impacted
 * nodes, hop distances, representative paths, warnings, and the risk score —
 * are rendered verbatim from the response and never recalculated here.
 */
export function ImpactPanel({
  analysisId,
  selectedNodeId,
  selectedQualifiedName,
  visibleEdges,
  nodeById,
  onSelectNode,
  onSelectEdge,
  onHighlightChange,
}: {
  analysisId: string;
  /** Currently selected graph node — the primary way to add a target. */
  selectedNodeId: string | null;
  selectedQualifiedName: string | null;
  visibleEdges: readonly GraphEdge[];
  nodeById: ReadonlyMap<string, GraphNode>;
  /** Selects a node in the graph (fetches detail + 1-hop neighbors there). */
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  /** Publishes impact highlighting for the canvas/list view. */
  onHighlightChange: (highlight: ImpactHighlight | null) => void;
}) {
  const [targets, setTargets] = React.useState<{ id: string; qualified_name: string }[]>([]);
  const [direction, setDirection] = React.useState<ImpactDirection>("both");
  const [depth, setDepth] = React.useState(IMPACT_DEFAULT_DEPTH);
  const [result, setResult] = React.useState<ImpactResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [focusNodeId, setFocusNodeId] = React.useState<string | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);
  // Keep the latest callbacks in refs so unmount cleanup stays correct.
  const highlightRef = React.useRef(onHighlightChange);
  highlightRef.current = onHighlightChange;

  const edgeById = React.useMemo(() => {
    const map = new Map<string, GraphEdge>();
    for (const edge of visibleEdges) map.set(edge.id, edge);
    return map;
  }, [visibleEdges]);

  // ---- target management ------------------------------------------------------

  const selectedAlreadyTarget = Boolean(
    selectedNodeId && targets.some((target) => target.id === selectedNodeId)
  );
  const targetsFull = targets.length >= IMPACT_MAX_TARGETS;

  const addSelectedAsTarget = () => {
    if (!selectedNodeId || selectedAlreadyTarget || targetsFull) return;
    const qualifiedName =
      selectedQualifiedName ?? nodeById.get(selectedNodeId)?.qualified_name ?? selectedNodeId;
    setTargets((current) => [...current, { id: selectedNodeId, qualified_name: qualifiedName }]);
    // A result built for a different target set is no longer shown as current.
    setResult(null);
    setFocusNodeId(null);
    setError(null);
  };

  const removeTarget = (targetId: string) => {
    setTargets((current) => current.filter((target) => target.id !== targetId));
    setResult(null);
    setFocusNodeId(null);
    setError(null);
  };

  // ---- run ----------------------------------------------------------------------

  const runImpact = async () => {
    if (targets.length === 0 || busy) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setBusy(true);
    setError(null);
    setFocusNodeId(null);
    try {
      const response = await computeImpact(
        analysisId,
        {
          target_ids: targets.map((target) => target.id),
          direction,
          max_depth: depth,
        },
        controller.signal
      );
      setResult(response);
    } catch (cause) {
      if (controller.signal.aborted) return; // superseded by a newer run
      setResult(null);
      setError(impactRunError(cause));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  };

  // Abort any in-flight request when the panel unmounts.
  React.useEffect(() => {
    const controller = abortRef;
    return () => controller.current?.abort();
  }, []);

  // ---- graph highlighting ---------------------------------------------------------

  React.useEffect(() => {
    if (!result) {
      highlightRef.current(null);
      return;
    }
    const focus = focusNodeId
      ? result.impacted.find((impacted) => impacted.node_id === focusNodeId) ?? null
      : null;
    highlightRef.current({
      targetNodeIds: result.targets.map((target) => target.node_id),
      directNodeIds: result.impacted.filter((impacted) => impacted.direct).map((i) => i.node_id),
      indirectNodeIds: result.impacted
        .filter((impacted) => !impacted.direct)
        .map((i) => i.node_id),
      pathEdgeIds: (focus?.paths ?? []).flatMap((path) => path.edges),
    });
  }, [result, focusNodeId]);

  // Clear highlighting when the panel goes away.
  React.useEffect(() => {
    const ref = highlightRef;
    return () => ref.current(null);
  }, []);

  // ---- focus ---------------------------------------------------------------------

  const selectImpacted = (nodeId: string) => {
    setFocusNodeId(nodeId);
    onSelectNode(nodeId);
  };

  const focusNode = result && focusNodeId
    ? result.impacted.find((impacted) => impacted.node_id === focusNodeId) ?? null
    : null;

  const directCount = result ? result.impacted.filter((impacted) => impacted.direct).length : 0;
  const indirectCount = result ? result.impacted.length - directCount : 0;
  const targetLabel =
    result && result.targets.length > 0
      ? result.targets.map((target) => target.qualified_name).join(", ")
      : "";

  return (
    <Card id="impact-panel" aria-label="Impact simulation">
      <CardHeader>
        <CardTitle>
          <Crosshair aria-hidden="true" className="mr-2 inline size-5" />
          Impact simulation
        </CardTitle>
        <CardDescription>
          Pick one or more target symbols, then run the impact analysis. Direct and indirect
          effects, hop distances, representative paths, and the risk score all come from the
          analysis result — nothing is estimated in the browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* ---- targets ---- */}
        <div className="space-y-2">
          <p className="text-sm font-medium" id="impact-targets-label">
            Target symbols ({targets.length}/{IMPACT_MAX_TARGETS})
          </p>
          {targets.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No targets yet — select a node in the graph or search symbols above, then add it
              as a target.
            </p>
          ) : (
            <ul aria-labelledby="impact-targets-label" className="flex flex-wrap gap-2">
              {targets.map((target) => (
                <li key={target.id}>
                  <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs">
                    <code className="max-w-72 truncate" title={target.qualified_name}>
                      {target.qualified_name}
                    </code>
                    <button
                      type="button"
                      aria-label={`Remove target ${target.qualified_name}`}
                      className="rounded-full p-0.5 hover:bg-muted"
                      onClick={() => removeTarget(target.id)}
                    >
                      <X aria-hidden="true" className="size-3.5" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={addSelectedAsTarget}
            disabled={!selectedNodeId || selectedAlreadyTarget || targetsFull}
            title={
              !selectedNodeId
                ? "Select a node in the graph first"
                : selectedAlreadyTarget
                  ? "The selected node is already a target"
                  : targetsFull
                    ? `At most ${IMPACT_MAX_TARGETS} targets per request`
                    : undefined
            }
          >
            <Plus aria-hidden="true" className="size-4" />
            {selectedNodeId && selectedQualifiedName
              ? `Add “${selectedQualifiedName}” as target`
              : "Add selected node as target"}
          </Button>
        </div>

        {/* ---- direction + depth ---- */}
        <div className="grid gap-4 sm:grid-cols-2">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Traversal direction</legend>
            {(
              [
                ["upstream", "Upstream — callers that depend on the target"],
                ["downstream", "Downstream — dependencies of the target"],
                ["both", "Both directions"],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-input px-3 py-1.5 text-sm has-[:checked]:bg-accent"
              >
                <input
                  type="radio"
                  name={`impact-direction-${analysisId}`}
                  value={value}
                  checked={direction === value}
                  onChange={() => setDirection(value)}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <div className="space-y-1.5">
            <label htmlFor={`impact-depth-${analysisId}`} className="text-sm font-medium">
              Maximum traversal depth
            </label>
            <select
              id={`impact-depth-${analysisId}`}
              className="h-9 w-full max-w-48 rounded-md border border-input bg-background px-3 text-sm"
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            >
              {Array.from(
                { length: IMPACT_MAX_DEPTH - IMPACT_MIN_DEPTH + 1 },
                (_, index) => IMPACT_MIN_DEPTH + index
              ).map((value) => (
                <option key={value} value={value}>
                  {value} {value === 1 ? "hop" : "hops"}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Between {IMPACT_MIN_DEPTH} and {IMPACT_MAX_DEPTH} hops, per the analysis limits.
            </p>
          </div>
        </div>

        <Button onClick={() => void runImpact()} disabled={busy || targets.length === 0}>
          {busy ? "Analyzing impact…" : "Run impact analysis"}
        </Button>

        {/* ---- states ---- */}
        {busy ? (
          <div className="space-y-2" aria-busy="true" aria-label="Calculating impact">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : error ? (
          <ErrorState
            title="Impact analysis failed"
            message={error}
            onRetry={() => void runImpact()}
          />
        ) : result && result.impacted.length === 0 ? (
          <EmptyState
            title="No impacted symbols"
            description={`No symbols were impacted within ${result.max_depth ?? depth} ${result.max_depth === 1 ? "hop" : "hops"} in the ${result.direction} direction. Try the other direction, “both”, or a deeper traversal.`}
          />
        ) : result ? (
          <div className="space-y-4">
            <p aria-live="polite" className="text-sm">
              <strong>{result.impacted.length}</strong> impacted symbol
              {result.impacted.length === 1 ? "" : "s"} — {directCount} direct, {indirectCount}{" "}
              indirect — within {result.max_depth ?? depth}{" "}
              {(result.max_depth ?? depth) === 1 ? "hop" : "hops"}, direction {result.direction}.
            </p>

            {result.truncated ? (
              <Alert>
                <TriangleAlert aria-hidden="true" className="size-4" />
                <AlertTitle>Partial impact result</AlertTitle>
                <AlertDescription>
                  The server limited this result — additional impacted symbols exist beyond the
                  returned set. Narrow the direction, reduce the depth, or analyze fewer targets.
                </AlertDescription>
              </Alert>
            ) : null}

            {result.warnings.length > 0 ? (
              <Alert>
                <TriangleAlert aria-hidden="true" className="size-4" />
                <AlertTitle>Analysis warnings</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc space-y-1 pl-5">
                    {result.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}

            <RiskScoreCard risk={result.risk} targetLabel={targetLabel} />

            <ImpactResults result={result} focusNodeId={focusNodeId} onSelectImpacted={selectImpacted} />

            {focusNode ? (
              <ImpactPathDetails
                focusQualifiedName={focusNode.qualified_name}
                focusNodeId={focusNode.node_id}
                paths={focusNode.paths ?? []}
                targetNodeIds={result.targets.map((target) => target.node_id)}
                edgeById={edgeById}
                nodeById={nodeById}
                onSelectEdge={onSelectEdge}
              />
            ) : null}

            <p className="text-xs text-muted-foreground">
              Static reachability does not prove a path executes at runtime. Unresolved or
              ambiguous references are excluded from the graph and reported as warnings by the
              backend.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
