/**
 * TypeScript types aligned with `contracts/openapi.yaml` (v0.1.0).
 *
 * Maintained by the frontend owner from the shared contract. Do not add
 * undocumented response keys; if a payload is missing, request a contract
 * change and update both sides together.
 */

// ---------------------------------------------------------------- primitives

export type ObjectId = string;
export type Timestamp = string;

export type ErrorCode =
  | "VALIDATION_ERROR"
  | "AUTH_REQUIRED"
  | "OAUTH_STATE_INVALID"
  | "GITHUB_TOKEN_ERROR"
  | "GITHUB_API_ERROR"
  | "GITHUB_APP_NOT_CONFIGURED"
  | "INSTALLATION_NOT_FOUND"
  | "REPOSITORY_ACCESS_DENIED"
  | "RATE_LIMITED"
  | "UPLOAD_INVALID"
  | "UPLOAD_TOO_LARGE"
  | "PROJECT_NOT_FOUND"
  | "SNAPSHOT_NOT_FOUND"
  | "ANALYSIS_NOT_FOUND"
  | "ANALYSIS_NOT_READY"
  | "DIFF_INVALID"
  | "COVERAGE_INVALID"
  | "NOT_FOUND"
  | "FORBIDDEN"
  | "CONFLICT"
  | "INTERNAL_ERROR";

/** Shared API error envelope (see `components.schemas.Error`). */
export interface ApiErrorBody {
  error: {
    code: ErrorCode | string;
    message: string;
    details?: Record<string, unknown>;
    request_id: string;
  };
}

// --------------------------------------------------------------------- auth

/** Safe current user object. Never contains GitHub tokens (AuthUser schema). */
export interface AuthUser {
  id: ObjectId;
  github_login: string;
  avatar_url?: string;
  created_at?: Timestamp;
}

/** `GET /api/v1/auth/me` response (SessionState schema). */
export interface SessionState {
  authenticated: boolean;
  user?: AuthUser;
}

// ---------------------------------------------------------------- pagination

export interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages?: number;
}

// -------------------------------------------------------------------- enums

/** `SourceProvider` schema. */
export type SourceProvider = "github" | "upload";

/** `AnalysisState` schema. */
export type AnalysisState =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_warnings"
  | "failed";

/** `NodeKind` schema (module covers file/module granularity). */
export type NodeKind = "module" | "class" | "function" | "method";

// ------------------------------------------------------------------ github

/** `GitHubInstallation` schema — an installation accessible to the user. */
export interface GitHubInstallation {
  id: number;
  account_login: string;
  account_type: "user" | "organization";
  avatar_url?: string;
}

/** `RepositorySummary` schema. */
export interface RepositorySummary {
  id: number;
  full_name: string;
  visibility: "public" | "private";
  default_branch: string;
  owner?: string;
  description?: string | null;
  html_url?: string;
}

/** `GET /api/v1/github/installations` response. */
export interface GitHubInstallationList {
  items: GitHubInstallation[];
}

/** `PaginatedRepositories` schema. */
export interface PaginatedRepositories {
  items: RepositorySummary[];
  pagination: Pagination;
}

// ---------------------------------------------------------------- projects

/** `GitHubConnection` schema — recorded repository link of a project. */
export interface GitHubConnection {
  installation_id: number;
  repository_id: number;
  full_name: string;
  ref: string;
  connected_at: Timestamp;
  visibility?: "public" | "private";
}

/** `DiagnosticsSummary` schema — counts only. */
export interface DiagnosticsSummary {
  syntax_errors?: number;
  unresolved_references?: number;
  ambiguous_references?: number;
  skipped_files?: number;
}

/** `AnalysisRun` schema — latest analysis state/summary of a project. */
export interface AnalysisRun {
  id: ObjectId;
  snapshot_id: ObjectId;
  state: AnalysisState;
  created_at: Timestamp;
  started_at?: Timestamp | null;
  finished_at?: Timestamp | null;
  flowlens_version?: string;
  graph_schema_version: string;
  python_file_count?: number;
  symbol_count?: number;
  edge_count?: number;
  diagnostics_summary?: DiagnosticsSummary;
  error_code?: ErrorCode | string | null;
}

/** `GitHubProvenance` schema — immutable source origin of a snapshot. */
export interface GitHubProvenance {
  repository_id: number;
  full_name: string;
  ref: string;
  commit_sha: string;
  imported_at: Timestamp;
}

/** `Snapshot` schema — immutable source snapshot. */
export interface Snapshot {
  id: ObjectId;
  project_id: ObjectId;
  provider: SourceProvider;
  created_at: Timestamp;
  content_hash: string;
  github_provenance?: GitHubProvenance | null;
  file_count?: number;
}

/** `Project` schema. */
export interface Project {
  id: ObjectId;
  name: string;
  source_provider: SourceProvider;
  created_at: Timestamp;
  updated_at: Timestamp;
  github_connection?: GitHubConnection | null;
  latest_snapshot?: Snapshot | null;
  latest_analysis?: AnalysisRun | null;
}

/** `PaginatedProjects` schema. */
export interface PaginatedProjects {
  items: Project[];
  pagination: Pagination;
}

/** `PaginatedSnapshots` schema. */
export interface PaginatedSnapshots {
  items: Snapshot[];
  pagination: Pagination;
}

// ----------------------------------------------------------------- symbols

/** `SourceLocation` schema — snapshot-relative source span. */
export interface SourceLocation {
  start_line: number;
  end_line: number;
  start_column?: number;
  end_column?: number;
}

/**
 * `Symbol` schema — a module/class/function/method record of an analysis.
 * (`Symbol` is shadowed in TS; the contract schema name is noted here.)
 */
export interface Symbol {
  id: string;
  kind: NodeKind;
  name: string;
  qualified_name: string;
  file_path: string;
  location?: SourceLocation;
  parent_id?: string | null;
}

/** `PaginatedSymbols` schema. */
export interface PaginatedSymbols {
  items: Symbol[];
  pagination: Pagination;
}

// -------------------------------------------------------------------- graph

/** `EdgeKind` schema. `CONTAINS` is structural, not a dependency. */
export type EdgeKind =
  | "CALLS"
  | "IMPORTS"
  | "INHERITS"
  | "REFERENCES"
  | "CONTAINS";

/** `ImpactDirection` schema (also the neighbor-expansion direction filter). */
export type ImpactDirection = "upstream" | "downstream" | "both";

/** `Confidence` schema — resolution confidence of an edge/evidence. */
export type Confidence = "high" | "medium" | "low";

/** `CoverageStatus` schema (unknown, never zero, when coverage is absent). */
export type CoverageStatus =
  | "covered"
  | "partially_covered"
  | "uncovered"
  | "unknown";

/** `view` query enum of `GET /api/v1/analyses/{analysis_id}/graph`. */
export type GraphView = "module" | "class" | "function";

/** `GraphNodeMetrics` schema — degrees and reachable counts. */
export interface GraphNodeMetrics {
  in_degree: number;
  out_degree: number;
  /** Reachable dependents count (optional in the contract). */
  upstream_reachable?: number;
  /** Reachable dependencies count (optional in the contract). */
  downstream_reachable?: number;
}

/** `GraphNode` schema — a Symbol plus optional metrics and coverage. */
export interface GraphNode extends Symbol {
  metrics?: GraphNodeMetrics;
  coverage_status?: CoverageStatus;
}

/** `EdgeEvidence` schema — where the edge was resolved in the source. */
export interface EdgeEvidence {
  file_path: string;
  line: number;
  column?: number;
  /** Source expression that produced the edge (bounded length). */
  expression?: string;
}

/** `GraphEdge` schema — typed, evidenced dependency edge. */
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  confidence: Confidence;
  /** Resolver/strategy name that produced the edge. */
  resolver?: string;
  /** At least one evidence location per dependency edge. */
  evidence: EdgeEvidence[];
}

/** `GraphResponse` schema — bounded graph/neighbors payload. */
export interface GraphResponse {
  analysis_id: ObjectId;
  view: GraphView;
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** True when server-side limits were hit. */
  truncated: boolean;
  total_nodes?: number;
  total_edges?: number;
  /** Unresolved/ambiguous references recorded in diagnostics. */
  unresolved_count?: number;
}
