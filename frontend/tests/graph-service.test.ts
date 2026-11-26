import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { getGraph, getNode, getNodeNeighbors, graphLoadError } from "@/features/graph/graph-service";
import { ApiError } from "@/lib/api-error";

/**
 * Graph service tests: exact query/path construction of the graph endpoint
 * group against `contracts/openapi.yaml` (repeated `node_kinds`/`edge_kinds`
 * array params, `view`/`limit`, node detail path, neighbor depth/direction),
 * plus the `ANALYSIS_NOT_READY` error mapping. fetch is stubbed (tests only).
 */

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => {
    throw new Error("unexpected fetch");
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    clone() {
      return jsonResponse(body, status);
    },
    json: async () => body,
  } as unknown as Response;
}

function calledUrl(): URL {
  const [url] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string];
  return new URL(String(url));
}

describe("graph service", () => {
  it("sends only view and limit by default for the filtered graph request", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        analysis_id: "a1",
        view: "function",
        nodes: [],
        edges: [],
        truncated: false,
      })
    );

    await getGraph("a1", { view: "function", limit: 500 });

    const url = calledUrl();
    expect(url.pathname).toBe("/api/v1/analyses/a1/graph");
    expect(url.searchParams.get("view")).toBe("function");
    expect(url.searchParams.get("limit")).toBe("500");
    expect(url.searchParams.has("node_kinds")).toBe(false);
    expect(url.searchParams.has("edge_kinds")).toBe(false);
  });

  it("serializes node/edge kind filters as repeated query params", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        analysis_id: "a1",
        view: "class",
        nodes: [],
        edges: [],
        truncated: false,
      })
    );

    await getGraph("a1", {
      view: "class",
      nodeKinds: ["class", "module"],
      edgeKinds: ["CALLS"],
    });

    const url = calledUrl();
    expect(url.searchParams.getAll("node_kinds")).toEqual(["class", "module"]);
    expect(url.searchParams.getAll("edge_kinds")).toEqual(["CALLS"]);
  });

  it("requests a node detail by id", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "n1",
        kind: "method",
        name: "save",
        qualified_name: "app.models:User.save",
        file_path: "app/models.py",
      })
    );

    await getNode("a1", "n1");

    expect(calledUrl().pathname).toBe("/api/v1/analyses/a1/nodes/n1");
  });

  it("sends neighbor depth, direction and limit as documented", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        analysis_id: "a1",
        view: "function",
        nodes: [],
        edges: [],
        truncated: false,
      })
    );

    await getNodeNeighbors("a1", "n1", { depth: 2, direction: "upstream", limit: 200 });

    const url = calledUrl();
    expect(url.pathname).toBe("/api/v1/analyses/a1/nodes/n1/neighbors");
    expect(url.searchParams.get("depth")).toBe("2");
    expect(url.searchParams.get("direction")).toBe("upstream");
    expect(url.searchParams.get("limit")).toBe("200");
  });

  it("maps ANALYSIS_NOT_READY to an actionable message", () => {
    const error = graphLoadError(
      new ApiError(409, "ANALYSIS_NOT_READY", "The analysis has not completed yet.")
    );
    expect(error).toMatch(/not available yet/i);
  });

  it("leaves other error messages untouched", () => {
    const error = graphLoadError(new ApiError(404, "ANALYSIS_NOT_FOUND", "No such analysis."));
    expect(error).toBe("No such analysis.");
  });
});
