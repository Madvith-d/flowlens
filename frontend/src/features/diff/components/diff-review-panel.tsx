"use client";

import * as React from "react";
import { TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { analyzeDiff, diffRunError } from "@/features/diff/diff-service";
import { RiskScoreCard } from "@/features/impact/components/risk-score-card";
import { CoverageSummaryRow } from "@/features/coverage/components/coverage-status";
import type { DiffChangeType, DiffResult, ImpactResult } from "@/types/api";

/**
 * Diff review (Phase 7B): paste or upload a unified diff, submit it to
 * `POST /analyses/{analysis_id}/diff`, and render the changed files, mapped
 * and unmapped symbols, and the combined impact the backend computed.
 *
 * Rules honored here:
 * - The diff is never parsed client-side; every mapping/impact value shown
 *   is a response field.
 * - Unmapped changes are preserved and shown with the backend's reason.
 * - The distinction between no impact and failed analysis is explicit.
 */
export function DiffReviewPanel({
  analysisId,
  onResult,
}: {
  analysisId: string;
  /** Publishes the latest real diff result (or null) to the page. */
  onResult?: (result: DiffResult | null) => void;
}) {
  const [unifiedDiff, setUnifiedDiff] = React.useState("");
  const [fileError, setFileError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<DiffResult | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);

  // Editing the diff invalidates the previous result.
  const changeDiff = (text: string) => {
    setUnifiedDiff(text);
    if (text !== unifiedDiff) {
      setResult(null);
      onResult?.(null);
    }
  };

  React.useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const submitDiff = async () => {
    if (!unifiedDiff.trim() || busy) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    setResult(null);
    onResult?.(null);
    try {
      const response = await analyzeDiff(analysisId, unifiedDiff, controller.signal);
      if (controller.signal.aborted) return;
      setResult(response);
      onResult?.(response);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(diffRunError(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  const readFile = async (file: File | null) => {
    if (!file) return;
    setFileError(null);
    try {
      const text = await file.text();
      changeDiff(text);
    } catch {
      setFileError("The file could not be read as text. Provide a plain-text unified diff.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Diff review</CardTitle>
        <CardDescription>
          Paste a unified diff (git diff format) or upload a .diff/.patch file.
          FlowLens maps the changed lines onto the snapshot&apos;s symbols and
          computes the combined impact for the mapped symbols. The diff itself
          is parsed on the backend — nothing is inferred in the browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="unified-diff" className="text-sm font-medium">
            Unified diff
          </label>
          <textarea
            id="unified-diff"
            className="min-h-40 w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            placeholder={"--- a/app/core.py\n+++ b/app/core.py\n@@ ... @@\n-def old():\n+def new():"}
            value={unifiedDiff}
            onChange={(event) => changeDiff(event.target.value)}
            spellCheck={false}
            aria-describedby="unified-diff-hint"
          />
          <p id="unified-diff-hint" className="text-xs text-muted-foreground">
            Added, modified, deleted, and unmapped changes are reported for each
            file. Changes outside any symbol span (e.g. module-level edits) stay
            visible as unmapped with the backend&apos;s reason.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void submitDiff()} disabled={busy || !unifiedDiff.trim()}>
            {busy ? "Analyzing diff…" : "Analyze diff"}
          </Button>
          <label className="inline-flex h-9 cursor-pointer items-center rounded-md border border-input px-3 text-sm font-medium shadow-xs outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 has-[:focus-visible]:ring-[3px]">
            Upload diff file
            <input
              type="file"
              accept=".diff,.patch,.txt,text/plain"
              className="sr-only"
              onChange={(event) => void readFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {fileError ? (
          <p role="alert" className="text-sm text-destructive">
            {fileError}
          </p>
        ) : null}

        {busy ? (
          <div className="space-y-2" aria-busy="true" aria-label="Analyzing diff">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : error ? (
          <ErrorState
            title="Diff analysis failed"
            message={error}
            onRetry={() => void submitDiff()}
            retryLabel="Retry analysis"
          />
        ) : !result ? (
          <p className="text-sm text-muted-foreground">
            No diff has been analyzed yet — paste or upload one, then run the analysis.
          </p>
        ) : (
          <DiffResultView result={result} />
        )}
      </CardContent>
    </Card>
  );
}

/** Everything below renders fields of a real `DiffResult` response. */
function DiffResultView({ result }: { result: DiffResult }) {
  return (
    <div className="space-y-4">
      {result.warnings.length > 0 ? (
        <Alert>
          <TriangleAlert aria-hidden="true" className="size-4" />
          <AlertTitle>Warnings</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-1 pl-5">
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {result.files.length === 0 ? (
        <EmptyState
          title="No changed files recognized"
          description="The backend did not find any changed files in the submitted diff. Check that the text is a complete unified diff (git diff format) and submit it again."
        />
      ) : (
        <div className="space-y-3">
          <p className="text-sm font-medium">
            Changed files
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {result.files.length} file{result.files.length === 1 ? "" : "s"}
            </span>
          </p>
          {result.files.map((file) => (
            <div key={file.path} className="rounded-md border">
              <div className="flex flex-wrap items-center gap-2 p-3">
                <code className="text-sm font-medium">{file.path}</code>
                <ChangeTypeBadge changeType={file.change_type} />
                <span className="text-xs text-muted-foreground">
                  {file.changed_line_count} changed line{file.changed_line_count === 1 ? "" : "s"}
                </span>
              </div>
              <div className="border-t p-3 text-sm">
                <DiffFileDetails file={file} />
              </div>
            </div>
          ))}
        </div>
      )}

      <CombinedImpactCard impact={result.combined_impact} />
    </div>
  );
}

/** Per-file mapped symbols and the honest unmapped remainder. */
function DiffFileDetails({ file }: { file: DiffResult["files"][number] }) {
  const mapped = file.mapped_symbols ?? [];
  const unmappedCount = file.unmapped_line_count;
  return (
    <div className="space-y-2">
      {mapped.length === 0 ? (
        <p className="text-muted-foreground">
          No symbols were mapped to this file&apos;s changes.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {mapped.map((symbol) => (
            <li key={symbol.symbol_id} className="flex flex-wrap items-center gap-2">
              <code className="text-xs">{symbol.qualified_name}</code>
              <ChangeTypeBadge changeType={symbol.change_type} />
              <span className="font-mono text-xs text-muted-foreground/70" title={symbol.symbol_id}>
                {symbol.symbol_id}
              </span>
            </li>
          ))}
        </ul>
      )}
      {typeof unmappedCount === "number" && unmappedCount > 0 ? (
        <p className="text-muted-foreground">
          <Badge variant="warning">unmapped</Badge>{" "}
          {unmappedCount} changed line{unmappedCount === 1 ? "" : "s"} could not be mapped to a
          symbol{file.unmapped_reason ? ` — ${file.unmapped_reason}` : ""}.
        </p>
      ) : null}
    </div>
  );
}

/** Combined impact of all mapped changed symbols (backend-computed). */
export function CombinedImpactCard({ impact }: { impact: ImpactResult }) {
  const impacted = impact.impacted;
  const targetNames = new Map(
    impact.targets.map((target) => [target.node_id, target.qualified_name])
  );

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium">Combined impact</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Computed by the backend for{" "}
          {impact.targets.length === 0
            ? "no mapped target"
            : `${impact.targets.length} mapped changed symbol${impact.targets.length === 1 ? "" : "s"}`}{" "}
          (direction: {impact.direction}
          {impact.max_depth ? `, depth ${impact.max_depth}` : ""}). Impact deduplicates across
          targets while keeping per-target attribution in the table below.
        </p>
      </div>

      {impact.truncated ? (
        <Alert>
          <TriangleAlert aria-hidden="true" className="size-4" />
          <AlertTitle>Partial result</AlertTitle>
          <AlertDescription>
            The server limited this impact result. The list below may not include every impacted
            symbol.
          </AlertDescription>
        </Alert>
      ) : null}

      {impacted.length === 0 ? (
        <EmptyState
          title="No impacted symbols"
          description="The backend found no callers or dependencies of the mapped changed symbols within its traversal limits. This means no statically reachable impact was found — it is not a claim that the change is safe."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Impacted symbols with direct/indirect status and per-target attribution
            </caption>
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">Symbol</th>
                <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
                <th scope="col" className="py-2 pr-4 font-medium">Impact</th>
                <th scope="col" className="py-2 pr-4 font-medium">Min hops</th>
                <th scope="col" className="py-2 font-medium">Attributed to changed symbols</th>
              </tr>
            </thead>
            <tbody>
              {impacted.map((node) => (
                <tr key={node.node_id} className="border-b">
                  <td className="py-2 pr-4 align-top">
                    <code className="text-xs">{node.qualified_name}</code>
                    <span className="sr-only">
                      {node.direct ? "direct" : "indirect"} impact, {node.min_hops} hops
                    </span>
                  </td>
                  <td className="py-2 pr-4 align-top">{node.kind}</td>
                  <td className="py-2 pr-4 align-top">
                    {node.direct ? (
                      <Badge variant="success">direct</Badge>
                    ) : (
                      <Badge variant="secondary">indirect</Badge>
                    )}
                  </td>
                  <td className="py-2 pr-4 align-top tabular-nums">
                    {node.min_hops} hop{node.min_hops === 1 ? "" : "s"}
                  </td>
                  <td className="py-2 align-top text-xs">
                    {node.attributed_to
                      .map((id) => targetNames.get(id) ?? id)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CoverageSummaryRow summary={impact.coverage_summary} />

      <RiskScoreCard
        risk={impact.risk}
        targetLabel={
          impact.targets.length === 1
            ? "the changed symbol"
            : `the ${impact.targets.length} changed symbols`
        }
      />

      {impact.warnings.length > 0 ? (
        <div>
          <p className="mb-1 text-sm font-medium">Impact warnings</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {impact.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Static reachability is not proof that a path executes at runtime. Impact
        here is inferred from statically resolved dependency edges only.
      </p>
    </div>
  );
}


/** Text-first change-type badge; color is decorative only. */
function ChangeTypeBadge({ changeType }: { changeType: DiffChangeType }) {
  return (
    <Badge
      variant={
        changeType === "added" ? "success" : changeType === "deleted" ? "warning" : "secondary"
      }
    >
      {changeType}
    </Badge>
  );
}

