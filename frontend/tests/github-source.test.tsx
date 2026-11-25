import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { GithubSourceForm } from "@/features/github/components/github-source-form";
import type {
  GitHubInstallationList,
  PaginatedRepositories,
  Project,
} from "@/types/api";

/**
 * Phase 3B GitHub source tests: no installation, installation selection,
 * repository list with pagination, no repositories, repository selection
 * prefilling the ref, import success, and permission-failure handling.
 * All responses are mocked (tests only).
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

const INSTALLATIONS: GitHubInstallationList = {
  items: [
    { id: 101, account_login: "octocat", account_type: "user" },
    { id: 202, account_login: "acme-org", account_type: "organization" },
  ],
};

function reposPage(page: number): PaginatedRepositories {
  return {
    items:
      page === 1
        ? [
            {
              id: 9001,
              full_name: "octocat/edge-service",
              visibility: "private",
              default_branch: "main",
              description: "The edge thing",
            },
            {
              id: 9002,
              full_name: "octocat/scripts",
              visibility: "public",
              default_branch: "master",
              description: null,
            },
          ]
        : [
            {
              id: 9003,
              full_name: "octocat/legacy-app",
              visibility: "public",
              default_branch: "develop",
            },
          ],
    pagination: { page, per_page: 2, total: 3, total_pages: 2 },
  };
}

const IMPORTED: Project = {
  id: "p7",
  name: "edge-service",
  source_provider: "github",
  created_at: "2025-06-04T10:00:00Z",
  updated_at: "2025-06-04T10:00:00Z",
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderForm() {
  const onCreated = vi.fn();
  render(<GithubSourceForm onCreated={onCreated} />);
  // Settle on one of the terminal states for the installation list.
  await waitFor(() => {
    const settled =
      screen.queryByRole("combobox", { name: /Installation/ }) ??
      screen.queryByText(/isn't installed anywhere yet/i) ??
      screen.queryByText(/Could not list installations/i);
    expect(settled).not.toBeNull();
  });
  return { onCreated };
}

describe("GitHub source flow", () => {
  it("prompts to install the FlowLens App when there are no installations", async () => {
    fetchMock.mockResolvedValue(json({ items: [] }));

    await renderForm();

    expect(await screen.findByText(/isn't installed anywhere yet/i)).toBeInTheDocument();
    const install = screen.getByRole("link", { name: /^Install$/ });
    expect(install).toHaveAttribute(
      "href",
      "http://localhost:8000/api/v1/github/install/start"
    );
  });

  it("lists installations and repositories for the selected installation", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(1));
      }
      return json(INSTALLATIONS);
    });

    await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "101");

    expect(await screen.findByText("octocat/edge-service")).toBeInTheDocument();
    expect(screen.getByText("octocat/scripts")).toBeInTheDocument();
    expect(screen.getByText(/Default branch: main/)).toBeInTheDocument();
    // Visibility labels appear, plus the "informational" disclaimer.
    expect(screen.getAllByText("private")).toHaveLength(1);
    expect(screen.getByText(/visibility label is informational/i)).toBeInTheDocument();
  });

  it("paginates repositories and shows an empty state when none are accessible", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(path.includes("page=2") ? 2 : 1));
      }
      return json(INSTALLATIONS);
    });

    const { onCreated } = await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "101");
    expect(await screen.findByText("octocat/edge-service")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^Next/ }));
    expect(await screen.findByText("octocat/legacy-app")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2 · 3 repositories")).toBeInTheDocument();

    // Select on page 2, then import.
    await userEvent.click(screen.getByRole("radio", { name: /Select repository octocat\/legacy-app/ }));
    expect(screen.getByLabelText(/Branch, tag, or commit SHA/)).toHaveValue("develop");

    fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/projects/from-github")) {
        expect(JSON.parse(String(init?.body))).toEqual({
          repository_id: 9003,
          installation_id: 101,
          ref: "develop",
        });
        return json(IMPORTED, 201);
      }
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(2));
      }
      return json(INSTALLATIONS);
    });

    await userEvent.click(screen.getByRole("button", { name: /Import octocat\/legacy-app/ }));
    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(IMPORTED));
  });

  it("shows a clear empty state when the installation has no repositories", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/github/installations/")) {
        return json({ items: [], pagination: { page: 1, per_page: 25, total: 0 } });
      }
      return json(INSTALLATIONS);
    });

    await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "202");
    expect(await screen.findByText("No accessible repositories")).toBeInTheDocument();
    expect(
      screen.getByText(/No repositories were granted.*FlowLens App installation for acme-org/i)
    ).toBeInTheDocument();
  });

  it("imports the selected repository at the chosen ref and redirects to its workspace", async () => {
    fetchMock.mockImplementation(async (url: URL | string, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith("/projects/from-github")) {
        expect(JSON.parse(String(init?.body))).toEqual({
          repository_id: 9001,
          installation_id: 101,
          ref: "feature/x",
        });
        return json(IMPORTED, 201);
      }
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(1));
      }
      return json(INSTALLATIONS);
    });

    const { onCreated } = await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "101");
    expect(await screen.findByText("octocat/edge-service")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: /Select repository octocat\/edge-service/ }));
    await userEvent.clear(screen.getByLabelText(/Branch, tag, or commit SHA/));
    await userEvent.type(screen.getByLabelText(/Branch, tag, or commit SHA/), "feature/x");

    await userEvent.click(screen.getByRole("button", { name: /Import octocat\/edge-service/ }));
    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(IMPORTED));
  });

  it("shows the backend's permission-denied message on REPOSITORY_ACCESS_DENIED", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.endsWith("/projects/from-github")) {
        return json(
          {
            error: {
              code: "REPOSITORY_ACCESS_DENIED",
              message: "FlowLens does not have access to this repository.",
              request_id: "r4",
            },
          },
          403
        );
      }
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(1));
      }
      return json(INSTALLATIONS);
    });

    await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "101");
    await screen.findByText("octocat/edge-service");
    await userEvent.click(screen.getByRole("radio", { name: /Select repository octocat\/edge-service/ }));

    await userEvent.click(screen.getByRole("button", { name: /Import octocat\/edge-service/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /FlowLens does not have access to this repository/
    );
    expect(screen.getByRole("button", { name: /Import/ })).toBeEnabled();
  });

  it("requires a ref before importing", async () => {
    fetchMock.mockImplementation(async (url: URL | string) => {
      const path = String(url);
      if (path.includes("/github/installations/101/repositories")) {
        return json(reposPage(1));
      }
      return json(INSTALLATIONS);
    });

    await renderForm();

    await userEvent.selectOptions(screen.getByLabelText(/Installation/), "101");
    await screen.findByText("octocat/edge-service");
    await userEvent.click(screen.getByRole("radio", { name: /Select repository octocat\/edge-service/ }));

    await userEvent.clear(screen.getByLabelText(/Branch, tag, or commit SHA/));
    await userEvent.click(screen.getByRole("button", { name: /Import octocat\/edge-service/ }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      /Enter a branch, tag, or commit SHA/
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/projects/from-github",
      expect.anything()
    );
  });

  it("shows installation list failures with a retry", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json(
          {
            error: {
              code: "INTERNAL_ERROR",
              message: "GitHub is not responding.",
              request_id: "r5",
            },
          },
          500
        )
      )
      .mockResolvedValue(json(INSTALLATIONS));

    await renderForm();

    expect(await screen.findByText(/Could not list installations/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByLabelText(/Installation/)).toBeInTheDocument();
  });
});
