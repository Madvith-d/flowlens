import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { analyzeDiff, diffRunError } from "@/features/diff/diff-service";
import { attachCoverage, coverageAttachError } from "@/features/coverage/coverage-service";
import {
  downloadReportMarkdown,
  generateReport,
} from "@/features/reports/reports-service";
import { ApiError } from "@/lib/api-error";
import { NetworkError } from "@/lib/api-error";

/**
 * Phase 7B service wiring tests: the exact URL, method, credentials, headers,
 * and JSON bodies of the frozen diff/coverage/report endpoint group in
 * `contracts/openapi.yaml`, plus the error-code mapping. Responses are
 * stubbed fetch responses (tests only — no mocks in product code paths).
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

function markdown(body: string, status = 200): Response {
  return {
    ok: status < 400,
    status,
    clone() {
      return markdown(body, status);
    },
    text: async () => body,
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

describe("analyzeDiff", () => {
  it("POSTs { unified_diff } as the documented body with cookies", async () => {
    const response = {
      analysis_id: "a1",
      files: [],
      combined_impact: null,
      warnings: [],
    };
    fetchMock.mockResolvedValueOnce(json(response));

    const result = await analyzeDiff("a1", "--- a/x.py\n+++ b/x.py");

    expect(result).toBe(response);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/diff");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body as string)).toEqual({
      unified_diff: "--- a/x.py\n+++ b/x.py",
    });
    expect((options.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});

describe("diffRunError", () => {
  it("maps DIFF_INVALID (422) to an actionable message", () => {
    const error = new ApiError(422, "DIFF_INVALID", "Bad diff.");
    expect(diffRunError(error)).toMatch(/could not be parsed.*unified diff/i);
  });

  it("maps ANALYSIS_NOT_READY to an in-progress message", () => {
    const error = new ApiError(409, "ANALYSIS_NOT_READY", "Analysis running.");
    expect(diffRunError(error)).toMatch(/still in progress/i);
  });

  it("falls back to the shared message for other errors", () => {
    expect(diffRunError(new NetworkError())).toBe("Could not reach the FlowLens backend.");
    const other = new ApiError(400, "VALIDATION_ERROR", "Empty diff.");
    expect(diffRunError(other)).toBe("Empty diff.");
  });
});

describe("attachCoverage", () => {
  it("POSTs the raw coverage JSON object as the body (no wrapper)", async () => {
    const artifact = { meta: { format: 3 }, files: { "app/core.py": {} } };
    const response = {
      analysis_id: "a1",
      summary: { covered: 5, partially_covered: 2, uncovered: 1, unknown: 8 },
      warnings: [],
    };
    fetchMock.mockResolvedValueOnce(json(response));

    const result = await attachCoverage("a1", artifact as Record<string, unknown>);

    expect(result).toBe(response);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/coverage");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body as string)).toEqual(artifact);
  });

  it("maps COVERAGE_INVALID to an actionable message", () => {
    const error = new ApiError(400, "COVERAGE_INVALID", "Not coverage json.");
    expect(coverageAttachError(error)).toMatch(/must be the JSON output of `coverage json`/i);
  });

  it("falls back to the shared message for other errors", () => {
    expect(coverageAttachError(new NetworkError())).toBe(
      "Could not reach the FlowLens backend."
    );
  });
});

describe("generateReport", () => {
  it("POSTs with no body when unscoped and returns ReportInfo", async () => {
    const response = {
      id: "r1",
      analysis_id: "a1",
      format: "markdown",
      created_at: "2025-06-10T10:00:00Z",
      filename: "flowlens-report-a1.md",
    };
    fetchMock.mockResolvedValueOnce(json(response, 201));

    const result = await generateReport("a1");

    expect(result).toEqual(response);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/reports");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.body).toBeUndefined();
    expect((options.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("POSTs the optional scoping body when targets are given", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ id: "r2", analysis_id: "a1", format: "markdown", created_at: "2025-06-10T10:00:00Z", filename: "r.md" }, 201)
    );

    await generateReport("a1", {
      target_ids: ["sym1", "sym2"],
      direction: "both",
      max_depth: 3,
    });

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(options.body as string)).toEqual({
      target_ids: ["sym1", "sym2"],
      direction: "both",
      max_depth: 3,
    });
  });
});

describe("downloadReportMarkdown", () => {
  it("GETs the download endpoint with cookies and returns the raw markdown text", async () => {
    fetchMock.mockResolvedValueOnce(markdown("# Impact report\n\n..."));

    const text = await downloadReportMarkdown("r1");

    expect(text).toBe("# Impact report\n\n...");
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/reports/r1/download");
    expect(options.method).toBe("GET");
    expect(options.credentials).toBe("include");
    expect((options.headers as Record<string, string>).Accept).toBe("text/markdown");
  });

  it("maps a 404 to the shared not-found error", async () => {
    fetchMock.mockResolvedValueOnce(markdown("", 404));

    await expect(downloadReportMarkdown("missing")).rejects.toThrow(
      /requested resource was not found/i
    );
  });
});
