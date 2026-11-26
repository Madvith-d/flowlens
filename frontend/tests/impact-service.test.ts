import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { computeImpact, impactRunError } from "@/features/impact/impact-service";
import { ApiError } from "@/lib/api-error";
import { NetworkError } from "@/lib/api-error";

/**
 * Impact service wiring tests: exact URL, method, credentials, and JSON body
 * of the frozen `POST /api/v1/analyses/{analysis_id}/impact` contract, plus
 * the error-code mapping. Responses are stubbed (tests only).
 */

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    clone() {
      return json(body, status);
    },
    json: async () => body,
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("computeImpact", () => {
  it("POSTs the documented request shape with cookies", async () => {
    const response = { analysis_id: "a1", targets: [], direction: "both", impacted: [], risk: null, warnings: [] };
    fetchMock.mockResolvedValueOnce(json(response));

    const result = await computeImpact("a1", {
      target_ids: ["n1", "n2"],
      direction: "upstream",
      max_depth: 5,
    });

    expect(result).toBe(response);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/impact");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body as string)).toEqual({
      target_ids: ["n1", "n2"],
      direction: "upstream",
      max_depth: 5,
    });
    expect((options.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("sends max_depth only as a request field, never a query parameter", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ analysis_id: "a1", targets: [], direction: "both", impacted: [], risk: null, warnings: [] })
    );

    await computeImpact("a1", { target_ids: ["n1"], direction: "both", max_depth: 3 });

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/impact");
    expect(url.includes("?")).toBe(false);
  });
});

describe("impactRunError", () => {
  it("maps ANALYSIS_NOT_READY (409) to an actionable message", () => {
    const error = new ApiError(409, "ANALYSIS_NOT_READY", "Analysis not finished.");
    expect(impactRunError(error)).toMatch(/not available yet — the analysis is still in progress/i);
  });

  it("lists missing target ids from the 404 error details", () => {
    const error = new ApiError(404, "NOT_FOUND", "Targets missing.", {
      details: { missing_target_ids: ["n7", "n8"] },
    });
    const message = impactRunError(error);
    expect(message).toContain("n7, n8");
    expect(message).toMatch(/remove the stale targets/i);
  });

  it("falls back to the shared message for other errors", () => {
    expect(impactRunError(new NetworkError())).toBe("Could not reach the FlowLens backend.");
    const other = new ApiError(400, "VALIDATION_ERROR", "Too many targets.");
    expect(impactRunError(other)).toBe("Too many targets.");
  });
});
