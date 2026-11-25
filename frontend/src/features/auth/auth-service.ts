import { apiClient } from "@/lib/api-client";
import type { SessionState } from "@/types/api";

/** Auth service — typed wrappers for the `/api/v1/auth/*` endpoints. */

/** `GET /api/v1/auth/me` — current session state; never contains tokens. */
export function getCurrentSession(): Promise<SessionState> {
  return apiClient.get<SessionState>("/api/v1/auth/me");
}

/** `POST /api/v1/auth/logout` — invalidates the server session cookie. */
export async function logout(): Promise<void> {
  await apiClient.post<void>("/api/v1/auth/logout");
}

/**
 * `GET /api/v1/auth/github/start` — browser navigation target that begins
 * the GitHub App user authorization flow. Returns the URL to assign to
 * `window.location.href`; do not fetch this endpoint.
 */
export function githubLoginUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  return `${base}/api/v1/auth/github/start`;
}
