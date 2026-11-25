import type { ApiErrorBody, ErrorCode } from "@/types/api";

/**
 * Error raised by the shared API client. Wraps the backend error envelope
 * (`{ error: { code, message, request_id } }`) and never carries stack
 * traces or raw backend text into UI.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | string;
  readonly requestId?: string;
  readonly details?: Record<string, unknown>;
  /** True when the app session is missing/expired and the user must sign in again. */
  readonly isAuthError: boolean;

  constructor(
    status: number,
    code: ErrorCode | string,
    message: string,
    options?: { requestId?: string; details?: Record<string, unknown> }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = options?.requestId;
    this.details = options?.details;
    this.isAuthError = status === 401;
  }
}

/** Network-level failure (backend unreachable, DNS, CORS, abort). */
export class NetworkError extends Error {
  constructor(message = "Could not reach the FlowLens backend.") {
    super(message);
    this.name = "NetworkError";
  }
}

function fallbackMessage(status: number): string {
  switch (status) {
    case 401:
      return "Your session has expired or you are signed out. Sign in again to continue.";
    case 403:
      return "FlowLens does not have access to this resource.";
    case 404:
      return "The requested resource was not found.";
    case 409:
      return "This action conflicts with the current state. Refresh and try again.";
    case 413:
      return "The upload is too large.";
    case 429:
      return "Too many requests. Wait a moment and try again.";
    default:
      return "An unexpected error occurred. Please try again.";
  }
}

/**
 * Map a fetch `Response` to an `ApiError`, preferring the documented error
 * envelope when the body parses, and a safe fallback otherwise.
 */
export async function toApiError(response: Response): Promise<ApiError> {
  let code: string = "INTERNAL_ERROR";
  let message = fallbackMessage(response.status);
  let requestId: string | undefined;
  let details: Record<string, unknown> | undefined;

  try {
    const body = (await response.clone().json()) as Partial<ApiErrorBody>;
    if (body?.error) {
      code = body.error.code;
      if (typeof body.error.message === "string" && body.error.message.length > 0) {
        message = body.error.message;
      }
      requestId = body.error.request_id;
      details = body.error.details;
    }
  } catch {
    // Non-JSON body (e.g. HTML error page): keep the safe fallback message.
  }

  return new ApiError(response.status, code, message, { requestId, details });
}
