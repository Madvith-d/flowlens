import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import { SessionProvider } from "@/features/auth/session-provider";

/**
 * Login page UX states per Phase 2B:
 * loading, unauthenticated (Continue with GitHub), session-expired,
 * GitHub callback failure, backend-unavailable, and logout navigation target.
 */

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

const DEFAULT_BASE = "http://localhost:8000";

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

function unauthorized(): Response {
  return json(
    { error: { code: "AUTH_REQUIRED", message: "no session", request_id: "r" } },
    401
  );
}

let fetchMock: ReturnType<typeof vi.fn>;

/**
 * jsdom cannot navigate or react to history.replaceState the way the
 * browser does; stub `location` with the given search string and capture
 * `assign`/`reload` calls.
 */
function stubLocation(search = "") {
  vi.stubGlobal("location", { assign: vi.fn(), href: "", search, reload: vi.fn() });
}

beforeEach(() => {
  replace.mockClear();
  window.history.replaceState({}, "", "/login");
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  stubLocation();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderLogin() {
  return render(
    <SessionProvider>
      <LoginPage />
    </SessionProvider>
  );
}

describe("LoginPage", () => {
  it("shows a session-check loading state before sign-in", () => {
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    renderLogin();

    expect(screen.getByText("Checking your session…")).toBeInTheDocument();
  });

  it("redirects an already-authenticated user to the dashboard", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ authenticated: true, user: { id: "u1", github_login: "octo" } })
    );
    renderLogin();

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("renders Continue with GitHub for unauthenticated users and navigates to the backend start endpoint on click", async () => {
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();

    const button = await screen.findByRole("button", {
      name: /Continue with GitHub/i,
    });
    await userEvent.click(button);

    expect(window.location.assign).toHaveBeenCalledWith(
      `${DEFAULT_BASE}/api/v1/auth/github/start`
    );
  });

  it("explains that a fetch/XHR call is not used for the OAuth redirect", async () => {
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();

    await screen.findByRole("button", { name: /Continue with GitHub/i });
    // Only /auth/me is fetched; the login redirect must be a navigation.
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls.some((url) => url.includes("/auth/github/start"))).toBe(false);
  });

  it("shows the session-expired message when redirected with ?reason=expired", async () => {
    stubLocation("?reason=expired");
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();

    expect(
      await screen.findByRole("heading", { name: "Session expired" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/sign in again to continue/i)
    ).toBeInTheDocument();
  });

  it("shows the signed-out message after a deliberate logout", async () => {
    stubLocation("?reason=signed-out");
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();

    expect(
      await screen.findByRole("heading", { name: "Signed out" })
    ).toBeInTheDocument();
  });

  it("shows an actionable failure alert when the GitHub callback failed", async () => {
    stubLocation("?reason=oauth");
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();

    expect(
      await screen.findByRole("heading", { name: "GitHub sign-in failed" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/authorization was denied or the session state was invalid/i)
    ).toBeInTheDocument();
  });

  it("shows a backend-unavailable state and offers a page reload when /auth/me cannot be reached", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderLogin();

    expect(
      await screen.findByRole("heading", { name: "Cannot reach the FlowLens backend" })
    ).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "Reload" }));
    expect(window.location.reload).toHaveBeenCalled();
  });

  it("does not render provider tokens or secrets anywhere", async () => {
    fetchMock.mockResolvedValueOnce(unauthorized());
    renderLogin();
    await screen.findByRole("button", { name: /Continue with GitHub/i });

    expect(document.body.textContent).not.toMatch(/access_token|client_secret|private_key/i);
  });
});
