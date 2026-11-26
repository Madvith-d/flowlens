import { ApiError, NetworkError, toApiError } from "@/lib/api-error";

/**
 * Single shared API client for all FlowLens backend calls.
 *
 * - Base URL from `NEXT_PUBLIC_API_BASE_URL` (see `.env.example`).
 * - Every request sends cookies (`credentials: "include"`) for the
 *   HttpOnly backend session cookie.
 * - Bounded with a default 20s timeout via `AbortSignal.timeout`.
 * - Errors are normalized to `ApiError`/`NetworkError`; raw responses and
 *   stack traces never reach components.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 20_000;

/**
 * Combine a caller-provided signal with a timeout into one controller.
 * Implemented manually (not AbortSignal.any) for broad runtime support.
 */
function withTimeout(timeoutMs: number, external?: AbortSignal): {
  signal: AbortSignal;
  cancel: () => void;
} {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", onAbort);
  }
  return {
    signal: controller.signal,
    cancel: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", onAbort);
    },
  };
}

type QueryValue = string | number | boolean | readonly string[];
/**
 * Query parameter values. Array values (`node_kinds`, `edge_kinds`) are
 * serialized as repeated params (`?kinds=a&kinds=b`), the standard OpenAPI
 * `form` collection format.
 */
type QueryParams = Record<string, QueryValue | undefined | null>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON body. For uploads use `form`. */
  body?: unknown;
  /** multipart/form-data body (e.g. ZIP upload). */
  form?: FormData;
  query?: QueryParams;
  signal?: AbortSignal;
  /** Override the default 20s timeout. */
  timeoutMs?: number;
}

function buildUrl(path: string, query?: QueryParams): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, item);
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

/**
 * Default handler shared by all calls: on a 401 it clears client session
 * state and redirects to login with `?reason=expired`. Replaced by the
 * session provider at runtime so tests and SSR are unaffected.
 */
let handleUnauthorized: () => void = () => {
  if (typeof window !== "undefined") {
    window.location.assign("/login?reason=expired");
  }
};

export function setUnauthorizedHandler(handler: () => void) {
  handleUnauthorized = handler;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, query, signal, timeoutMs } = options;

  const { signal: combinedSignal, cancel } = withTimeout(
    timeoutMs ?? DEFAULT_TIMEOUT_MS,
    signal
  );

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      credentials: "include",
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(form ? {} : { Accept: "application/json" }),
      },
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: combinedSignal,
    });
  } catch (error) {
    cancel();
    // Abort from a caller-controlled signal is not an infrastructure error.
    if (signal?.aborted) throw error;
    throw new NetworkError();
  }
  cancel();

  if (response.status === 401 && !path.startsWith("/api/v1/auth/me")) {
    // Session expired mid-session: hand over to the session-aware handler
    // (redirect to login). `/auth/me` is exempt: the session provider uses a
    // 401 from it to detect the signed-out state without a redirect loop.
    handleUnauthorized();
    throw new ApiError(401, "AUTH_REQUIRED", "Your session has expired. Sign in again.");
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string, query?: QueryParams, signal?: AbortSignal) =>
    request<T>(path, { method: "GET", query, signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: "POST", body, signal }),
  postForm: <T>(path: string, form: FormData, signal?: AbortSignal) =>
    request<T>(path, { method: "POST", form, signal }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/**
 * Absolute URL for endpoints the browser must navigate to directly
 * (OAuth redirect flows), never fetched with XHR.
 */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
