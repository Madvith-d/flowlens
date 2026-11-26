import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { GraphWorkspace } from "@/features/graph/components/graph-workspace";
import type { GraphEdge, GraphNode, GraphResponse, ImpactResult, RiskFactor } from "@/types/api";

/**
 * Phase 6B impact visualization tests, rendered through the graph workspace
 * (the panel drives canvas/list highlighting and reuses graph selection).
 * All API responses are stubbed fetch responses (tests only) and Cytoscape
 * is mocked — these tests cover the contract wiring of the impact panel
 * (request shape, direct/indirect rendering, risk display, paths, honest
 * states), not pixel layout.
 */

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("cytoscape", () => {
  const instance = {
    elements: vi.fn(() => ({ remove: vi.fn(), removeClass: vi.fn() })),
    add: vi.fn(),
    on: vi.fn(),
    destroy: vi.fn(),
    fit: vi.fn(),
    zoom: vi.fn(() => 1),
    minZoom: vi.fn(() => 0.1),
    maxZoom: vi.fn(() => 10),
    layout: vi.fn(() => ({ run: vi.fn() })),
    getElementById: vi.fn(() => ({ addClass: vi.fn() })),
  };
  return { default: vi.fn(() => instance) };
});

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

function node(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    kind: "function",
    name: id,
    qualified_name: `app:${id}`,
    file_path: "app/mod.py",
    location: { start_line: 1, end_line: 9 },
    parent_id: null,
    ...overrides,
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  overrides: Partial<GraphEdge> = {}
): GraphEdge {
  return {
    id,
    source,
    target,
    kind: "CALLS",
    confidence: "high",
    resolver: "ast-lexical",
    evidence: [{ file_path: "app/caller.py", line: 12, column: 4, expression: "target()" }],
    ...overrides,
  };
}

const target = node("n1", {
  name: "load_data",
  qualified_name: "app.core:load_data",
  file_path: "app/core.py",
});
const directCaller = node("n2", {
  name: "handler",
  qualified_name: "app.api:handler",
  file_path: "app/api.py",
});
const indirectCaller = node("n3", {
  name: "route",
  qualified_name: "app.web:route",
  file_path: "app/web.py",
});

const baseEdges = [
  edge("e1", "n2", "n1", {
    evidence: [{ file_path: "app/api.py", line: 12, column: 4, expression: "load_data()" }],
  }),
  edge("e2", "n3", "n2", {
    evidence: [{ file_path: "app/web.py", line: 33, column: 8, expression: "handler()" }],
  }),
];

function risk(overrides: Partial<ImpactResult["risk"]> = {}): ImpactResult["risk"] {
  const factors: RiskFactor[] = [
    {
      key: "upstream_reachable_dependents",
      label: "Upstream reachable dependents",
      weight: 0.4375,
      raw_value: 5,
      normalized_value: 0.125,
      included: true,
      description: "Normalized against the configured reachability cap.",
    },
    {
      key: "in_degree_centrality",
      label: "In-degree centrality",
      weight: 0.25,
      raw_value: 2,
      normalized_value: 0.2,
      included: true,
    },
    {
      key: "coverage_deficiency",
      label: "Coverage deficiency",
      weight: 0,
      normalized_value: null,
      included: false,
      description: "No Coverage.py data attached to this analysis.",
    },
  ];
  return {
    score: 42,
    version: "risk-model-v1",
    coverage_included: false,
    factors,
    caveats: [
      "Risk is a prioritization heuristic, not a predicted failure probability.",
      "Coverage data was not available; the remaining factors were renormalized.",
    ],
    ...overrides,
  };
}

function impactResult(extra: Partial<ImpactResult> = {}): ImpactResult {
  return {
    analysis_id: "a1",
    targets: [{ node_id: "n1", qualified_name: "app.core:load_data" }],
    direction: "both",
    max_depth: 3,
    impacted: [
      {
        node_id: "n2",
        kind: "function",
        qualified_name: "app.api:handler",
        direct: true,
        min_hops: 1,
        paths: [{ edges: ["e1"] }],
        attributed_to: ["n1"],
      },
      {
        node_id: "n3",
        kind: "function",
        qualified_name: "app.web:route",
        direct: false,
        min_hops: 2,
        paths: [{ edges: ["e-unknown", "e1"] }],
        attributed_to: ["n1"],
      },
    ],
    truncated: false,
    risk: risk(),
    warnings: ["2 unresolved or ambiguous references were excluded from the graph."],
    ...extra,
  };
}

function defaultHandler(impact: ImpactResult = impactResult()) {
  return async (url: string | URL) => {
    const parsed = new URL(String(url));
    if (parsed.pathname.endsWith("/graph")) {
      return json({
        analysis_id: "a1",
        view: "function",
        nodes: [target, directCaller, indirectCaller],
        edges: baseEdges,
        truncated: false,
      } satisfies GraphResponse);
    }
    const nodeMatch = parsed.pathname.match(/^\/api\/v1\/analyses\/a1\/nodes\/([^/]+)$/);
    if (nodeMatch) {
      const id = decodeURIComponent(nodeMatch[1]);
      const found = [target, directCaller, indirectCaller].find((n) => n.id === id);
      return json(found ?? node(id));
    }
    if (parsed.pathname.endsWith("/neighbors")) {
      return json({ analysis_id: "a1", view: "function", nodes: [], edges: [], truncated: false });
    }
    if (parsed.pathname.endsWith("/impact")) {
      return json(impact);
    }
    if (parsed.pathname.endsWith("/symbols")) {
      return json({ items: [], pagination: { page: 1, per_page: 10, total: 0 } });
    }
    throw new Error(`unexpected request: ${parsed.pathname}`);
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

function impactRequests(): { url: URL; body: Record<string, unknown>; method: string }[] {
  return fetchMock.mock.calls
    .map(([url, options]) => [new URL(String(url)), options] as const)
    .filter(([url]) => url.pathname.endsWith("/impact"))
    .map(([url, options]) => ({
      url,
      body: JSON.parse(String((options as RequestInit).body ?? "{}")) as Record<string, unknown>,
      method: String((options as RequestInit).method ?? "GET"),
    }));
}

/** Adds the (already selected) node as a target and runs the analysis. */
async function addTargetAndRun(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /add .*app\.core:load_data.* as target/i }));
  await user.click(screen.getByRole("button", { name: /run impact analysis/i }));
}

/** Selects n1 via the accessible table view (no canvas interaction needed). */
async function selectTargetNode(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("radio", { name: /table \(accessible list view\)/i }));
  const nodesTable = await screen.findByRole("table", { name: /graph nodes/i });
  await user.click(within(nodesTable).getByText("app.core:load_data"));
}

describe("impact panel (Phase 6B)", () => {
  it("runs impact for the selected node and renders the response verbatim", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);

    // Run is disabled until a target is added; the panel explains what to do.
    expect(screen.getByRole("button", { name: /run impact analysis/i })).toBeDisabled();
    expect(screen.getByText(/no targets yet/i)).toBeInTheDocument();

    await addTargetAndRun(user);

    await waitFor(() => expect(impactRequests()).toHaveLength(1));
    const request = impactRequests()[0];
    expect(request.url.pathname).toBe("/api/v1/analyses/a1/impact");
    expect(request.method).toBe("POST");
    expect(request.body).toEqual({ target_ids: ["n1"], direction: "both", max_depth: 3 });

    // Summary, direct/indirect distinction, and hop distances as text.
    const summary = await screen.findByText(
      (_, element) =>
        element?.getAttribute("aria-live") === "polite" &&
        /direct, 1 indirect/.test(element.textContent ?? "")
    );
    expect(summary.textContent).toMatch(/2 impacted symbols — 1 direct, 1 indirect/);
    const table = screen.getByRole("table", {
      name: /impacted symbols with direct or indirect status/i,
    });
    const firstRow = within(table).getByText("app.api:handler").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(within(firstRow as HTMLElement).getByText("direct")).toBeInTheDocument();
    expect(within(firstRow as HTMLElement).getByText("1 hop")).toBeInTheDocument();
    const secondRow = within(table).getByText("app.web:route").closest("tr");
    expect(within(secondRow as HTMLElement).getByText("indirect")).toBeInTheDocument();
    expect(within(secondRow as HTMLElement).getByText("2 hops")).toBeInTheDocument();
    expect(within(firstRow as HTMLElement).getByText("app.core:load_data")).toBeInTheDocument();

    // Warnings from the backend are surfaced, plus the static-path caveat.
    expect(
      screen.getByText(/2 unresolved or ambiguous references were excluded/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/static reachability does not prove/i)).toBeInTheDocument();
  });

  it("sends the chosen direction and traversal depth", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);

    await user.click(screen.getByRole("radio", { name: /upstream — callers/i }));
    await user.selectOptions(screen.getByLabelText(/maximum traversal depth/i), "5");
    await addTargetAndRun(user);

    await waitFor(() => expect(impactRequests()).toHaveLength(1));
    expect(impactRequests()[0].body).toEqual({
      target_ids: ["n1"],
      direction: "upstream",
      max_depth: 5,
    });
  });

  it("renders the backend risk score and factor breakdown without recalculating", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    const score = await screen.findByTestId("risk-score-value");
    expect(score).toHaveTextContent("42");
    expect(screen.getByText(/score version risk-model-v1/i)).toBeInTheDocument();
    // Coverage disclosure, in text (never color-only).
    expect(screen.getByText(/computed without coverage/i)).toBeInTheDocument();
    expect(screen.getByText(/heuristic · not a failure probability/i)).toBeInTheDocument();

    const factorTable = screen.getByRole("table", {
      name: /risk score factor breakdown/i,
    });
    const upstream = within(factorTable).getByText("Upstream reachable dependents");
    const upstreamRow = upstream.closest("tr") as HTMLElement;
    expect(within(upstreamRow).getByText("43.8%")).toBeInTheDocument(); // 0.4375 weight
    expect(within(upstreamRow).getByText("0.125")).toBeInTheDocument(); // normalized value
    expect(within(upstreamRow).getByText("included")).toBeInTheDocument();
    const coverageRow = within(factorTable).getByText("Coverage deficiency").closest("tr") as HTMLElement;
    expect(within(coverageRow).getByText("excluded")).toBeInTheDocument();
    // Null normalized value and absent raw value both render as em-dashes.
    expect(within(coverageRow).getAllByText("—").length).toBe(2);

    // Backend caveats displayed as-is.
    expect(
      screen.getByText(/prioritization heuristic, not a predicted failure probability/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/renormalized/i)).toBeInTheDocument();
  });

  it("renders an empty state when nothing is impacted", async () => {
    fetchMock.mockImplementation(defaultHandler(impactResult({ impacted: [], warnings: [] })));

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    expect(await screen.findByText("No impacted symbols")).toBeInTheDocument();
    expect(screen.getByText(/try the other direction/i)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /impacted symbols/i })).not.toBeInTheDocument();
  });

  it("maps ANALYSIS_NOT_READY to an actionable error with retry", async () => {
    fetchMock.mockImplementation(async (url: string | URL) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/graph")) {
        return json({
          analysis_id: "a1",
          view: "function",
          nodes: [target],
          edges: [],
          truncated: false,
        } satisfies GraphResponse);
      }
      if (parsed.pathname.endsWith("/impact")) {
        return json(
          {
            error: {
              code: "ANALYSIS_NOT_READY",
              message: "The analysis has not completed yet.",
              request_id: "r9",
            },
          },
          409
        );
      }
      if (parsed.pathname.endsWith("/neighbors")) {
        return json({ analysis_id: "a1", view: "function", nodes: [], edges: [], truncated: false });
      }
      return json(target);
    });

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    expect(await screen.findByText("Impact analysis failed")).toBeInTheDocument();
    expect(screen.getByText(/not available yet — the analysis is still in progress/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("lists missing target ids from a 404 and keeps targets editable", async () => {
    fetchMock.mockImplementation(async (url: string | URL) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/graph")) {
        return json({
          analysis_id: "a1",
          view: "function",
          nodes: [target],
          edges: [],
          truncated: false,
        } satisfies GraphResponse);
      }
      if (parsed.pathname.endsWith("/impact")) {
        return json(
          {
            error: {
              code: "NOT_FOUND",
              message: "Target symbols missing.",
              details: { missing_target_ids: ["n1"] },
              request_id: "r10",
            },
          },
          404
        );
      }
      if (parsed.pathname.endsWith("/neighbors")) {
        return json({ analysis_id: "a1", view: "function", nodes: [], edges: [], truncated: false });
      }
      return json(target);
    });

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    const missingMessage = await screen.findByText(/some impact targets could not be found/i);
    expect(missingMessage.textContent).toContain("(n1)");
    expect(screen.getByText(/remove the stale targets/i)).toBeInTheDocument();
    expect(screen.getByText(/remove the stale targets/i)).toBeInTheDocument();
    // The stale target can be removed with its chip button.
    expect(
      screen.getByRole("button", { name: /remove target app\.core:load_data/i })
    ).toBeInTheDocument();
  });

  it("shows the partial-impact alert when the server truncated the result", async () => {
    fetchMock.mockImplementation(defaultHandler(impactResult({ truncated: true })));

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    expect(await screen.findByText("Partial impact result")).toBeInTheDocument();
    expect(screen.getByText(/the server limited this result/i)).toBeInTheDocument();
  });

  it("selects an impacted node in the graph and shows its representative paths", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    const table = await screen.findByRole("table", {
      name: /impacted symbols with direct or indirect status/i,
    });
    // The direct row comes first; select it.
    const selectButtons = within(table).getAllByRole("button", { name: /select in graph/i });
    await user.click(selectButtons[0]);

    // Selection flows into the graph workspace (node detail + neighbors fetch).
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/nodes/n2"))).toBe(true);
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("/nodes/n2/neighbors"))
      ).toBe(true);
    });

    // Path details render the returned edge sequence with visible-graph data.
    expect(await screen.findByText(/representative paths — app\.api:handler/i)).toBeInTheDocument();
    expect(await screen.findByText(/Path 1 — 1 edge/i)).toBeInTheDocument();
    expect(screen.getByText(/runs impacted → target/i)).toBeInTheDocument();
    // The chain endpoints appear in the path list (qualified names).
    expect(screen.getAllByText("app.api:handler").length).toBeGreaterThan(0);
    expect(screen.getAllByText("app.core:load_data").length).toBeGreaterThan(0);
    // At least one chain entry exposes its evidence for inspection
    // (selected-node details also render it per edge).
    expect(
      screen.getAllByRole("button", { name: /evidence: app\/api\.py:12/i }).length
    ).toBeGreaterThan(0);
  });

  it("shows missing path edges as bare ids instead of reconstructing them", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    const table = await screen.findByRole("table", {
      name: /impacted symbols with direct or indirect status/i,
    });
    // The indirect row (app.web:route) has a path whose middle edge is not
    // in the visible graph: "Select in graph" buttons appear in row order.
    const buttons = within(table).getAllByRole("button", { name: /select in graph/i });
    await user.click(buttons[1]);

    expect(await screen.findByText(/representative paths — app\.web:route/i)).toBeInTheDocument();
    expect(screen.getByText(/edge e-unknown/i)).toBeInTheDocument();
    expect(screen.getByText(/not in the visible graph/i)).toBeInTheDocument();
    // No orientation is claimed for a path that cannot be fully resolved.
    expect(screen.queryByText(/runs impacted → target/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/runs target → impacted/i)).not.toBeInTheDocument();
  });

  it("renders impact status in the accessible table view and legend as text", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    // Table view (keyboard/AT accessible) labels every node's impact status.
    const nodesTable = await screen.findByRole("table", { name: /graph nodes/i });
    const handlerRow = within(nodesTable).getByText("app.api:handler").closest("tr") as HTMLElement;
    expect(within(handlerRow).getByText("direct impact")).toBeInTheDocument();
    const routeRow = within(nodesTable).getByText("app.web:route").closest("tr") as HTMLElement;
    expect(within(routeRow).getByText("indirect impact")).toBeInTheDocument();
    const targetRow = within(nodesTable).getByText("app.core:load_data").closest("tr") as HTMLElement;
    expect(within(targetRow).getByText("target")).toBeInTheDocument();

    // The canvas legend restates the same meaning in text (never color-only).
    await user.click(screen.getByRole("radio", { name: /^canvas$/i }));
    expect(await screen.findByText(/impact target — solid blue outline/i)).toBeInTheDocument();
    expect(screen.getByText(/direct impact — solid green outline/i)).toBeInTheDocument();
    expect(screen.getByText(/indirect impact — dashed amber outline/i)).toBeInTheDocument();
  });

  it("removes a target chip and clears a stale result", async () => {
    fetchMock.mockImplementation(defaultHandler());

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    const user = userEvent.setup();
    await selectTargetNode(user);
    await addTargetAndRun(user);

    expect(await screen.findByText(/2 impacted symbols/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove target app\.core:load_data/i }));
    expect(screen.getByRole("button", { name: /run impact analysis/i })).toBeDisabled();
    expect(screen.getByText(/no targets yet/i)).toBeInTheDocument();
    // The result for the removed target set is no longer shown as current.
    expect(
      screen.queryByText(
        (_, element) =>
          element?.getAttribute("aria-live") === "polite" &&
          /direct, 1 indirect/.test(element.textContent ?? "")
      )
    ).not.toBeInTheDocument();
  });
});
