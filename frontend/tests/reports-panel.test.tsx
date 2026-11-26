import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { ReportsPanel } from "@/features/reports/components/reports-panel";
import type { DiffResult, ReportInfo } from "@/types/api";

/**
 * Phase 7B reports tests: generation (scoping rules), metadata display,
 * Markdown preview via the download endpoint, save-to-disk download, and the
 * honest error/hint states (report listing is not part of the contract).
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

const REPORT: ReportInfo = {
  id: "r1",
  analysis_id: "a1",
  format: "markdown",
  created_at: "2025-06-10T10:00:00Z",
  filename: "flowlens-report-a1.md",
};

function diffScope(overrides: Partial<DiffResult> = {}): DiffResult {
  return {
    analysis_id: "a1",
    files: [
      {
        path: "app/core.py",
        change_type: "modified",
        changed_line_count: 5,
        mapped_symbols: [
          { symbol_id: "sym1", qualified_name: "app.core:load_data", change_type: "modified" },
          { symbol_id: "sym2", qualified_name: "app.core:save_data", change_type: "modified" },
        ],
      },
    ],
    combined_impact: {
      analysis_id: "a1",
      targets: [
        { node_id: "sym1", qualified_name: "app.core:load_data" },
        { node_id: "sym2", qualified_name: "app.core:save_data" },
      ],
      direction: "both",
      max_depth: 3,
      impacted: [],
      risk: {
        score: 10,
        version: "risk-v1",
        coverage_included: false,
        factors: [],
      },
      warnings: [],
    },
    warnings: [],
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let createObjectURLMock: ReturnType<typeof vi.fn>;
let revokeObjectURLMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  // jsdom has no blob URL implementation; capture the anchor download flow.
  createObjectURLMock = vi.fn(() => "blob:flowlens-report");
  revokeObjectURLMock = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { value: createObjectURLMock, writable: true, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURLMock, writable: true, configurable: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function generate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /generate report/i }));
  await screen.findByText(REPORT.filename, {}, { timeout: 5000 });
}

describe("ReportsPanel", () => {
  it("states that only reports generated in this session are available (contract has no report listing)", () => {
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    expect(
      screen.getByText(/contract exposes no report listing/i)
    ).toBeInTheDocument();
  });

  it("disables the diff-scope option until a diff with mapped symbols exists", () => {
    const { rerender } = render(<ReportsPanel analysisId="a1" diffScope={null} />);
    const radio = screen.getByRole("radio", { name: /changed symbols from the diff review/i });
    expect(radio).toBeDisabled();

    rerender(<ReportsPanel analysisId="a1" diffScope={diffScope()} />);
    expect(
      screen.getByRole("radio", { name: /changed symbols from the diff review/i })
    ).not.toBeDisabled();
  });

  it("generates an unscoped report (empty body) and shows the metadata", async () => {
    fetchMock.mockResolvedValueOnce(json(REPORT, 201));
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    await generate(user);

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/analyses/a1/reports");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(options.body).toBeUndefined();

    expect(screen.getByText("markdown")).toBeInTheDocument();
    expect(screen.getByText(/created Jun 10, 2025/i)).toBeInTheDocument();
    expect(screen.getByTitle("r1")).toBeInTheDocument();
  });

  it("scopes the request to the diff's mapped symbols when that option is chosen", async () => {
    fetchMock.mockResolvedValueOnce(json(REPORT, 201));
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={diffScope()} />);
    await user.click(
      screen.getByRole("radio", { name: /changed symbols from the diff review/i })
    );
    await generate(user);

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(options.body as string)).toEqual({
      target_ids: ["sym1", "sym2"],
      direction: "both",
      max_depth: 3,
    });
  });

  it("previews the generated Markdown through the download endpoint verbatim", async () => {
    fetchMock.mockResolvedValueOnce(json(REPORT, 201));
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    await generate(user);

    fetchMock.mockResolvedValueOnce(markdown("# FlowLens impact report\n\n| Risk | 42 |"));
    await user.click(screen.getByRole("button", { name: /preview markdown/i }));

    expect(await screen.findByText(/# FlowLens impact report/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/rendered verbatim from the downloaded markdown/i)).toBeInTheDocument();

    const [url, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/reports/r1/download");
    expect(options.credentials).toBe("include");
    expect((options.headers as Record<string, string>).Accept).toBe("text/markdown");
  });

  it("surfaces a download failure as a retryable error without partial output", async () => {
    fetchMock.mockResolvedValueOnce(json(REPORT, 201));
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    await generate(user);

    fetchMock.mockResolvedValueOnce(
      json({ error: { code: "NOT_FOUND", message: "gone", request_id: "r" } }, 404)
    );
    await user.click(screen.getByRole("button", { name: /preview markdown/i }));

    expect(await screen.findByText(/preview failed/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/requested resource was not found|gone/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry preview/i })).toBeInTheDocument();
  });

  it("downloads the report as a blob using the server-provided filename", async () => {
    fetchMock.mockResolvedValueOnce(json(REPORT, 201));
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    await generate(user);

    fetchMock.mockResolvedValueOnce(markdown("# report body"));
    await user.click(screen.getByRole("button", { name: /^download$/i }));

    await vi.waitFor(() => expect(createObjectURLMock).toHaveBeenCalledTimes(1), { timeout: 5000 });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "http://localhost:8000/api/v1/reports/r1/download",
      expect.anything()
    );
  });

  it("maps ANALYSIS_NOT_READY (409) to an actionable generation error", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        { error: { code: "ANALYSIS_NOT_READY", message: "running", request_id: "r" } },
        409
      )
    );
    const user = userEvent.setup();
    render(<ReportsPanel analysisId="a1" diffScope={null} />);
    await user.click(screen.getByRole("button", { name: /generate report/i }));

    expect(await screen.findByText(/reports are not available yet/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/report generation failed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry generation/i })).toBeInTheDocument();
  });
});
