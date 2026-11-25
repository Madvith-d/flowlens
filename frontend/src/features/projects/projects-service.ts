import { API_BASE_URL, apiClient } from "@/lib/api-client";
import { ApiError, NetworkError, toApiError } from "@/lib/api-error";
import type { PaginatedProjects, PaginatedSnapshots, Project, Snapshot } from "@/types/api";

/**
 * Projects service — typed wrappers for the `/api/v1/projects/*` endpoints.
 * All responses come from the backend; the frontend never derives project
 * data or access decisions locally.
 */

const UPLOAD_TIMEOUT_MS = 120_000;

/** `GET /api/v1/projects` — the current user's projects. */
export function listProjects(
  params?: { page?: number; perPage?: number },
  signal?: AbortSignal
): Promise<PaginatedProjects> {
  return apiClient.get<PaginatedProjects>(
    "/api/v1/projects",
    { page: params?.page, per_page: params?.perPage },
    signal
  );
}

/** `POST /api/v1/projects` — create a project record without a snapshot. */
export function createProject(input: { name: string }): Promise<Project> {
  return apiClient.post<Project>("/api/v1/projects", input);
}

/**
 * `GET /api/v1/projects/{project_id}` — project detail with source provenance.
 * Returns 404 when the project does not exist or is not owned by the user.
 */
export function getProject(projectId: string, signal?: AbortSignal): Promise<Project> {
  return apiClient.get<Project>(`/api/v1/projects/${projectId}`, undefined, signal);
}

/** `GET /api/v1/projects/{project_id}/snapshots` — immutable snapshots, newest first. */
export function listSnapshots(
  projectId: string,
  params?: { page?: number; perPage?: number },
  signal?: AbortSignal
): Promise<PaginatedSnapshots> {
  return apiClient.get<PaginatedSnapshots>(
    `/api/v1/projects/${projectId}/snapshots`,
    { page: params?.page, per_page: params?.perPage },
    signal
  );
}

/**
 * `POST /api/v1/projects/from-github` — import from a verified repository.
 * The backend verifies installation, repository ID, and ref server-side;
 * the ref is resolved to a commit SHA recorded as snapshot provenance.
 */
export function createProjectFromGithub(input: {
  repository_id: number;
  installation_id: number;
  ref: string;
  name?: string;
}): Promise<Project> {
  return apiClient.post<Project>("/api/v1/projects/from-github", input);
}

/**
 * `POST /api/v1/projects/{project_id}/refresh` — fetch the recorded ref again
 * into a NEW immutable snapshot. Historical snapshots are never mutated.
 * `ref` optionally snapshots a different branch/tag/commit.
 */
export function refreshProject(projectId: string, ref?: string): Promise<Snapshot> {
  return apiClient.post<Snapshot>(`/api/v1/projects/${projectId}/refresh`, ref ? { ref } : {});
}

/**
 * `DELETE /api/v1/projects/{project_id}/github-connection` — disconnect the
 * repository link. Existing snapshots and reports are retained (documented
 * by the screen; the backend enforces retention).
 */
export function disconnectGithubConnection(projectId: string): Promise<void> {
  return apiClient.delete<void>(`/api/v1/projects/${projectId}/github-connection`);
}

export interface UploadProgress {
  /** Bytes sent so far; equals `total` once the request body is uploaded. */
  loaded: number;
  /** Total bytes to send. */
  total: number;
}

/**
 * `POST /api/v1/projects/from-upload` — create a project and its first
 * immutable snapshot from a ZIP archive (multipart/form-data).
 *
 * Uses `XMLHttpRequest` (not fetch) because fetch cannot report real upload
 * progress; `onProgress` is wired to native `xhr.upload.onprogress` events.
 * No fake progress is ever displayed. `withCredentials` keeps the same
 * HttpOnly session cookie semantics as the shared API client, and error
 * responses are normalized through the shared error envelope parser.
 */
export function createProjectFromUpload(input: {
  file: File;
  name?: string;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}): Promise<Project> {
  return new Promise<Project>((resolve, reject) => {
    const form = new FormData();
    form.append("file", input.file);
    if (input.name) {
      form.append("name", input.name);
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/v1/projects/from-upload`);
    xhr.withCredentials = true;
    xhr.timeout = UPLOAD_TIMEOUT_MS;

    if (input.onProgress) {
      const report = input.onProgress;
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          report({ loaded: event.loaded, total: event.total });
        }
      };
    }

    let abortedByCaller = false;
    const abortFromSignal = () => {
      abortedByCaller = true;
      xhr.abort();
    };
    input.signal?.addEventListener("abort", abortFromSignal);

    const cleanup = () => input.signal?.removeEventListener("abort", abortFromSignal);

    xhr.onload = () => {
      cleanup();
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Project);
        } catch {
          reject(
            new ApiError(
              xhr.status,
              "INTERNAL_ERROR",
              "FlowLens received an unreadable response while creating the project."
            )
          );
        }
        return;
      }
      // Normalize through the shared error-envelope parser (same as fetch).
      const responseLike = {
        status: xhr.status,
        clone: () => responseLike,
        json: async () => JSON.parse(xhr.responseText),
      } as unknown as Response;
      toApiError(responseLike).then(reject, reject);
    };

    const failWith = (error: Error) => {
      cleanup();
      reject(error);
    };

    xhr.onerror = () =>
      failWith(
        new NetworkError("The upload could not reach the FlowLens backend.")
      );
    xhr.ontimeout = () =>
      failWith(
        new NetworkError("The upload timed out. Try again or use a smaller archive.")
      );
    xhr.onabort = () =>
      failWith(
        abortedByCaller
          ? new NetworkError("Upload cancelled.")
          : new NetworkError("The upload was interrupted.")
      );

    xhr.send(form);
  });
}
