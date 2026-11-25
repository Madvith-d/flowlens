import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "sonner";

import ProjectDetailPage from "@/app/(protected)/projects/[project_id]/page";
import type { Project, Snapshot } from "@/types/api";

/**
 * Phase 3B project detail tests: provenance, snapshot history, the
 * created-notice, the refresh action, disconnect with confirmation, and
 * not-found handling. All API responses are mocked (tests only).
 * The sonner <Toaster /> is mounted so toast feedback is observable.
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

const GIT_SNAPSHOT: Snapshot = {
  id: "s1",
  project_id: "p1",
  provider: "github",
  created_at: "2025-06-02T10:00:00Z",
  content_hash: "cafebabedeadbeef1234",
  file_count: 30,
  github_provenance: {
    repository_id: 10,
    full_name: "acme/service-a",
    ref: "main",
    commit_sha: "8f14e45fceea167a",
    imported_at: "2025-06-02T10:00:00Z",
  },
};

function githubProject(): Project {
  return {
    id: "p1",
    name: "Service A",
    source_provider: "github",
    created_at: "2025-06-01T10:00:00Z",
    updated_at: "2025-06-02T10:00:00Z",
    github_connection: {
      installation_id: 1,
      repository_id: 10,
      full_name: "acme/service-a",
      ref: "main",
      connected_at: "2025-06-01T10:00:00Z",
    },
    latest_snapshot: GIT_SNAPSHOT,
    latest_analysis: {
      id: "a1",
      snapshot_id: "s1",
      state: "queued",
      created_at: "2025-06-02T11:00:00Z",
      graph_schema_version: "v1",
    },
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  window.history.replaceState({}, "", "/projects/p1");
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <>
      <ProjectDetailPage />
      <Toaster />
    </>
  );
}

describe("project detail page", () => {
  it("shows source provenance, GitHub connection, and snapshot history", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/snapshots")) {
        return json({ items: [GIT_SNAPSHOT], pagination: { page: 1, per_page: 50, total: 1 } });
      }
      return json(githubProject());
    });

    renderPage();

    expect(await screen.findByText("Service A")).toBeInTheDocument();
    // Workspace entry point (Phase 4B) targets the analysis workspace.
    expect(screen.getByRole("link", { name: /open workspace/i })).toHaveAttribute(
      "href",
      "/projects/p1/workspace"
    );
    expect(screen.getByText("Source origin")).toBeInTheDocument();
    expect(screen.getByText("Resolved commit")).toBeInTheDocument();
    // Repository + ref appear in both the origin card and the connection card.
    expect(screen.getAllByText("acme/service-a").length).toBeGreaterThan(0);
    expect(screen.getByTitle("8f14e45fceea167a")).toBeInTheDocument();
    // Snapshot history: ref + short commit + file count, plus content hash provenance.
    expect(screen.getAllByText(/main @ 8f14e45f…/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/30 files/).length).toBeGreaterThan(0);
  });

  it("shows the project-created notice for a fresh creation", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/snapshots")) {
        return json({ items: [], pagination: { page: 1, per_page: 50, total: 0 } });
      }
      return json(githubProject());
    });

    window.history.replaceState({}, "", "/projects/p1?created=1");
    renderPage();

    expect(await screen.findByText("Project created")).toBeInTheDocument();
  });

  it("refreshes into a new snapshot and reloads history", async () => {
    let refreshes = 0;
    fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === "POST" && path.endsWith("/refresh")) {
        refreshes += 1;
        return json(
          { ...GIT_SNAPSHOT, id: "s2", created_at: "2025-06-05T10:00:00Z" },
          201
        );
      }
      if (path.includes("/snapshots")) {
        const items =
          refreshes > 0
            ? [{ ...GIT_SNAPSHOT, id: "s2", created_at: "2025-06-05T10:00:00Z" }, GIT_SNAPSHOT]
            : [GIT_SNAPSHOT];
        return json({
          items,
          pagination: { page: 1, per_page: 50, total: refreshes > 0 ? 2 : 1 },
        });
      }
      return json(githubProject());
    });

    renderPage();

    await screen.findByText("Service A");
    await userEvent.click(screen.getByRole("button", { name: /Refresh snapshot/ }));

    expect(await screen.findByText("Snapshot refreshed")).toBeInTheDocument();
    // The new snapshot (June 5) is now in the history list.
    expect(await screen.findByText(/Jun 5, 2025/)).toBeInTheDocument();
  });

  it("disconnects the repository only after confirmation, and states snapshots are kept", async () => {
    let disconnected = false;
    fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === "DELETE") {
        disconnected = true;
        return json(undefined, 204);
      }
      if (path.includes("/snapshots")) {
        return json({ items: [GIT_SNAPSHOT], pagination: { page: 1, per_page: 50, total: 1 } });
      }
      const project = githubProject();
      return json(disconnected ? { ...project, github_connection: null } : project);
    });

    renderPage();

    await screen.findByText("Service A");
    await userEvent.click(screen.getByRole("button", { name: /Disconnect repository/ }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(
      /all existing snapshots, analyses, and reports for this project are kept/i
    );

    await userEvent.click(
      within(dialog).getByRole("button", { name: /^Disconnect repository$/ })
    );

    expect(
      await screen.findByText(/This project's GitHub repository link was removed/i)
    ).toBeInTheDocument();
    expect(screen.getAllByText("Repository disconnected").length).toBeGreaterThan(0);
    // Snapshot history remains visible after disconnecting.
    expect(screen.getByText("Snapshots")).toBeInTheDocument();
    expect(screen.getAllByText(/main @ 8f14e45f…/).length).toBeGreaterThan(0);
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

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(
      screen.getByText(/check the dashboard for your projects/i)
    ).toBeInTheDocument();
  });
});
