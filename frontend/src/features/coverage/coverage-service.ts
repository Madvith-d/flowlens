import { apiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import type { CoverageResult } from "@/types/api";

/**
 * Coverage service — typed wrapper for the coverage endpoint group in
 * `contracts/openapi.yaml`:
 *
 * - `POST /api/v1/analyses/{analysis_id}/coverage` — attach a Coverage.py
 *   JSON artifact. Per the contract, the request body is the raw
 *   `coverage json` output itself (an object), not a wrapper around it.
 *
 * The frontend validates nothing beyond "is this JSON" — schema, path
 * normalization, and line-to-symbol mapping are backend work. Missing
 * coverage stays `unknown`; it is never rendered as uncovered.
 */

/** `POST /api/v1/analyses/{analysis_id}/coverage` with the raw artifact JSON. */
export function attachCoverage(
  analysisId: string,
  coverageJson: Record<string, unknown>,
  signal?: AbortSignal
): Promise<CoverageResult> {
  return apiClient.post<CoverageResult>(
    `/api/v1/analyses/${analysisId}/coverage`,
    coverageJson,
    signal
  );
}

/**
 * Map an API error to a coverage-specific, actionable message.
 * Known case: 400 `COVERAGE_INVALID` for malformed artifacts; everything
 * else falls back to the shared error message.
 */
export function coverageAttachError(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === "COVERAGE_INVALID") {
    return "The coverage artifact was rejected. It must be the JSON output of `coverage json` (Coverage.py). Check the file and try again.";
  }
  return errorMessage(cause);
}
