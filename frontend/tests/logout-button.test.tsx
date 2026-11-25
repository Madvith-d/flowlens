import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/session-provider";
import { LogoutButton } from "@/features/auth/components/logout-button";

/**
 * Logout UX: confirmation dialog, pending state, success navigation,
 * and failure state.
 */

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

function okSession(): Response {
  return {
    ok: true,
    status: 200,
    clone() {
      return okSession();
    },
    json: async () => ({
      authenticated: true,
      user: { id: "u1", github_login: "octo" },
    }),
  } as unknown as Response;
}

function errorResponse(status: number, code: string, message: string): Response {
  return {
    ok: false,
    status,
    clone() {
      return errorResponse(status, code, message);
    },
    json: async () => ({ error: { code, message, request_id: "r" } }),
  } as unknown as Response;
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

function renderLogout() {
  return render(
    <SessionProvider>
      <LogoutButton variant="outline" />
    </SessionProvider>
  );
}

describe("LogoutButton", () => {
  it("requires confirmation before signing out", async () => {
    fetchMock.mockResolvedValueOnce(okSession());
    renderLogout();

    const trigger = await screen.findByRole("button", { name: "Sign out" });
    await userEvent.click(trigger);

    expect(
      await screen.findByRole("heading", { name: /Sign out of FlowLens\?/i })
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // only /auth/me so far
  });

  it("calls the logout endpoint and navigates to /login?reason=signed-out on confirm", async () => {
    fetchMock
      .mockResolvedValueOnce(okSession())
      .mockResolvedValueOnce({ ok: true, status: 204 } as unknown as Response);
    renderLogout();

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await userEvent.click(await screen.findByRole("button", { name: /^Sign out$/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/auth/logout",
        expect.objectContaining({ method: "POST", credentials: "include" })
      );
    });
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login?reason=signed-out");
    });
  });

  it("cancels without calling the backend", async () => {
    fetchMock.mockResolvedValueOnce(okSession());
    renderLogout();

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    const logoutCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/auth/logout")
    );
    expect(logoutCalls).toHaveLength(0);
  });

  it("shows an error message when logout fails on the backend", async () => {
    fetchMock
      .mockResolvedValueOnce(okSession())
      .mockResolvedValueOnce(
        errorResponse(500, "INTERNAL_ERROR", "Logout is temporarily unavailable.")
      );
    renderLogout();

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await userEvent.click(await screen.findByRole("button", { name: /^Sign out$/ }));

    expect(
      await screen.findByText("Logout is temporarily unavailable.")
    ).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalledWith("/login?reason=signed-out");
  });
});
