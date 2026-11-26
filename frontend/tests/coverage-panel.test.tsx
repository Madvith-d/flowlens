import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { CoveragePanel } from "@/features/coverage/components/coverage-panel";
import { GraphLegend } from "@/features/graph/components/graph-legend";
import { GraphListView } from "@/features/graph/components/graph-list-view";
import type {
  CoverageResult,
  GraphEdge,
  GraphNode,
} from "@/types/api";

/**
 * Phase 7B coverage tests: attach wiring (raw artifact JSON body), summary
 * rendering, unmatched-file/warning display, the "unknown is not uncovered"
 * rule, error states, and the graph overlay (list-view column + legend).
 * All API responses are stubbed fetch responses (tests only).
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

function coverageResult(overrides: Partial<CoverageResult> = {}): CoverageResult {
  return {
    analysis_id: "a1",
    summary: { covered: 10, partially_covered: 4, uncovered: 3, unknown: 12 },
    unmatched_file_count: 2,
    warnings: ["coverage/date missing lines skipped"],
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CoveragePanel", () => {
  it("explains the four statuses and that unknown ≠ zero coverage before attach", () => {
    render(<CoveragePanel analysisId="a1" />);
    expect(screen.getByText(/coverage statuses/i)).toBeInTheDocument();
    expect(
      screen.getByText(/no coverage information — not zero coverage, just no data/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /attach coverage/i })).toBeDisabled();
  });

  it("rejects non-JSON input client-side without any request", async () => {
    const user = userEvent.setup();
    render(<CoveragePanel analysisId="a1" />);
    await user.type(screen.getByLabelText(/Coverage\.py JSON artifact/i), "not json");
    await user.click(screen.getByRole("button", { name: /attach coverage/i }));

    expect(
      screen.getByText(/does not look like JSON/i)
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a JSON scalar before any request (contract expects an object)", async () => {
    render(<CoveragePanel analysisId="a1" />);
    fireEvent.change(screen.getByLabelText(/Coverage\.py JSON artifact/i), {
      target: { value: "[1, 2]" },
    });
    fireEvent.click(screen.getByRole("button", { name: /attach coverage/i }));

    expect(screen.getByText(/must be a JSON object/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs the parsed artifact and renders the summary, unmatched count, and warnings", async () => {
    fetchMock.mockResolvedValueOnce(json(coverageResult()));
    const user = userEvent.setup();
    render(<CoveragePanel analysisId="a1" />);
    fireEvent.change(screen.getByLabelText(/Coverage\.py JSON artifact/i), {
      target: { value: '{"meta": {"format": 3}}' },
    });
    await user.click(screen.getByRole("button", { name: /attach coverage/i }));

    // Summary row: every status count as text; unknown explained, not zeroed.
    await screen.findByText(/coverage summary of this analysis/i, {}, { timeout: 5000 });
    expect(screen.getByText("covered · 10")).toBeInTheDocument();
    expect(screen.getByText("partially covered · 4")).toBeInTheDocument();
    expect(screen.getByText("uncovered · 3")).toBeInTheDocument();
    expect(screen.getByText("unknown · 12")).toBeInTheDocument();
    expect(screen.getByText(/unknown means no coverage information/i)).toBeInTheDocument();

    // Unmatched files reported honestly with their consequence.
    expect(
      screen.getByText(/2 coverage files could not be matched/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/coverage for unmatched files is never attributed to symbols/i)
    ).toBeInTheDocument();

    // Warnings verbatim.
    expect(screen.getByText(/coverage\/date missing lines skipped/i)).toBeInTheDocument();

    // Request wiring: raw artifact object is the body.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/coverage");
    expect(JSON.parse(options.body as string)).toEqual({ meta: { format: 3 } });
    expect(options.credentials).toBe("include");
  });

  it("renders a zero unmatched result without an unmatched alert", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        coverageResult({
          summary: { covered: 1, partially_covered: 0, uncovered: 0, unknown: 0 },
          unmatched_file_count: 0,
          warnings: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<CoveragePanel analysisId="a1" />);
    fireEvent.change(screen.getByLabelText(/Coverage\.py JSON artifact/i), {
      target: { value: '{"files": {}}' },
    });
    await user.click(screen.getByRole("button", { name: /attach coverage/i }));

    await screen.findByText(/coverage summary of this analysis/i, {}, { timeout: 5000 });
    expect(screen.queryByText(/could not be matched/i)).not.toBeInTheDocument();
  });

  it("maps COVERAGE_INVALID to an actionable error with retry", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        { error: { code: "COVERAGE_INVALID", message: "bad artifact", request_id: "req-2" } },
        400
      )
    );
    const user = userEvent.setup();
    render(<CoveragePanel analysisId="a1" />);
    fireEvent.change(screen.getByLabelText(/Coverage\.py JSON artifact/i), {
      target: { value: '{"bad": true}' },
    });
    await user.click(screen.getByRole("button", { name: /attach coverage/i }));

    expect(
      await screen.findByText(/must be the JSON output of `coverage json`/i, {}, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(screen.getByText(/could not attach coverage/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry attaching/i })).toBeInTheDocument();
  });
});

describe("Graph coverage overlay", () => {
  const nodes: GraphNode[] = [
    {
      id: "n1",
      kind: "function",
      name: "load_data",
      qualified_name: "app.core:load_data",
      file_path: "app/core.py",
      parent_id: null,
      coverage_status: "covered",
    },
    {
      id: "n2",
      kind: "function",
      name: "handler",
      qualified_name: "app.api:handler",
      file_path: "app/api.py",
      parent_id: null,
      coverage_status: "unknown",
    },
    {
      id: "n3",
      kind: "function",
      name: "route",
      qualified_name: "app.web:route",
      file_path: "app/web.py",
      parent_id: null,
    },
  ];
  const edges: GraphEdge[] = [];

  it("shows the coverage column with full text statuses when enabled", () => {
    render(
      <GraphListView
        nodes={nodes}
        edges={edges}
        selectedNodeId={null}
        selectedEdgeId={null}
        showCoverage={true}
        onSelectNode={vi.fn()}
        onSelectEdge={vi.fn()}
      />
    );
    const headers = screen.getAllByRole("columnheader");
    expect(headers.some((header) => header.textContent === "Coverage")).toBe(true);
    expect(screen.getByText("covered")).toBeInTheDocument();
    expect(screen.getAllByText("unknown").length).toBeGreaterThan(0);
  });

  it("hides the coverage column when the graph reports no coverage data", () => {
    render(
      <GraphListView
        nodes={nodes}
        edges={edges}
        selectedNodeId={null}
        selectedEdgeId={null}
        onSelectNode={vi.fn()}
        onSelectEdge={vi.fn()}
      />
    );
    expect(
      screen.queryAllByRole("columnheader").filter(
        (header) => header.textContent === "Coverage"
      )
    ).toHaveLength(0);
  });

  it("legend explains the overlay text markers when coverage data exists", () => {
    render(<GraphLegend showCoverage={true} />);
    expect(screen.getByText(/coverage overlay/i)).toBeInTheDocument();
    expect(screen.getByText(/covered — all executable lines/i)).toBeInTheDocument();
    expect(
      screen.getByText(/unknown — no coverage information, never zero coverage/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/does not measure assertion quality/i)).toBeInTheDocument();
  });

  it("legend omits the coverage section when no coverage is attached", () => {
    render(<GraphLegend />);
    expect(screen.queryByText(/coverage overlay/i)).not.toBeInTheDocument();
  });
});
