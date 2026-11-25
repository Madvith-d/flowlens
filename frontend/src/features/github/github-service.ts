import { API_BASE_URL, apiClient } from "@/lib/api-client";
import type { GitHubInstallationList, PaginatedRepositories } from "@/types/api";

/** GitHub integration service — typed wrappers for the `/api/v1/github/*` endpoints. */

/**
 * `GET /api/v1/github/installations` — installations accessible to the
 * signed-in user. The backend verifies against the GitHub API; the list is
 * never derived from browser-supplied data.
 */
export function listInstallations(signal?: AbortSignal): Promise<GitHubInstallationList> {
  return apiClient.get<GitHubInstallationList>("/api/v1/github/installations", undefined, signal);
}

/**
 * `GET /api/v1/github/installations/{installation_id}/repositories` —
 * paginated repositories the user and the installation are both permitted
 * to access. Access is verified server-side; the `visibility` label is
 * informational only and must never be used to infer access.
 */
export function listInstallationRepositories(
  installationId: number,
  params?: { page?: number; perPage?: number },
  signal?: AbortSignal
): Promise<PaginatedRepositories> {
  return apiClient.get<PaginatedRepositories>(
    `/api/v1/github/installations/${installationId}/repositories`,
    { page: params?.page, per_page: params?.perPage },
    signal
  );
}

/**
 * `GET /api/v1/github/install/start` — browser navigation target that begins
 * the GitHub App installation flow. Must be a full-page navigation, never a
 * fetch (GitHub redirects the browser through its own UI).
 */
export function githubInstallUrl(): string {
  return `${API_BASE_URL}/api/v1/github/install/start`;
}
