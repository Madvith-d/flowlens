import { apiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import type { ImpactRequest, ImpactResult } from "@/types/api";

/**
 * Impact service — typed wrapper for the impact endpoint group in
 * `contracts/openapi.yaml`:
 *
 * - `POST /api/v1/analyses/{analysis_id}/impact` (ImpactRequest →
 *   ImpactResult with impacted nodes, representative paths, and the
 *   backend-computed explainable risk score).
 *
 * The frontend never computes, recalculates, or estimates impact, hops,
 * paths, or risk factors — every value displayed comes from this response.
 */

/** Contract bounds of `ImpactRequest` (minItems/maxItems/minimum/maximum). */
export const IMPACT_MAX_TARGETS = 10;
export const IMPACT_MIN_DEPTH = 1;
export const IMPACT_MAX_DEPTH = 10;
/** Contract default for `max_depth`. */
export const IMPACT_DEFAULT_DEPTH = 3;

/**
 * What the impact panel asks the graph workspace to highlight. All IDs come
 * from a real `ImpactResult`; nothing here is derived client-side.
 */
export interface ImpactHighlight {
  targetNodeIds: readonly string[];
  directNodeIds: readonly string[];
  indirectNodeIds: readonly string[];
  /** Edge IDs of the focused impacted node's representative paths. */
  pathEdgeIds: readonly string[];
}

/** `POST /api/v1/analyses/{analysis_id}/impact`. */
export function computeImpact(
  analysisId: string,
  request: ImpactRequest,
  signal?: AbortSignal
): Promise<ImpactResult> {
  return apiClient.post<ImpactResult>(
    `/api/v1/analyses/${analysisId}/impact`,
    {
      target_ids: request.target_ids,
      direction: request.direction,
      max_depth: request.max_depth,
    },
    signal
  );
}

/**
 * Map an API error to an impact-specific, actionable message.
 *
 * Known cases (per the backend Phase 6A contract behavior):
 * - 409 `ANALYSIS_NOT_READY`: the analysis is not in a completed state.
 * - 404 `NOT_FOUND` with `details.missing_target_ids[]`: one or more
 *   requested target IDs do not exist in this analysis.
 * Everything else falls back to the shared error message.
 */
export function impactRunError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === "ANALYSIS_NOT_READY") {
      return "Impact is not available yet — the analysis is still in progress. Try again once it completes.";
    }
    const missing = cause.details?.["missing_target_ids"];
    if (
      (cause.code === "NOT_FOUND" || cause.code === "ANALYSIS_NOT_FOUND") &&
      Array.isArray(missing) &&
      missing.length > 0
    ) {
      const ids = missing.map((value) => String(value)).join(", ");
      return `Some impact targets could not be found in this analysis (${ids}). Remove the stale targets and add them again from the graph or symbol search.`;
    }
  }
  return errorMessage(cause);
}
