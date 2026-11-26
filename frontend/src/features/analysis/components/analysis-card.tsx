"use client";

import * as React from "react";
import { Loader2, RotateCw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { AnalysisStateBadge } from "@/features/projects/components/analysis-state-badge";
import { DiagnosticsSummaryList } from "@/features/analysis/components/diagnostics-summary";
import type { AnalysisRun } from "@/types/api";

/**
 * Analysis run status: state badge, timestamps, file/symbol/edge counts,
 * versions, and the diagnostics summary. Every value comes from the
 * `AnalysisRun` response; nothing is estimated client-side.
 */
export function AnalysisCard({
  analysis,
  pollLimitReached,
  pollError,
  onManualRefresh,
}: {
  analysis: AnalysisRun;
  /** Polling budget exhausted — offer an honest manual refresh. */
  pollLimitReached: boolean;
  /** A status poll failed — show the error and a retry action. */
  pollError: string | null;
  onManualRefresh: () => void;
}) {
  const pending = analysis.state === "queued" || analysis.state === "running";

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle id="analysis-status-title">Analysis</CardTitle>
          <AnalysisStateBadge state={analysis.state} />
        </div>
        <CardDescription>
          Static analysis of the selected immutable snapshot. FlowLens parses
          source without executing it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {pending ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 aria-hidden="true" className="size-4 animate-spin" />
            {analysis.state === "queued"
              ? "Queued — waiting for the backend to pick up this run."
              : "Running — status refreshes automatically while this panel is open."}
          </p>
        ) : null}

        {analysis.state === "failed" ? (
          <Alert variant="destructive">
            <AlertTitle>Analysis failed</AlertTitle>
            <AlertDescription>
              The backend reported failure
              {analysis.error_code ? ` (${analysis.error_code})` : ""}.
              {analysis.finished_at ? ` Finished ${formatDateTime(analysis.finished_at)}.` : ""}
              {" "}You can retry against the same immutable snapshot.
            </AlertDescription>
          </Alert>
        ) : null}

        {analysis.state === "completed_with_warnings" ? (
          <Alert variant="warning">
            <AlertTitle>Completed with warnings</AlertTitle>
            <AlertDescription>
              The snapshot was analyzed, but some files or references produced
              diagnostics. See the counts below.
            </AlertDescription>
          </Alert>
        ) : null}

        {pollLimitReached ? (
          <Alert variant="info">
            <AlertTitle>Still running</AlertTitle>
            <AlertDescription>
              <div className="flex flex-wrap items-center gap-3">
                <p>
                  Automatic status refresh stopped after the polling budget was
                  reached. Use the refresh button to check the current state.
                </p>
                <Button variant="outline" size="sm" onClick={onManualRefresh}>
                  <RotateCw aria-hidden="true" className="size-3.5" />
                  Refresh status
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        ) : null}

        {pollError ? (
          <p role="alert" className="text-sm text-destructive">
            {pollError}{" "}
            <Button
              variant="outline"
              size="sm"
              className="ml-1"
              onClick={onManualRefresh}
            >
              <RotateCw aria-hidden="true" className="size-3.5" />
              Refresh status
            </Button>
          </p>
        ) : null}

        {analysis.state === "completed" || analysis.state === "completed_with_warnings" ? (
          <>
            <AnalysisCounts analysis={analysis} />
            <div>
              <h4 className="mb-2 text-sm font-medium">Diagnostics</h4>
              <DiagnosticsSummaryList summary={analysis.diagnostics_summary} />
            </div>
          </>
        ) : null}

        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <dt>Analysis run</dt>
          <dd title={analysis.id}>{analysis.id}</dd>
          <dt>Created</dt>
          <dd>{formatDateTime(analysis.created_at)}</dd>
          {analysis.started_at ? (
            <>
              <dt>Started</dt>
              <dd>{formatDateTime(analysis.started_at)}</dd>
            </>
          ) : null}
          {analysis.finished_at ? (
            <>
              <dt>Finished</dt>
              <dd>{formatDateTime(analysis.finished_at)}</dd>
            </>
          ) : null}
          {analysis.flowlens_version ? (
            <>
              <dt>FlowLens version</dt>
              <dd>{analysis.flowlens_version}</dd>
            </>
          ) : null}
          <dt>Graph schema</dt>
          <dd>{analysis.graph_schema_version}</dd>
        </dl>
      </CardContent>
    </Card>
  );
}

/** File/symbol/edge counters. Zero Python files is a real, shown state. */
function AnalysisCounts({ analysis }: { analysis: AnalysisRun }) {
  const rows: ReadonlyArray<[string, number | undefined, string]> = [
    ["Python files", analysis.python_file_count, "files parsed"],
    ["Symbols", analysis.symbol_count, "symbols extracted"],
    ["Edges", analysis.edge_count, "dependency edges"],
  ];
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([label, value, description]) => (
        <React.Fragment key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd>
            {value === undefined ? (
              <span className="text-muted-foreground">unknown</span>
            ) : (
              <>
                <span className="font-medium">{value}</span>{" "}
                <span className="text-xs text-muted-foreground">{description}</span>
              </>
            )}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

/** Loading skeleton for the analysis card while the run is being fetched/started. */
export function AnalysisCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-64" />
      </CardContent>
    </Card>
  );
}
