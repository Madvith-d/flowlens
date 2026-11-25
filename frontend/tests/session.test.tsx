import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { SessionProvider, useSession } from "@/features/auth/session-provider";
import { RequireAuth } from "@/features/auth/require-auth";

/**
 * Session lifecycle tests: loading, authenticated, unauthenticated redirect,
 * backend-unavailable error state, refresh, and logout.
 */

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

function okSession(authenticated: boolean, login?: string) {
  return {
    ok: true,
    status: 200,
    clone() {
      return okSession(authenticated, login);
    },
    json: async () =>
      authenticated
        ? {
            authenticated: true,
            user: { id: "u1", github_login: login ?? "octocat" },
          }
        : { authenticated: false },
  } as unknown as Response;
}

function unauthorized() {
  return {
    ok: false,
    status: 401,
    clone() {
      return unauthorized();
    },
    json: async () => ({
      error: { code: "AUTH_REQUIRED", message: "no session", request_id: "r" },
    }),
  } as unknown as Response;
}

function Guarded() {
  return (
    <SessionProvider>
      <RequireAuth>
        <div>Protected content</div>
      </RequireAuth>
    </SessionProvider>
  );
}

/** Probe exposing session actions through a button, never during render. */
function ActionProbe({ action }: { action: "refresh" | "logout" }) {
  return (
    <SessionProvider>
      <ProbeInner action={action} />
    </SessionProvider>
  );
}

function ProbeInner({ action }: { action: "refresh" | "logout" }) {
  const { refresh, logout, user, status } = useSession();
  return (
    <div>
      {user ? <span>@{user.github_login}</span> : null}
      <span data-testid="status">{status}</span>
      <button onClick={() => void (action === "refresh" ? refresh() : logout())}>
        run {action}
      </button>
    </div>
  );
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  replace.mockClear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionProvider + RequireAuth", () => {
  it("renders a loading state while the session check is pending", () => {
    fetchMock.mockReturnValueOnce(new Promise(() => {})); // never resolves
    render(<Guarded />);

    expect(screen.getByLabelText("Checking your session")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("renders protected content once the session is authenticated", async () => {
    fetchMock.mockResolvedValueOnce(okSession(true));
    render(<Guarded />);

    await screen.findByText("Protected content");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/me"),
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("redirects unauthenticated users to the login page with the expired reason", async () => {
    fetchMock.mockResolvedValueOnce(unauthorized());
    render(<Guarded />);

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login?reason=expired");
    });
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("shows an actionable error state when the backend cannot be reached", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<Guarded />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach FlowLens");
    expect(alert).toHaveTextContent("Could not reach the FlowLens backend");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("retries the session check from the error state", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(okSession(true));

    render(<Guarded />);
    const retry = await screen.findByRole("button", { name: "Try again" });
    await userEvent.click(retry);

    await screen.findByText("Protected content");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears session state and posts logout when logging out", async () => {
    fetchMock
      .mockResolvedValueOnce(okSession(true))
      .mockResolvedValueOnce({ ok: true, status: 204 } as unknown as Response);

    render(<ActionProbe action="logout" />);
    await screen.findByText("@octocat");

    await userEvent.click(screen.getByRole("button", { name: "run logout" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/auth/logout",
        expect.objectContaining({ method: "POST", credentials: "include" })
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
  });

  it("falls back to unauthenticated on a refresh that returns 401 without redirecting", async () => {
    fetchMock
      .mockResolvedValueOnce(okSession(true))
      .mockResolvedValueOnce(unauthorized());

    render(<ActionProbe action="refresh" />);
    expect(await screen.findByText("authenticated")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "run refresh" }));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(replace).not.toHaveBeenCalled();
  });
});
