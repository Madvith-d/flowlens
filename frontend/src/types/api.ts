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
