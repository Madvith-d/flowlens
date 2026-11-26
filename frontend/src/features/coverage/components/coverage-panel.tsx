"use client";

import * as React from "react";
import { TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CoverageLegend,
  CoverageSummaryRow,
} from "@/features/coverage/components/coverage-status";
import { attachCoverage, coverageAttachError } from "@/features/coverage/coverage-service";
import type { CoverageResult } from "@/types/api";

/**
 * Coverage overlay attach panel (Phase 7B): paste or upload a Coverage.py
 * JSON artifact and attach it to the completed analysis via
 * `POST /analyses/{analysis_id}/coverage`.
 *
 * Rules honored here:
 * - Only JSON validity is checked client-side; schema and path mapping are
 *   the backend's job and its errors are surfaced verbatim-mapped.
 * - Missing/unknown coverage is displayed as unknown, never as uncovered.
 * - The response carries summary counts only; per-symbol coverage status
 *   comes later through graph node fields, which the actions here link to.
 */
export function CoveragePanel({
  analysisId,
  onAttached,
}: {
  analysisId: string;
  /** Notifies the page when a real artifact was attached. */
  onAttached?: (result: CoverageResult) => void;
}) {
  const [coverageText, setCoverageText] = React.useState("");
  const [fileError, setFileError] = React.useState<string | null>(null);
  const [parseError, setParseError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<CoverageResult | null>(null);

  const abortRef = React.useRef<AbortController | null>(null);
  React.useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const changeText = (text: string) => {
    setCoverageText(text);
    setParseError(null);
  };

  const readFile = async (file: File | null) => {
    if (!file) return;
    setFileError(null);
    try {
      changeText(await file.text());
    } catch {
      setFileError("The file could not be read as text. Provide a JSON file.");
    }
  };

  const attach = async () => {
    if (busy) return;
    setParseError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(coverageText);
    } catch {
      setParseError(
        "This does not look like JSON. The backend expects the exact JSON output of `coverage json`."
      );
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setParseError(
        "The artifact must be a JSON object — the raw output of `coverage json`, not a wrapper."
      );
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      const response = await attachCoverage(
        analysisId,
        parsed as Record<string, unknown>,
        controller.signal
      );
      if (controller.signal.aborted) return;
      setResult(response);
      onAttached?.(response);
      toast.success("Coverage attached", {
        description:
          "Symbol coverage statuses are now included in analysis results — open the graph to see the overlay.",
      });
    } catch (cause) {
      if (controller.signal.aborted) return;
      setResult(null);
      setError(coverageAttachError(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Coverage overlay</CardTitle>
        <CardDescription>
          Attach the JSON output of <code className="text-xs">coverage json</code> (Coverage.py)
          for this analysis. FlowLens normalizes the artifact against the snapshot and maps
          covered/partially-covered/uncovered lines to symbols on the backend. Files that cannot
          be matched to the snapshot are reported, not guessed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="coverage-json" className="text-sm font-medium">
            Coverage.py JSON artifact
          </label>
          <textarea
            id="coverage-json"
            className="min-h-32 w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            placeholder={'{"meta": …, "files": {"app/core.py": {"executed_lines": [...], …}}}'}
            value={coverageText}
            onChange={(event) => changeText(event.target.value)}
            spellCheck={false}
            aria-describedby="coverage-json-hint"
          />
          <p id="coverage-json-hint" className="text-xs text-muted-foreground">
            Generate it inside your project with <code>coverage run</code> then{" "}
            <code>coverage json</code>. FlowLens never runs your tests — it only reads the
            artifact you provide.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void attach()} disabled={busy || !coverageText.trim()}>
            {busy ? "Attaching…" : "Attach coverage"}
          </Button>
          <label className="inline-flex h-9 cursor-pointer items-center rounded-md border border-input px-3 text-sm font-medium shadow-xs outline-none transition-colors hover:bg-accent has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50">
            Upload JSON file
            <input
              type="file"
              accept=".json,application/json"
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
        {parseError ? (
          <p role="alert" className="text-sm text-destructive">
            {parseError}
          </p>
        ) : null}

        {busy ? (
          <div className="space-y-2" aria-busy="true" aria-label="Attaching coverage artifact">
            <Skeleton className="h-20 w-full" />
          </div>
        ) : error ? (
          <ErrorState
            title="Could not attach coverage"
            message={error}
            onRetry={() => void attach()}
            retryLabel="Retry attaching"
          />
        ) : result ? (
          <div className="space-y-4">
            <CoverageSummaryRow summary={result.summary} label="Coverage summary of this analysis:" />

            {typeof result.unmatched_file_count === "number" &&
            result.unmatched_file_count > 0 ? (
              <Alert>
                <TriangleAlert aria-hidden="true" className="size-4" />
                <AlertTitle>
                  {result.unmatched_file_count} coverage file
                  {result.unmatched_file_count === 1 ? "" : "s"} could not be matched to this
                  snapshot
                </AlertTitle>
                <AlertDescription>
                  Paths in the artifact that do not exist in the analyzed snapshot are excluded.
                  Coverage for unmatched files is never attributed to symbols.
                </AlertDescription>
              </Alert>
            ) : null}

            {result.warnings.length > 0 ? (
              <div>
                <p className="mb-1 text-sm font-medium">Warnings</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {result.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <CoverageLegend />
          </div>
        ) : (
          <CoverageLegend title="Coverage statuses (after attaching)" />
        )}
      </CardContent>
    </Card>
  );
}
