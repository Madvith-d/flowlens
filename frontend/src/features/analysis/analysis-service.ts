import { apiClient } from "@/lib/api-client";
import type {
  AnalysisRun,
  NodeKind,
  PaginatedSymbols,
  Symbol,
} from "@/types/api";

/**
 * Analysis service — typed wrappers for the analyses endpoint group
 * (`/api/v1/snapshots/{snapshot_id}/analyses` and `/api/v1/analyses/...`).
 *
 * All state comes from the backend: the frontend never invents analysis
 * progress, counts, or symbol records.
 */

/** `POST /api/v1/snapshots/{snapshot_id}/analyses` — queue an analysis run. */
export function startAnalysis(snapshotId: string): Promise<AnalysisRun> {
  return apiClient.post<AnalysisRun>(`/api/v1/snapshots/${snapshotId}/analyses`);
}

/**
 * `GET /api/v1/analyses/{analysis_id}` — run state, counters, and the
 * diagnostics summary. Used for status polling and manual refresh.
 */
export function getAnalysis(
  analysisId: string,
  signal?: AbortSignal
): Promise<AnalysisRun> {
  return apiClient.get<AnalysisRun>(`/api/v1/analyses/${analysisId}`, undefined, signal);
}

/**
 * `GET /api/v1/analyses/{analysis_id}/symbols` — searchable, paginated
 * symbol catalog of a completed analysis.
 *
 * `q` searches short and qualified names; `kind` filters to one node kind,
 * both per the contract. Pagination is bounded by the contract (`per_page`
 * max 100).
 */
export function listSymbols(
  analysisId: string,
  params?: { q?: string; kind?: NodeKind; page?: number; perPage?: number },
  signal?: AbortSignal
): Promise<PaginatedSymbols> {
  return apiClient.get<PaginatedSymbols>(
    `/api/v1/analyses/${analysisId}/symbols`,
    {
      q: params?.q || undefined,
      kind: params?.kind || undefined,
      page: params?.page,
      per_page: params?.perPage,
    },
    signal
  );
}

/** Terminal analysis states after which polling must stop. */
export function isTerminalState(state: AnalysisRun["state"]): boolean {
  return (
    state === "completed" ||
    state === "completed_with_warnings" ||
    state === "failed"
  );
}

/** True while an analysis is still queued or running. */
export function isPendingState(state: AnalysisRun["state"]): boolean {
  return state === "queued" || state === "running";
}

export type { Symbol };
