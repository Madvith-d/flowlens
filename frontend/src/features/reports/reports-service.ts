import { apiClient } from "@/lib/api-client";
import type { ReportInfo, ReportRequest } from "@/types/api";

/**
 * Reports service — typed wrapper for the report endpoint group in
 * `contracts/openapi.yaml`:
 *
 * - `POST /api/v1/analyses/{analysis_id}/reports` (201 → `ReportInfo`),
 *   with an optional `{ target_ids, direction, max_depth }` scoping body.
 * - `GET /api/v1/reports/{report_id}/download` → `text/markdown`.
 *
 * The frontend renders the downloaded Markdown verbatim — the report content
 * is entirely backend-generated from stored analysis data.
 */

/** `POST /api/v1/analyses/{analysis_id}/reports`. */
export function generateReport(
  analysisId: string,
  request?: ReportRequest,
  signal?: AbortSignal
): Promise<ReportInfo> {
  return apiClient.post<ReportInfo>(
    `/api/v1/analyses/${analysisId}/reports`,
    request,
    signal
  );
}

/** `GET /api/v1/reports/{report_id}/download` — raw Markdown text. */
export function downloadReportMarkdown(
  reportId: string,
  signal?: AbortSignal
): Promise<string> {
  return apiClient.getText(`/api/v1/reports/${reportId}/download`, signal);
}

/**
 * Trigger a browser download of the report Markdown through the credentialed
 * API client, using the server-provided filename. Returns the filename.
 *
 * (A bare anchor to the endpoint is not enough: fetch guarantees cookies on
 * cross-origin calls and lets the UI surface a 404 as an error state.)
 */
export async function saveReportFile(reportId: string, filename: string): Promise<string> {
  const markdown = await downloadReportMarkdown(reportId);
  const blob = new Blob([markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return filename;
}
