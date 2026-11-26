import { apiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import type {
  EdgeKind,
  GraphNode,
  GraphResponse,
  GraphView,
  ImpactDirection,
  NodeKind,
} from "@/types/api";

/**
 * Graph service — typed wrappers for the graph endpoint group in
 * `contracts/openapi.yaml`:
 *
 * - `GET /api/v1/analyses/{analysis_id}/graph` (filtered, bounded subgraph)
 * - `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}` (node detail)
 * - `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}/neighbors`
 *   (bounded neighborhood expansion)
 *
 * All filters, limits, and results come from the backend; the frontend never
 * fabricates nodes, edges, metrics, or truncation flags.
 */

/** Filters of `GET /graph` exactly as documented in the contract. */
export interface GraphFilters {
  /** Granularity level; contract default is `function`. */
  view?: GraphView;
  /** Node kind filter (repeated `node_kinds` query params). */
  nodeKinds?: readonly NodeKind[];
  /** Edge kind filter (repeated `edge_kinds` query params). */
  edgeKinds?: readonly EdgeKind[];
  /** Maximum number of nodes returned; contract max is 2000. */
  limit?: number;
}

/** `GET /api/v1/analyses/{analysis_id}/graph` — bounded filtered subgraph. */
export function getGraph(
  analysisId: string,
  filters?: GraphFilters,
  signal?: AbortSignal
): Promise<GraphResponse> {
  return apiClient.get<GraphResponse>(
    `/api/v1/analyses/${analysisId}/graph`,
    {
      view: filters?.view,
      node_kinds: filters?.nodeKinds && filters.nodeKinds.length > 0
        ? filters.nodeKinds
        : undefined,
      edge_kinds: filters?.edgeKinds && filters.edgeKinds.length > 0
        ? filters.edgeKinds
        : undefined,
      limit: filters?.limit,
    },
    signal
  );
}

/** `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}` — node detail. */
export function getNode(
  analysisId: string,
  nodeId: string,
  signal?: AbortSignal
): Promise<GraphNode> {
  return apiClient.get<GraphNode>(
    `/api/v1/analyses/${analysisId}/nodes/${encodeURIComponent(nodeId)}`,
    undefined,
    signal
  );
}

/**
 * `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}/neighbors` — bounded
 * neighborhood expansion. `depth` is 1–3, `limit` max 500, per the contract.
 */
export function getNodeNeighbors(
  analysisId: string,
  nodeId: string,
  params?: { depth?: number; direction?: ImpactDirection; limit?: number },
  signal?: AbortSignal
): Promise<GraphResponse> {
  return apiClient.get<GraphResponse>(
    `/api/v1/analyses/${analysisId}/nodes/${encodeURIComponent(nodeId)}/neighbors`,
    {
      depth: params?.depth,
      direction: params?.direction,
      limit: params?.limit,
    },
    signal
  );
}

/**
 * Map an API error to a graph-specific message. `ANALYSIS_NOT_READY`
 * (graph/graph-adjacent request for a still-pending analysis) is the known
 * case; everything else falls back to the shared error message.
 */
export function graphLoadError(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === "ANALYSIS_NOT_READY") {
    return "The dependency graph is not available yet — the analysis is still in progress.";
  }
  return errorMessage(cause);
}
