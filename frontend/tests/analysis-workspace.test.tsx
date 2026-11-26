import { render, screen, act, fireEvent } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "sonner";

import WorkspacePage from "@/app/(protected)/projects/[project_id]/workspace/page";
import type { AnalysisRun, Project, Snapshot } from "@/types/api";

/**
 * Phase 4B workspace tests: analysis start against the selected snapshot,
 * bounded status polling to completion, failure/retry, snapshot switching,
 * no-snapshot and no-Python-files states, and the poll error/limit paths.
 * All API responses are mocked (tests only).
 *
 * Fake timers run for the whole test (interactions use fireEvent; helper
 * `flush` advances the timer/microtask/react queues), so every poll
 * interval of the component is under test control.
 */

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ project_id: "p1" }),
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

const SNAPSHOT_S1: Snapshot = {
  id: "s1",
  project_id: "p1",
  provider: "github",
  created_at: "2025-06-02T10:00:00Z",
  content_hash: "cafebabedeadbeef1234",
  file_count: 12,
  github_provenance: {
    repository_id: 10,
    full_name: "acme/service-a",
    ref: "main",
    commit_sha: "8f14e45fceea167a",
    imported_at: "2025-06-02T10:00:00Z",
  },
};

const SNAPSHOT_S2: Snapshot = {
  ...SNAPSHOT_S1,
  id: "s2",
  created_at: "2025-06-05T10:00:00Z",
};

function run(overrides: Partial<AnalysisRun> = {}): AnalysisRun {
  return {
    id: "a1",
    snapshot_id: "s1",
    state: "completed",
    created_at: "2025-06-02T11:00:00Z",
    started_at: "2025-06-02T11:00:05Z",
    finished_at: "2025-06-02T11:00:20Z",
    flowlens_version: "0.1.0",
    graph_schema_version: "v1",
    python_file_count: 12,
    symbol_count: 40,
    edge_count: 33,
    diagnostics_summary: {
      syntax_errors: 1,
      unresolved_references: 0,
      ambiguous_references: 0,
      skipped_files: 2,
    },
    error_code: null,
    ...overrides,
  };
}

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: "p1",
    name: "Service A",
    source_provider: "github",
    created_at: "2025-06-01T10:00:00Z",
    updated_at: "2025-06-02T10:00:00Z",
    github_connection: null,
    latest_snapshot: SNAPSHOT_S1,
    latest_analysis: null,
    ...overrides,
  };
}

const SYMBOL_PAGE = {
  items: [
    {
      id: "sym-1",
      kind: "function",
      name: "load_user",
      qualified_name: "app.api:load_user",
      file_path: "app/api.py",
      location: { start_line: 3, end_line: 9 },
      parent_id: null,
    },
  ],
  pagination: { page: 1, per_page: 25, total: 1, total_pages: 1 },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  window.history.replaceState({}, "", "/projects/p1/workspace");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Advance the fake/microtask/react queues until quiet. Each iteration
 * processes queued timers at the current time plus all pending microtasks
 * and commits; a handful of iterations settle the useAsync fetch chains.
 */
async function flush(ticks = 8) {
  for (let i = 0; i < ticks; i += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  }
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function renderPage() {
  return render(
    <>
      <WorkspacePage />
      <Toaster />
    </>
  );
}

/** Shared API routing used by the lifecycle tests. */
function mockBackend(options: {
  snapshots?: Snapshot[];
  getProject?: () => Project;
  startRun?: () => AnalysisRun;
  analysisStates?: Partial<AnalysisRun>[];
  symbols?: unknown;
}) {
  const {
    snapshots = [SNAPSHOT_S1],
    getProject = () => project(),
    startRun = () =>
      run({
        id: "a1",
        state: "queued",
        snapshot_id: SNAPSHOT_S1.id,
        created_at: "2025-06-02T11:00:00Z",
        started_at: null,
        finished_at: null,
      }),
    analysisStates = [{ state: "running" }, { state: "completed" }],
    symbols = SYMBOL_PAGE,
  } = options;

  let pollIndex = 0;
  const startedSpy = vi.fn<(url: string, init?: RequestInit) => void>();

  fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
    const path = String(url);

    if (init?.method === "POST" && path.includes(`/snapshots/${snapshots[0].id}/analyses`)) {
      startedSpy(path, init);
      return json(startRun(), 202);
    }
    if (path.includes("/analyses/") && path.includes("/symbols")) {
      return json(symbols);
    }
    if (path.includes("/analyses/")) {
      const overrides = analysisStates[Math.min(pollIndex, analysisStates.length - 1)];
      pollIndex += 1;
      return json(run(overrides));
    }
    if (path.includes("/projects/p1/snapshots")) {
      return json({
        items: snapshots,
        pagination: { page: 1, per_page: 50, total: snapshots.length },
      });
    }
    if (path.includes("/projects/p1")) {
      return json(getProject());
    }
    return json(
      { error: { code: "NOT_FOUND", message: `unexpected url ${path}`, request_id: "r" } },
      404
    );
  });

  return { startedSpy };
}

describe("project workspace", () => {
  it("starts an analysis for the selected snapshot, polls to completion, and shows symbols", async () => {
    const { startedSpy } = mockBackend({});

    renderPage();
    await flush();

    // Project loads; latest snapshot selected by default.
    expect(screen.getByText("Service A")).toBeInTheDocument();
    expect(
      screen.getByText(/Analyses run against one immutable snapshot/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/main @ 8f14e45f…/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /analyze this snapshot/i }));
    await flush();

    expect(startedSpy).toHaveBeenCalledTimes(1);
    expect(String(startedSpy.mock.calls[0][0])).toContain("/api/v1/snapshots/s1/analyses");
    expect(screen.getByText(/Queued — waiting for the backend/i)).toBeInTheDocument();

    // First poll → running.
    await advance(2_000);
    expect(screen.getByText(/Running — status refreshes automatically/i)).toBeInTheDocument();

    // Second poll → completed: counters, diagnostics, symbol catalog.
    await advance(2_000);
    await flush();

    expect(screen.getByText("Python files")).toBeInTheDocument();
    expect(screen.getByText(/^12$/)).toBeInTheDocument();
    expect(screen.getByText("Syntax errors: 1")).toBeInTheDocument();
    expect(screen.getByText("Skipped files: 2")).toBeInTheDocument();
    expect(screen.getByText("Unresolved references: 0")).toBeInTheDocument();
    expect(screen.getByText("app.api:load_user")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows a failed analysis with its error code and retries into a new queued run", async () => {
    mockBackend({
      getProject: () =>
        project({
          latest_analysis: run({
            state: "failed",
            error_code: "INTERNAL_ERROR",
            python_file_count: undefined,
            diagnostics_summary: undefined,
            finished_at: null,
          }),
        }),
      startRun: () =>
        run({
          id: "a2",
          state: "queued",
          created_at: "2025-06-10T09:00:00Z",
          started_at: null,
          finished_at: null,
          python_file_count: undefined,
          diagnostics_summary: undefined,
        }),
      analysisStates: [{ id: "a2", state: "queued" }],
    });

    renderPage();
    await flush();

    expect((screen.getAllByText(/Analysis failed/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/INTERNAL_ERROR/)).toBeInTheDocument();
    expect(screen.getByText(/retry against the same immutable snapshot/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry analysis/i }));
    await flush();

    // The new (newer) run takes over: the card returns to the queued state.
    expect(screen.getByText(/Queued — waiting for the backend/i)).toBeInTheDocument();
  });

  it("keeps per-snapshot analysis state when switching snapshots", async () => {
    mockBackend({
      snapshots: [SNAPSHOT_S2, SNAPSHOT_S1],
      getProject: () =>
        project({
          latest_snapshot: SNAPSHOT_S2,
          latest_analysis: run({ snapshot_id: "s1", state: "completed" }),
        }),
    });

    renderPage();
    await flush();

    // Latest snapshot s2 selected; the known analysis belongs to s1.
    expect(screen.getByText(/belongs to a different snapshot/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze this snapshot/i })).toBeInTheDocument();

    // Switch to s1 — its completed analysis is shown.
    fireEvent.change(screen.getByLabelText(/analyzed snapshot/i), { target: { value: "s1" } });
    await flush();
    expect(screen.getByText("Python files")).toBeInTheDocument();
    expect(screen.getByText(/^40$/)).toBeInTheDocument();

    // Switch back to s2 — honest unknown state again.
    fireEvent.change(screen.getByLabelText(/analyzed snapshot/i), { target: { value: "s2" } });
    await flush();
    expect(screen.getByText(/belongs to a different snapshot/i)).toBeInTheDocument();
    expect(screen.queryByText("Python files")).not.toBeInTheDocument();
  });

  it("shows an empty state when the project has no source snapshot", async () => {
    mockBackend({
      snapshots: [],
      getProject: () => project({ latest_snapshot: null }),
    });

    renderPage();
    await flush();

    expect(screen.getByText("No source snapshot yet")).toBeInTheDocument();
    expect(
      screen.getByText(/refresh the github connection from the project settings/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open project settings/i })).toBeInTheDocument();
  });

  it("shows the no-Python-files state for a completed empty analysis", async () => {
    mockBackend({
      getProject: () =>
        project({
          latest_analysis: run({
            python_file_count: 0,
            symbol_count: 0,
            edge_count: 0,
            state: "completed",
          }),
        }),
    });

    renderPage();
    await flush();

    expect(screen.getByText("No Python files in this snapshot")).toBeInTheDocument();
    expect(
      screen.getByText(/check that the snapshot contains Python source/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows completed-with-warnings diagnostics prominently", async () => {
    mockBackend({
      getProject: () =>
        project({
          latest_analysis: run({ state: "completed_with_warnings" }),
        }),
    });

    renderPage();
    await flush();

    expect(screen.getByText("Completed with warnings")).toBeInTheDocument();
    expect(screen.getAllByText("Analyzed with warnings").length).toBeGreaterThan(0);
    expect(screen.getByText("Syntax errors: 1")).toBeInTheDocument();
    expect(screen.getByText("Skipped files: 2")).toBeInTheDocument();
    expect(screen.getByText("app.api:load_user")).toBeInTheDocument();
  });

  it("stops polling and offers a manual refresh when a status poll fails", async () => {
    mockBackend({
      analysisStates: [{ state: "running" }, { state: "running" }, { state: "completed" }],
    });
    let pollAttempts = 0;

    // First status poll fails at the transport level; the API client wraps
    // it as a NetworkError ("Could not reach the FlowLens backend.").
    const original = fetchMock.getMockImplementation() as (
      url: URL | string,
      init?: RequestInit
    ) => Promise<Response>;
    fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
      const path = String(url);
      if (path.includes("/analyses/") && !path.includes("/symbols") && init?.method !== "POST") {
        pollAttempts += 1;
        if (pollAttempts === 1) {
          return Promise.reject(new TypeError("network down"));
        }
      }
      return original(url, init);
    });

    renderPage();
    await flush();

    fireEvent.click(screen.getByRole("button", { name: /analyze this snapshot/i }));
    await flush();
    expect(screen.getByText(/Queued — waiting for the backend/i)).toBeInTheDocument();

    // First (failed) poll: polling stops, an actionable error shows.
    await advance(2_000);
    await flush();
    expect(
      screen.getByText(/could not reach the flowlens backend/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();

    // Manual refresh resumes the status loop.
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    await flush();
    expect(
      screen.getByText(/Running — status refreshes automatically/i)
    ).toBeInTheDocument();
  });

  it("stops automatically after the polling budget and says so honestly", async () => {
    mockBackend({ analysisStates: [{ state: "running" }] });

    renderPage();
    await flush();

    fireEvent.click(screen.getByRole("button", { name: /analyze this snapshot/i }));
    await flush();
    expect(screen.getByText(/Queued — waiting for the backend/i)).toBeInTheDocument();

    // 300 polls at 2s each; the next attempt trips the budget.
    await advance(2_000 * 305);

    expect(screen.getByText("Still running")).toBeInTheDocument();
    expect(
      screen.getByText(/automatic status refresh stopped after the polling budget/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();
  });

  it("shows a not-found state for missing or foreign projects", async () => {
    fetchMock.mockResolvedValue(
      json(
        {
          error: {
            code: "PROJECT_NOT_FOUND",
            message: "Project does not exist or is not owned by you.",
            request_id: "r6",
          },
        },
        404
      )
    );

    renderPage();
    await flush();

    expect(screen.getByText("Project not found")).toBeInTheDocument();
    expect(
      screen.getByText(/check the dashboard for your projects/i)
    ).toBeInTheDocument();
  });

  it("links back to settings and the project settings card is reachable", async () => {
    mockBackend({});
    renderPage();
    await flush();

    const settingsLink = screen.getByRole("link", { name: /settings & snapshots/i });
    expect(settingsLink).toHaveAttribute("href", "/projects/p1");
    expect(screen.getByRole("link", { name: /project settings/i })).toHaveAttribute(
      "href",
      "/projects/p1"
    );

    // The rest of the header shows project and workspace labels.
    expect(screen.getByText("Workspace — analyze a snapshot and browse its symbols.")).toBeInTheDocument();
  });
});
