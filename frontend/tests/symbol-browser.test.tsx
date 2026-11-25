import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { SymbolBrowser } from "@/features/analysis/components/symbol-browser";
import type { PaginatedSymbols, Symbol } from "@/types/api";

/**
 * Phase 4B symbol browser tests: search/kind/pagination parameters of
 * `GET /analyses/{id}/symbols`, symbol detail, and the empty/not-ready
 * states. All API responses are mocked (tests only).
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

function symbol(overrides: Partial<Symbol> = {}): Symbol {
  return {
    id: "sym-1",
    kind: "class",
    name: "User",
    qualified_name: "app.models:User",
    file_path: "app/models.py",
    location: { start_line: 10, end_line: 42, start_column: 4, end_column: 50 },
    parent_id: null,
    ...overrides,
  };
}

function symbolPage(items: Symbol[], total = items.length, page = 1): PaginatedSymbols {
  return {
    items,
    pagination: { page, per_page: 25, total, total_pages: Math.max(1, Math.ceil(total / 25)) },
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

function lastCallUrlAndInit(): { url: string; init?: RequestInit } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [
    string,
    RequestInit | undefined,
  ];
  return { url: String(url), init };
}

describe("symbol browser", () => {
  it("loads page 1 without q/kind and renders the table", async () => {
    fetchMock.mockResolvedValue(
      json(symbolPage([symbol(), symbol({ id: "sym-2", kind: "function", name: "load", qualified_name: "app.api:load", file_path: "app/api.py", location: { start_line: 1, end_line: 5 } })]))
    );

    render(<SymbolBrowser analysisId="a1" />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    const { url } = lastCallUrlAndInit();
    expect(url).toContain("/api/v1/analyses/a1/symbols?");
    expect(url).toContain("page=1");
    expect(url).toContain("per_page=25");
    expect(url).not.toContain("q=");
    expect(url).not.toContain("kind=");

    expect(screen.getByText("app.api:load")).toBeInTheDocument();
    expect(screen.getByText(/app\/api\.py · lines 1–5/)).toBeInTheDocument();
  });

  it("sends q (debounced) and kind filters as query parameters", async () => {
    fetchMock.mockResolvedValue(json(symbolPage([])));

    render(<SymbolBrowser analysisId="a1" />);
    await screen.findByText("No symbols found");

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/search symbols/i), "user");

    await waitFor(() => {
      expect(lastCallUrlAndInit().url).toContain("q=user");
    });

    await user.selectOptions(screen.getByLabelText(/filter symbols by kind/i), "class");

    await waitFor(() => {
      expect(lastCallUrlAndInit().url).toContain("kind=class");
    });
  });

  it("paginates with the backend and disables next on the last page", async () => {
    // 26 symbols over 2 pages; start on page 1.
    fetchMock.mockImplementation(async (url: string | URL) => {
      const page = new URL(String(url)).searchParams.get("page") === "2" ? 2 : 1;
      const items =
        page === 2
          ? [symbol({ id: "sym-x" })]
          : Array.from({ length: 25 }, (_, i) =>
              symbol({ id: `sym-${i}`, name: `s${i}`, qualified_name: `m:s${i}` })
            );
      return json(symbolPage(items, 26, page));
    });

    render(<SymbolBrowser analysisId="a1" />);
    expect(await screen.findByText(/Page 1 of 2 · 26 symbols/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    await screen.findByText(/Page 2 of 2/);
    expect(lastCallUrlAndInit().url).toContain("page=2");
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /previous/i })).toBeEnabled();
  });

  it("shows a selected symbol's detail with source location", async () => {
    fetchMock.mockResolvedValue(
      json(
        symbolPage([
          symbol({
            id: "sym-m",
            kind: "method",
            name: "save",
            qualified_name: "app.models:User.save",
            file_path: "app/models.py",
            location: { start_line: 100, end_line: 120, start_column: 8, end_column: 60 },
            parent_id: "sym-user-class",
          }),
        ])
      )
    );

    render(<SymbolBrowser analysisId="a1" />);

    const qualifiedCell = await screen.findByText("app.models:User.save");
    const row = qualifiedCell.closest("tr") as HTMLElement;
    await userEvent.click(row);

    expect(screen.getByText(/Selected symbol/i)).toBeInTheDocument();
    expect(screen.getByText("100–120")).toBeInTheDocument();
    expect(screen.getByText("8–60")).toBeInTheDocument();
    expect(screen.getByText("Columns")).toBeInTheDocument();
    expect(screen.getByText("sym-user-class")).toBeInTheDocument();
    expect(screen.getByText("app/models.py")).toBeInTheDocument();

    // Deselect collapses the detail.
    await userEvent.click(row);
    expect(screen.queryByText(/Selected symbol/i)).not.toBeInTheDocument();
  });

  it("shows the analysis-not-ready error as an actionable message", async () => {
    fetchMock.mockResolvedValue(
      json(
        {
          error: {
            code: "ANALYSIS_NOT_READY",
            message: "The analysis has not completed yet.",
            request_id: "r9",
          },
        },
        409
      )
    );

    render(<SymbolBrowser analysisId="a1" />);

    expect(
      await screen.findByText(/symbols are not available yet/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("renders the empty state for a page with no symbols", async () => {
    fetchMock.mockResolvedValue(json(symbolPage([])));

    render(<SymbolBrowser analysisId="a1" />);

    expect(await screen.findByText("No symbols found")).toBeInTheDocument();
    expect(
      screen.getByText(/did not find any Python symbols/i)
    ).toBeInTheDocument();
  });
});
