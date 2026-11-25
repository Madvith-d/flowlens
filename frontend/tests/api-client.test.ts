import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient, setUnauthorizedHandler } from "@/lib/api-client";
import { ApiError, NetworkError } from "@/lib/api-error";

/**
 * Unit tests for the shared API client:
 * credentials handling, base URL, error envelope mapping, 401 handling,
 * network failures, and JSON/multipart bodies.
 */

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return {
    ok: init.status ? init.status < 400 : true,
    status: init.status ?? 200,
    json: async () => body,
    clone() {
      return jsonResponse(body, init);
    },
  } as unknown as Response;
}

describe("apiClient", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    setUnauthorizedHandler(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("sends cookies with credentials: include on every request", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ authenticated: false }));

    await apiClient.get("/api/v1/auth/me");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect(url).toBe("http://localhost:8000/api/v1/auth/me");
  });

  it("uses NEXT_PUBLIC_API_BASE_URL when provided", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.flowlens.test");
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    const { apiClient: fresh } = await import("@/lib/api-client");

    await fresh.get("/api/v1/health");

    const [url] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe("https://api.flowlens.test/api/v1/health");
  });

  it("serializes JSON bodies and sets the content type", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ authenticated: false }));

    await apiClient.post("/api/v1/auth/logout", { example: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ example: true }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json"
    );
  });

  it("passes FormData bodies untouched for multipart uploads", async () => {
    const form = new FormData();
    form.append("name", "demo");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "p1" }, { status: 201 }));

    await apiClient.postForm("/api/v1/projects/from-upload", form);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe(form);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("appends query parameters and skips empty values", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }));

    await apiClient.get("/api/v1/projects", { page: 2, q: undefined });

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/projects?page=2");
    expect(url).not.toContain("q=");
  });

  it("maps the shared error envelope to ApiError with code and request_id", async () => {
    const body = {
      error: {
        code: "REPOSITORY_ACCESS_DENIED",
        message: "FlowLens does not have access to this repository.",
        request_id: "req-123",
        details: { repository_id: 42 },
      },
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(body, { status: 403 }));

    const error = await apiClient
      .get("/api/v1/github/installations")
      .then(() => {
        throw new Error("should have thrown");
      })
      .catch((e: unknown) => e as ApiError);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(403);
    expect((error as ApiError).code).toBe("REPOSITORY_ACCESS_DENIED");
    expect((error as ApiError).message).toBe(
      "FlowLens does not have access to this repository."
    );
    expect((error as ApiError).requestId).toBe("req-123");
    expect((error as ApiError).isAuthError).toBe(false);
  });

  it("falls back to a safe message when the error body is not the documented envelope", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse("<html>Server error</html>", { status: 500 }));

    const error = (await apiClient
      .get("/api/v1/projects")
      .catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("INTERNAL_ERROR");
    expect(error.message).toBe("An unexpected error occurred. Please try again.");
  });

  it("signals auth-expiry and invokes the unauthorized handler on a mid-session 401", async () => {
    const unauthorized = vi.fn();
    setUnauthorizedHandler(unauthorized);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "AUTH_REQUIRED", message: "expired", request_id: "r1" } },
        { status: 401 }
      )
    );

    const error = (await apiClient.get("/api/v1/projects").catch((e: unknown) => e)) as ApiError;

    expect(unauthorized).toHaveBeenCalledTimes(1);
    expect(error.isAuthError).toBe(true);
    expect(error.code).toBe("AUTH_REQUIRED");
  });

  it("does not fire the redirect handler for /auth/me 401s", async () => {
    const unauthorized = vi.fn();
    setUnauthorizedHandler(unauthorized);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "AUTH_REQUIRED", message: "no session", request_id: "r2" } },
        { status: 401 }
      )
    );

    const session = await apiClient.get("/api/v1/auth/me").catch((e: unknown) => e);
    expect(unauthorized).not.toHaveBeenCalled();
    expect((session as ApiError).isAuthError).toBe(true);
  });

  it("raises NetworkError when the backend is unreachable", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const error = await apiClient.get("/api/v1/auth/me").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(NetworkError);
  });

  it("resolves 204 No Content responses as undefined", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      clone() {
        return this;
      },
      json: async () => {
        throw new Error("no body");
      },
    } as unknown as Response);

    await expect(apiClient.post("/api/v1/auth/logout")).resolves.toBeUndefined();
  });
});
