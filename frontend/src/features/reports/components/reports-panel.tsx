"use client";

import * as React from "react";
import { Download, FileText } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import {
  downloadReportMarkdown,
  generateReport,
  saveReportFile,
} from "@/features/reports/reports-service";
import type { DiffResult, ReportInfo, ReportRequest } from "@/types/api";

/**
 * Report generation panel (Phase 7B): generate a Markdown impact report via
 * `POST /analyses/{analysis_id}/reports`, preview it through the download
 * endpoint, and save the file locally.
 *
 * Rules honored here:
 * - The report and its metadata come entirely from the backend; the preview
 *   renders the downloaded Markdown verbatim (no client-side "improvements").
 * - The optional scope body uses only target IDs echoed by a real diff
 *   response (mapped changed symbols) plus its direction/depth.
 * - The contract exposes no way to list earlier reports, so only reports
 *   generated in this session are shown — stated honestly in the UI.
 */
export function ReportsPanel({
  analysisId,
  diffScope,
}: {
  analysisId: string;
  /** Latest real diff result; enables "scope to changed symbols" reporting. */
  diffScope: DiffResult | null;
}) {
  const [scope, setScope] = React.useState<"analysis" | "diff">("analysis");
  const [busy, setBusy] = React.useState(false);
  const [report, setReport] = React.useState<ReportInfo | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Preview of the generated report's Markdown (fetched on demand).
  const [preview, setPreview] = React.useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);

  // Download (save-to-disk) state, separate from preview.
  const [downloading, setDownloading] = React.useState(false);
  const [downloadError, setDownloadError] = React.useState<string | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);
  React.useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const mappedTargetCount = React.useMemo(() => countMappedTargets(diffScope), [diffScope]);

  const buildRequest = (): ReportRequest | undefined => {
    if (scope !== "diff" || !diffScope) return undefined;
    const targetIds = [...new Set(collectMappedSymbolIds(diffScope))];
    if (targetIds.length === 0) return undefined;
    return {
      target_ids: targetIds,
      direction: diffScope.combined_impact.direction,
      max_depth: diffScope.combined_impact.max_depth,
    };
  };

  const runGenerate = async () => {
    if (busy) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      const created = await generateReport(analysisId, buildRequest(), controller.signal);
      if (controller.signal.aborted) return;
      setReport(created);
      setPreview(null);
      setPreviewError(null);
      setDownloadError(null);
      toast.success("Report generated", {
        description: `Markdown report “${created.filename}” was created. Preview or download it below.`,
      });
    } catch (cause) {
      if (controller.signal.aborted) return;
      setReport(null);
      setError(reportError(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  const runPreview = async () => {
    if (!report || previewLoading) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const markdown = await downloadReportMarkdown(report.id);
      setPreview(markdown);
    } catch (cause) {
      setPreview(null);
      setPreviewError(errorMessage(cause));
    } finally {
      setPreviewLoading(false);
    }
  };

  const runDownload = async () => {
    if (!report || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const downloaded = await saveReportFile(report.id, report.filename);
      toast.success("Report downloaded", {
        description: `Saved as “${downloaded}”.`,
      });
    } catch (cause) {
      setDownloadError(errorMessage(cause));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Markdown report</CardTitle>
        <CardDescription>
          Generate a deterministic Markdown impact report from the stored analysis data. The
          preview shows the exact downloaded file — the exported report matches what FlowLens
          computed, including provenance, impact, risk factors, coverage when attached, and
          analysis limitations.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-2 rounded-md border p-3">
          <legend className="text-sm font-medium">Report scope</legend>
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="radio"
              name="report-scope"
              checked={scope === "analysis"}
              onChange={() => setScope("analysis")}
            />
            <span>
              Entire analysis
              <span className="block text-xs text-muted-foreground">
                Include the analysis&apos;s stored impact data without target scoping.
              </span>
            </span>
          </label>
          <label
            className={`flex items-start gap-2 text-sm ${diffScope ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}
          >
            <input
              type="radio"
              name="report-scope"
              checked={scope === "diff"}
              onChange={() => mappedTargetCount > 0 && setScope("diff")}
              disabled={mappedTargetCount === 0}
            />
            <span>
              Changed symbols from the diff review
              <span className="block text-xs text-muted-foreground">
                {diffScope
                  ? mappedTargetCount > 0
                    ? `Scope the report to the ${mappedTargetCount} symbol${mappedTargetCount === 1 ? "" : "s"} mapped by the last analyzed diff, with its direction (${diffScope.combined_impact.direction}) and depth.`
                    : "The last analyzed diff mapped no symbols — there is nothing to scope to."
                  : "Analyze a diff first to enable this option."}
              </span>
            </span>
          </label>
        </fieldset>

        <div>
          <Button onClick={() => void runGenerate()} disabled={busy}>
            <FileText aria-hidden="true" className="size-4" />
            {busy ? "Generating…" : "Generate report"}
          </Button>
        </div>

        {busy ? (
          <div className="space-y-2" aria-busy="true" aria-label="Generating report">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : error ? (
          <ErrorState
            title="Report generation failed"
            message={error}
            onRetry={() => void runGenerate()}
            retryLabel="Retry generation"
          />
        ) : report ? (
          <div className="space-y-3">
            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <p className="flex flex-wrap items-center gap-2 font-medium">
                <FileText aria-hidden="true" className="size-4" /> {report.filename}
                <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                  {report.format}
                </span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Created {formatDateTime(report.created_at)} · report id{" "}
                <code title={report.id}>{report.id.slice(0, 8)}</code>
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void runPreview()}
                disabled={previewLoading}
                aria-expanded={preview !== null}
                aria-controls="report-preview"
              >
                {previewLoading ? "Loading preview…" : preview !== null ? "Reload preview" : "Preview Markdown"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => void runDownload()} disabled={downloading}>
                <Download aria-hidden="true" className="size-4" />
                {downloading ? "Downloading…" : "Download"}
              </Button>
            </div>

            {previewError ? (
              <ErrorState
                title="Preview failed"
                message={previewError}
                onRetry={() => void runPreview()}
                retryLabel="Retry preview"
              />
            ) : null}
            {downloadError ? (
              <ErrorState
                title="Download failed"
                message={downloadError}
                onRetry={() => void runDownload()}
                retryLabel="Retry download"
              />
            ) : null}

            {previewLoading ? (
              <Skeleton className="h-48 w-full" aria-label="Loading report preview" />
            ) : preview !== null ? (
              <div id="report-preview" className="space-y-2">
                <pre className="max-h-[480px] overflow-auto rounded-md border bg-muted/30 p-4 font-mono text-xs whitespace-pre-wrap" tabIndex={0} aria-label="Markdown report preview">
                  {preview}
                </pre>
                <p className="text-xs text-muted-foreground">
                  Rendered verbatim from the downloaded Markdown file — formatting, diagnostics,
                  and caveats are exactly as generated.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No preview loaded yet. The preview fetches the generated file; the download
                saves it locally.
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No report generated in this session. Past reports stay available on the backend,
            but the contract exposes no report listing — generate a new one here to preview or
            download it.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Error mapping for report generation requests. */
function reportError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === "ANALYSIS_NOT_READY") {
      return "Reports are not available yet — the analysis is still in progress. Try again once it completes.";
    }
    if (cause.code === "NOT_FOUND" || cause.code === "ANALYSIS_NOT_FOUND") {
      return "This analysis was not found. Go back to the workspace and reopen the review from a completed analysis.";
    }
  }
  return errorMessage(cause);
}

/** Unique mapped symbol IDs across every file of a real diff result. */
function collectMappedSymbolIds(diff: DiffResult): string[] {
  const ids: string[] = [];
  for (const file of diff.files) {
    for (const symbol of file.mapped_symbols ?? []) {
      ids.push(symbol.symbol_id);
    }
  }
  return ids;
}

function countMappedTargets(diffScope: DiffResult | null): number {
  if (!diffScope) return 0;
  return new Set(collectMappedSymbolIds(diffScope)).size;
}
