import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { GraphWorkspace } from "@/features/graph/components/graph-workspace";
import type { GraphEdge, GraphNode, GraphResponse } from "@/types/api";

/**
 * Phase 5B interactive graph workspace tests. All API responses are stubbed
 * fetch responses (tests only) and Cytoscape itself is mocked — these tests
 * cover the contract wiring (filters, search, node detail, neighbor
 * expansion, evidence display) and honest state handling, not pixel layout.
 */

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// Mock the renderer: the component under test is the data/context wiring.
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
    qualified_name: `app.core:${id}`,
    file_path: "app/core.py",
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
    evidence: [{ file_path: "app/core.py", line: 12, column: 4, expression: "load_data()" }],
    ...overrides,
  };
}

function graphResponse(
  nodes: GraphNode[],
  edges: GraphEdge[],
  extra: Partial<GraphResponse> = {}
): GraphResponse {
  return {
    analysis_id: "a1",
    view: "function",
    nodes,
    edges,
    truncated: false,
    total_nodes: nodes.length,
    total_edges: edges.length,
    ...extra,
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

function urlsCalled(): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url));
}

function lastUrl(): URL {
  const calls = fetchMock.mock.calls;
  return new URL(String(calls[calls.length - 1][0]));
}

/** Serve the graph for any view unless a test overrides the handler. */
function defaultGraphHandler(graph: GraphResponse) {
  return async (url: string | URL) => {
    const parsed = new URL(String(url));
    if (parsed.pathname.endsWith("/graph")) return json(graph);
    throw new Error(`unexpected request: ${parsed.pathname}`);
  };
}

describe("graph workspace", () => {
  it("loads the bounded graph and renders canvas and legend", async () => {
    const nodes = [node("n1"), node("n2"), node("n3")];
    const edges = [edge("e1", "n1", "n2")];
    fetchMock.mockImplementation(defaultGraphHandler(graphResponse(nodes, edges)));

    render(
      <GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />
    );

    expect(await screen.findByText(/3 visible nodes/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /interactive dependency graph canvas/i })).toBeInTheDocument();
    // Legend is present and explains kinds in text (never color-only).
    expect(screen.getByText("Legend")).toBeInTheDocument();
    expect(screen.getByText(/CONTAINS — structural containment/i)).toBeInTheDocument();

    const url = lastUrl();
    expect(url.pathname).toBe("/api/v1/analyses/a1/graph");
    expect(url.searchParams.get("view")).toBe("function");
    expect(url.searchParams.get("limit")).toBe("500");
    expect(screen.getByText(/Dependency graph — Service A/i)).toBeInTheDocument();
  });

  it("refetches with view/limit/kind filters when the controls change", async () => {
    fetchMock.mockImplementation(defaultGraphHandler(graphResponse([node("n1")], [])));

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    expect(await screen.findByText(/1 visible node/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /file \/ module/i }));

    await waitFor(() => {
      const graphCalls = urlsCalled().filter((url) => url.includes("/graph"));
      expect(graphCalls.length).toBeGreaterThan(1);
    });
    const lastGraphUrl = new URL(
      urlsCalled().filter((url) => url.includes("/graph")).slice(-1)[0]
    );
    expect(lastGraphUrl.searchParams.get("view")).toBe("module");

    // Node-kind filters serialize as repeated params.
    await user.click(screen.getByRole("checkbox", { name: /^module$/i }));
    await waitFor(() => {
      const last = new URL(
        urlsCalled().filter((url) => url.includes("/graph")).slice(-1)[0]
      );
      expect(last.searchParams.getAll("node_kinds")).toContain("module");
    });
  });

  it("shows the empty state when the filtered graph has no nodes", async () => {
    fetchMock.mockImplementation(defaultGraphHandler(graphResponse([], [])));

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    expect(await screen.findByText("No nodes in this graph view")).toBeInTheDocument();
    expect(
      screen.getByText(/try a different view level, clear the kind filters/i)
    ).toBeInTheDocument();
  });

  it("maps ANALYSIS_NOT_READY to an actionable error with retry", async () => {
    fetchMock.mockResolvedValue(
      json(
        {
          error: {
            code: "ANALYSIS_NOT_READY",
            message: "The analysis has not completed yet.",
            request_id: "r7",
          },
        },
        409
      )
    );

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    expect(
      await screen.findByText(/graph is not available yet — the analysis is still in progress/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows a partial-graph alert when the server truncated the result", async () => {
    fetchMock.mockImplementation(
      defaultGraphHandler(graphResponse([node("n1")], [], { truncated: true, total_nodes: 900 }))
    );

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    expect(await screen.findByText("Partial graph")).toBeInTheDocument();
    expect(screen.getByText(/showing 1 of 900 nodes/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/unresolved or ambiguous references/i)
    ).not.toBeInTheDocument();
  });

  it("surfaces unresolved-reference counts as diagnostics, not invented edges", async () => {
    fetchMock.mockImplementation(
      defaultGraphHandler(
        graphResponse([node("n1")], [], { unresolved_count: 4 })
      )
    );

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    expect(await screen.findByText(/4 unresolved or ambiguous references/i)).toBeInTheDocument();
  });

  it("searches the symbol catalog and loads the picked node's detail and neighbors", async () => {
    const n1 = node("n1", { name: "load_data", qualified_name: "app.core:load_data" });
    const caller = node("n7", {
      kind: "method",
      name: "handler",
      qualified_name: "app.api:Views.handler",
      file_path: "app/api.py",
    });
    const detail: GraphNode = {
      ...n1,
      kind: "function",
      metrics: { in_degree: 3, out_degree: 2, upstream_reachable: 7, downstream_reachable: 5 },
    };

    fetchMock.mockImplementation(async (url: string | URL) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/graph")) {
        return json(graphResponse([n1, node("n2")], []));
      }
      if (parsed.pathname === "/api/v1/analyses/a1/symbols") {
        expect(parsed.searchParams.get("q")).toBe("load");
        return json({
          items: [
            {
              id: "n1",
              kind: "function",
              name: "load_data",
              qualified_name: "app.core:load_data",
              file_path: "app/core.py",
            },
          ],
          pagination: { page: 1, per_page: 10, total: 1, total_pages: 1 },
        });
      }
      if (parsed.pathname === "/api/v1/analyses/a1/nodes/n1") {
        return json(detail);
      }
      if (parsed.pathname === "/api/v1/analyses/a1/nodes/n1/neighbors") {
        return json(
          graphResponse([caller], [edge("e-in", "n7", "n1", { kind: "CALLS", confidence: "medium" })]),
          // responses default has been graphResponse(); keep explicit shape
        );
      }
      throw new Error(`unexpected request: ${parsed.pathname}`);
    });

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);
    expect(await screen.findByText(/2 visible nodes/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/search graph nodes by name/i), "load");

    // Debounced search fires only for the symbol catalog.
    await waitFor(() => {
      const symbolCalls = urlsCalled().filter((url) => url.includes("/symbols"));
      expect(symbolCalls.length).toBeGreaterThan(0);
    });

    const resultButton = await screen.findByRole("button", { name: /app\.core:load_data/ });
    await user.click(resultButton);

    // Node detail + 1-hop neighbors are fetched through the graph endpoints.
    await waitFor(() => {
      expect(urlsCalled().some((url) => url.includes("/nodes/n1"))).toBe(true);
      expect(urlsCalled().some((url) => url.includes("/nodes/n1/neighbors"))).toBe(true);
    });
    const neighborsUrl = new URL(
      urlsCalled().filter((url) => url.includes("/nodes/n1/neighbors")).slice(-1)[0]
    );
    expect(neighborsUrl.searchParams.get("depth")).toBe("1");
    expect(neighborsUrl.searchParams.get("direction")).toBe("both");

    // Details panel shows backend metrics and the caller with its evidence.
    expect(await screen.findByText("app.core:load_data")).toBeInTheDocument();
    expect(screen.getByText("3 / 2")).toBeInTheDocument(); // in/out degree
    expect(
      screen.getByText(
        (_, element) => element?.tagName === "DD" && element.textContent === "7 / 5"
      )
    ).toBeInTheDocument(); // reachable upstream / downstream
    expect(screen.getByText("Direct callers (upstream)")).toBeInTheDocument();
    expect(screen.getByText("app.api:Views.handler")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /evidence: app\/core\.py:12/i })).toBeInTheDocument();
  });

  it("expands the selected node's neighborhood with depth and direction", async () => {
    fetchMock.mockImplementation(async (url: string | URL) => {
      const parsed = new URL(String(url));
      if (parsed.pathname.endsWith("/graph")) {
        return json(graphResponse([node("n1"), node("n2")], [edge("e1", "n1", "n2")]));
      }
      if (parsed.pathname === "/api/v1/analyses/a1/nodes/n1") {
        return json(node("n1"));
      }
      if (parsed.pathname === "/api/v1/analyses/a1/nodes/n1/neighbors") {
        const depth = parsed.searchParams.get("depth");
        const direction = parsed.searchParams.get("direction");
        if (depth === "2" && direction === "upstream") {
          return json(
            graphResponse(
              [node("n9")],
              [edge("e-up", "n9", "n1")]
            )
          );
        }
        return json(graphResponse([], [edge("e1", "n1", "n2")]));
      }
      throw new Error(`unexpected request: ${parsed.pathname}`);
    });

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    // Use the accessible table alternative to select the row without canvas.
    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /table \(accessible list view\)/i }));

    const nodesTable = await screen.findByRole("table", { name: /graph nodes/i });
    await user.click(within(nodesTable).getByText("app.core:n1"));

    // The details panel opens with the node's qualified name.
    await screen.findByText(/Selected node/i);

    await user.selectOptions(screen.getByLabelText(/depth/i), "2");
    await user.selectOptions(screen.getByLabelText(/direction/i), "upstream");
    await user.click(screen.getByRole("button", { name: /expand neighbors/i }));

    await waitFor(() => {
      const expandCall = urlsCalled()
        .filter((url) => url.includes("/nodes/n1/neighbors"))
        .map((url) => new URL(url))
        .find((url) => url.searchParams.get("depth") === "2");
      expect(expandCall?.searchParams.get("direction")).toBe("upstream");
    });

    // The merged neighbor is now visible (3 nodes: 2 base + n9).
    await screen.findByText(/3 visible nodes · 2 visible edges/i);
  });

  it("shows edge details with evidence when an edge is selected in table view", async () => {
    fetchMock.mockImplementation(
      defaultGraphHandler(
        graphResponse(
          [node("n1", { name: "handler", qualified_name: "app.api:handler" }), 
           node("n2", { name: "load_data", qualified_name: "app.core:load_data" })],
          [
            edge("e1", "n1", "n2", {
              kind: "CALLS",
              confidence: "low",
              resolver: "ast-import",
              evidence: [{ file_path: "app/api.py", line: 33, column: 8, expression: "load_data(x)" }],
            }),
          ]
        )
      )
    );

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /table \(accessible list view\)/i }));

    const edgesTable = await screen.findByRole("table", { name: /graph edges/i });
    await user.click(within(edgesTable).getByText("CALLS"));

    expect(screen.getByText(/edge details/i)).toBeInTheDocument();
    expect(screen.getByText("low confidence")).toBeInTheDocument();
    expect(screen.getByText("ast-import")).toBeInTheDocument();
    expect(screen.getByText("app/api.py:33:8")).toBeInTheDocument();
    expect(screen.getByText("load_data(x)")).toBeInTheDocument();
    expect(
      screen.queryByText(/structural containment, not a dependency/i)
    ).not.toBeInTheDocument();
  });

  it("renders the CONTAINS structural marker in the relationships table", async () => {
    fetchMock.mockImplementation(
      defaultGraphHandler(
        graphResponse([node("n1"), node("n2")], [
          edge("ec", "n1", "n2", { kind: "CONTAINS" }),
        ])
      )
    );

    render(<GraphWorkspace projectId="p1" analysisId="a1" projectName="Service A" />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /table \(accessible list view\)/i }));

    const edgesTable = await screen.findByRole("table", { name: /graph edges/i });
    expect(within(edgesTable).getByText(/structural/)).toBeInTheDocument();
  });
});
