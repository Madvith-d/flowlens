import { apiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import type { DiffResult } from "@/types/api";

/**
 * Diff service — typed wrapper for the diff endpoint group in
 * `contracts/openapi.yaml`:
 *
 * - `POST /api/v1/analyses/{analysis_id}/diff` with `{ unified_diff }` →
 *   `DiffResult` (changed files, mapped/unmapped symbols, combined impact).
 *
 * The frontend never parses the diff itself. File, hunk, and symbol mapping
 * are all backend work — the UI only transmits the unified diff text and
 * renders the response.
 */

/** `POST /api/v1/analyses/{analysis_id}/diff`. */
export function analyzeDiff(
  analysisId: string,
  unifiedDiff: string,
  signal?: AbortSignal
): Promise<DiffResult> {
  return apiClient.post<DiffResult>(
    `/api/v1/analyses/${analysisId}/diff`,
    { unified_diff: unifiedDiff },
    signal
  );
}

/**
 * Map an API error to a diff-specific, actionable message.
 *
 * Known cases (contract: 400/422 `DIFF_INVALID` for unparseable input,
 * 409 `ANALYSIS_NOT_READY` for analyses that have not completed):
 * everything else falls back to the shared error message.
 */
export function diffRunError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === "DIFF_INVALID") {
      return "The diff could not be parsed. Check that the text is a valid unified diff (git diff format) and try again.";
    }
    if (cause.code === "ANALYSIS_NOT_READY") {
      return "Diff analysis is not available yet — the analysis is still in progress. Try again once it completes.";
    }
  }
  return errorMessage(cause);
}
