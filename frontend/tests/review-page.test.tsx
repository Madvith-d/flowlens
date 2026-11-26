import { render, screen } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import ReviewPage from "@/app/(protected)/projects/[project_id]/review/page";
import type { AnalysisRun, Project } from "@/types/api";

/**
 * Phase 7B review page tests: analysis selection for the review tools
 * (`?analysis=` or latest completed), the not-finished and no-analysis
 * states, and that all three panels are mounted against the chosen
 * analysis. Responses are stubbed fetch responses (tests only).
 */

const searchParams = new URLSearchParams();

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ project_id: "p1" }),
  useSearchParams: () => searchParams,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

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

function run(state: AnalysisRun["state"], id = "a1"): AnalysisRun {
  return {
    id,
    snapshot_id: "s1",
    state,
    created_at: "2025-06-02T11:00:00Z",
    graph_schema_version: "v1",
  };
}

function project(latestAnalysis: AnalysisRun | null): Project {
  return {
    id: "p1",
    name: "service-a",
    source_provider: "github",
    created_at: "2025-06-01T10:00:00Z",
    updated_at: "2025-06-02T10:00:00Z",
    latest_snapshot: null,
    latest_analysis: latestAnalysis,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  searchParams.delete("analysis");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProjectReviewPage", () => {
  it("renders all three review tools for a completed analysis", async () => {
    fetchMock.mockResolvedValueOnce(json(project(run("completed"))));
    render(<ReviewPage />);

    expect(await screen.findByText(/review changes — service-a/i, {}, { timeout: 5000 })).toBeInTheDocument();
    // Coverage, diff, and report panels are all present.
    expect(screen.getByText(/coverage overlay/i)).toBeInTheDocument();
    expect(screen.getAllByText(/diff review/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/markdown report/i).length).toBeGreaterThan(0);
    // The analysis id context is displayed.
    expect(screen.getByTitle("a1")).toBeInTheDocument();
    // No review endpoint is called until the user acts.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/v1/projects/p1");
  });

  it("uses the ?analysis= parameter when present, ignoring the latest run", async () => {
    searchParams.set("analysis", "a9");
    fetchMock.mockResolvedValueOnce(json(project(run("running"))));
    render(<ReviewPage />);

    expect(await screen.findByText(/review changes — service-a/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByTitle("a9")).toBeInTheDocument();
  });

  it("shows the honest not-finished state when the latest analysis is not completed", async () => {
    fetchMock.mockResolvedValueOnce(json(project(run("running"))));
    render(<ReviewPage />);

    expect(await screen.findByText(/analysis not finished/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/the latest analysis for this project is running/i)).toBeInTheDocument();
    // No review tools are mounted for an unfinished analysis.
    expect(screen.queryByText(/coverage overlay/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /analyze diff/i })).not.toBeInTheDocument();
  });

  it("shows the no-analysis state when the project has no analysis yet", async () => {
    fetchMock.mockResolvedValueOnce(json(project(null)));
    render(<ReviewPage />);

    expect(await screen.findByText(/no completed analysis yet/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(
      screen.getByText(/run an analysis on a snapshot in the project workspace first/i)
    ).toBeInTheDocument();
  });
});
