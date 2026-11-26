import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { DiffReviewPanel } from "@/features/diff/components/diff-review-panel";
import type { DiffResult, ImpactResult, RiskFactor } from "@/types/api";

/**
 * Phase 7B diff review panel tests: request wiring, changed-file/symbol
 * rendering (mapped + unmapped + warnings), combined impact display with the
 * shared risk card, honest no-impact state, DIFF_INVALID error handling, and
 * stale-result clearing. All API responses are stubbed fetch responses
 * (tests only; no mocks in product code).
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

function factor(key: RiskFactor["key"], label: string): RiskFactor {
  return {
    key,
    label,
    weight: 0.5,
    normalized_value: 0.4,
    included: true,
  };
}

function impact(overrides: Partial<ImpactResult> = {}): ImpactResult {
  return {
    analysis_id: "a1",
    targets: [{ node_id: "sym1", qualified_name: "app.core:load_data" }],
    direction: "both",
    max_depth: 3,
    impacted: [
      {
        node_id: "n2",
        kind: "function",
        qualified_name: "app.api:handler",
        direct: true,
        min_hops: 1,
        attributed_to: ["sym1"],
      },
      {
        node_id: "n3",
        kind: "function",
        qualified_name: "app.web:route",
        direct: false,
        min_hops: 2,
        attributed_to: ["sym1"],
      },
    ],
    risk: {
      score: 42,
      version: "risk-v1",
      coverage_included: true,
      factors: [factor("upstream_reachable_dependents", "Upstream reachable dependents")],
    },
    warnings: [],
    ...overrides,
  };
}

function diffResult(overrides: Partial<DiffResult> = {}): DiffResult {
  return {
    analysis_id: "a1",
    files: [
      {
        path: "app/core.py",
        change_type: "modified",
        changed_line_count: 12,
        mapped_symbols: [
          { symbol_id: "sym1", qualified_name: "app.core:load_data", change_type: "modified" },
        ],
        unmapped_line_count: 3,
        unmapped_reason: "module-level changes outside any symbol span",
      },
      {
        path: "app/new_api.py",
        change_type: "added",
        changed_line_count: 40,
        mapped_symbols: [],
      },
    ],
    combined_impact: impact(),
    warnings: ["One hunk could not be mapped"],
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

async function analyzeSuccessfully(result: DiffResult) {
  fetchMock.mockResolvedValueOnce(json(result));
  const user = userEvent.setup();
  render(<DiffReviewPanel analysisId="a1" />);
  await user.type(screen.getByLabelText("Unified diff"), "--- a/x.py\n+++ b/x.py");
  await user.click(screen.getByRole("button", { name: /analyze diff/i }));
  await screen.findByText(/changed files/i, {}, { timeout: 5000 });
}

describe("DiffReviewPanel", () => {
  it("disables the analyze action until a diff is provided", () => {
    render(<DiffReviewPanel analysisId="a1" />);
    expect(screen.getByRole("button", { name: /analyze diff/i })).toBeDisabled();
    expect(
      screen.getByText(/no diff has been analyzed yet/i)
    ).toBeInTheDocument();
  });

  it("submits the diff and renders files, mapped/unmapped symbols, and warnings", async () => {
    await analyzeSuccessfully(diffResult());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/diff");
    expect(JSON.parse(options.body as string)).toEqual({
      unified_diff: "--- a/x.py\n+++ b/x.py",
    });

    // Changed files with their change type as text badges.
    expect(screen.getByText("app/core.py")).toBeInTheDocument();
    expect(screen.getByText("app/new_api.py")).toBeInTheDocument();
    expect(screen.getAllByText("modified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("added").length).toBeGreaterThan(0);

    // Mapped symbol, unmapped remainder with the backend's reason.
    expect(screen.getAllByText("app.core:load_data").length).toBeGreaterThan(0);
    expect(screen.getByText(/module-level changes outside any symbol span/i)).toBeInTheDocument();

    // Warnings from the response.
    expect(screen.getByText(/one hunk could not be mapped/i)).toBeInTheDocument();
  });

  it("renders the combined impact table and the backend risk score verbatim", async () => {
    await analyzeSuccessfully(
      diffResult({
        combined_impact: impact({ coverage_summary: { covered: 1, partially_covered: 1, uncovered: 0, unknown: 2 } }),
      })
    );

    expect(screen.getByText("app.api:handler")).toBeInTheDocument();
    expect(screen.getByText("app.web:route")).toBeInTheDocument();
    expect(screen.getAllByText("direct").length).toBeGreaterThan(0);
    expect(screen.getAllByText("indirect").length).toBeGreaterThan(0);

    // Risk comes from the response: 42/100, version, coverage included.
    expect(screen.getByTestId("risk-score-value")).toHaveTextContent("42");
    expect(screen.getByText(/score version risk-v1/i)).toBeInTheDocument();
    expect(screen.getByText(/includes coverage/i)).toBeInTheDocument();

    // Coverage summary of impacted symbols (unknown ≠ zero, in text).
    expect(screen.getByText(/unknown means no coverage information/i)).toBeInTheDocument();
  });

  it("shows the honest no-impact empty state when the backend finds no impacted symbols", async () => {
    await analyzeSuccessfully(
      diffResult({ combined_impact: impact({ impacted: [], targets: [{ node_id: "sym1", qualified_name: "app.core:load_data" }] }) })
    );
    expect(screen.getByText(/no impacted symbols/i)).toBeInTheDocument();
    expect(
      screen.getByText(/not a claim that the change is safe/i)
    ).toBeInTheDocument();
  });

  it("reports files with nothing mapped without hiding them", async () => {
    await analyzeSuccessfully(
      diffResult({
        files: [{ path: "app/mod_only.py", change_type: "modified", changed_line_count: 5 }],
        combined_impact: impact({ impacted: [], targets: [] }),
      })
    );
    expect(screen.getByText(/no symbols were mapped to this file/i)).toBeInTheDocument();
  });

  it("maps DIFF_INVALID to an actionable error with retry", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        { error: { code: "DIFF_INVALID", message: "unparseable", request_id: "req-1" } },
        422
      )
    );
    const user = userEvent.setup();
    render(<DiffReviewPanel analysisId="a1" />);
    await user.type(screen.getByLabelText("Unified diff"), "not a diff");
    await user.click(screen.getByRole("button", { name: /analyze diff/i }));

    expect(
      await screen.findByText(/check that the text is a valid unified diff/i, {}, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(screen.getByText(/diff analysis failed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry analysis/i })).toBeInTheDocument();
  });

  it("clears a stale result when the diff text changes again", async () => {
    await analyzeSuccessfully(diffResult());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Unified diff"), "{backspace}");
    expect(screen.queryByText("app/core.py")).not.toBeInTheDocument();
    expect(screen.getByText(/no diff has been analyzed yet/i)).toBeInTheDocument();
  });
});
