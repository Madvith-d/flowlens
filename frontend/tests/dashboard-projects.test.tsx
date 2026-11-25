import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { ProjectsDashboard } from "@/features/projects/components/projects-dashboard";
import type { PaginatedProjects, Project } from "@/types/api";

/**
 * Phase 3B dashboard tests: loading, list rendering (provider badges,
 * repository/ref metadata, latest snapshot, analysis status), empty
 * dashboard, backend error + retry, and pagination.
 * All API responses are mocked (tests only — the app calls the real API).
 */

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
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

function project(partial: Partial<Project>): Project {
  return {
    id: "p1",
    name: "Demo",
    source_provider: "github",
    created_at: "2025-06-01T10:00:00Z",
    updated_at: "2025-06-01T10:00:00Z",
    ...partial,
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

describe("projects dashboard", () => {
  it("shows skeletons while loading", () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ProjectsDashboard />);
    expect(screen.getByLabelText("Loading projects")).toBeInTheDocument();
  });

  it("renders projects with provider, source metadata, snapshot, and analysis status", async () => {
    const body: PaginatedProjects = {
      items: [
        project({
          id: "p1",
          name: "Service A",
          source_provider: "github",
          github_connection: {
            installation_id: 1,
            repository_id: 10,
            full_name: "acme/service-a",
            ref: "main",
            connected_at: "2025-06-01T09:00:00Z",
          },
          latest_snapshot: {
            id: "s1",
            project_id: "p1",
            provider: "github",
            created_at: "2025-06-02T10:00:00Z",
            content_hash: "hash-abcdef123456",
            github_provenance: {
              repository_id: 10,
              full_name: "acme/service-a",
              ref: "main",
              commit_sha: "8f14e45fceea167a5a36dedd1d9d07cc7d0e...",
              imported_at: "2025-06-02T10:00:00Z",
            },
          },
          latest_analysis: {
            id: "a1",
            snapshot_id: "s1",
            state: "completed_with_warnings",
            created_at: "2025-06-02T11:00:00Z",
            graph_schema_version: "v1",
          },
        }),
        project({
          id: "p2",
          name: "Notebook B",
          source_provider: "upload",
          github_connection: null,
          latest_snapshot: {
            id: "s2",
            project_id: "p2",
            provider: "upload",
            created_at: "2025-06-03T10:00:00Z",
            content_hash: "uploadhash123",
            file_count: 42,
          },
          latest_analysis: null,
        }),
      ],
      pagination: { page: 1, per_page: 25, total: 2 },
    };
    fetchMock.mockResolvedValue(json(body));

    render(<ProjectsDashboard />);

    expect(await screen.findByText("Service A")).toBeInTheDocument();
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("ZIP upload")).toBeInTheDocument();
    expect(screen.getByText("acme/service-a")).toBeInTheDocument();
    expect(screen.getByText("main", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Analyzed with warnings")).toBeInTheDocument();
    expect(screen.getByText("No analysis yet")).toBeInTheDocument();
    expect(screen.getByText(/42 files/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Service A/ })
    ).toHaveAttribute("href", "/projects/p1");
  });

  it("shows the empty state when the user has no projects", async () => {
    fetchMock.mockResolvedValue(
      json({ items: [], pagination: { page: 1, per_page: 25, total: 0 } })
    );

    render(<ProjectsDashboard />);

    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New project/ })).toHaveAttribute(
      "href",
      "/projects/new"
    );
  });

  it("shows an error state with retry, and recovers", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json(
          {
            error: {
              code: "INTERNAL_ERROR",
              message: "The backend had a problem.",
              request_id: "r1",
            },
          },
          500
        )
      )
      .mockResolvedValueOnce(json({ items: [], pagination: { page: 1, per_page: 25, total: 0 } }));

    render(<ProjectsDashboard />);

    expect(await screen.findByText("Could not load your projects")).toBeInTheDocument();
    expect(screen.getByText("The backend had a problem.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("paginates projects through the backend", async () => {
    const page1: PaginatedProjects = {
      items: [project({ id: "p1", name: "First Project" })],
      pagination: { page: 1, per_page: 1, total: 2, total_pages: 2 },
    };
    const page2: PaginatedProjects = {
      items: [project({ id: "p2", name: "Second Project" })],
      pagination: { page: 2, per_page: 1, total: 2, total_pages: 2 },
    };

    fetchMock.mockImplementation(async (url: URL | string) =>
      json(String(url).includes("page=2") ? page2 : page1)
    );

    render(<ProjectsDashboard />);

    expect(await screen.findByText("First Project")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(await screen.findByText("Second Project")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2 · 2 projects")).toBeInTheDocument();
  });
});
