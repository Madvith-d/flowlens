"use client";

import * as React from "react";

import { setUnauthorizedHandler } from "@/lib/api-client";
import { ApiError } from "@/lib/api-error";
import { getCurrentSession, logout as apiLogout } from "@/features/auth/auth-service";
import type { AuthUser, SessionState } from "@/types/api";

export type SessionStatus = "loading" | "authenticated" | "unauthenticated" | "error";

interface SessionContextValue {
  status: SessionStatus;
  user: AuthUser | null;
  /** Human-readable reason shown on the login page (e.g. "expired"). */
  loginReason: string | null;
  /** Non-auth error message when the session check failed (backend down). */
  error: string | null;
  /** Re-run the `/auth/me` check. */
  refresh: () => Promise<void>;
  /** Logout: invalidates the backend session, then clears client state. */
  logout: () => Promise<void>;
}

const SessionContext = React.createContext<SessionContextValue | null>(null);

export function SessionProvider({
  children,
  initialSession,
}: {
  children: React.ReactNode;
  /** Server-provided session snapshot (optional; client checks `/auth/me`). */
  initialSession?: SessionState | null;
}) {
  const [status, setStatus] = React.useState<SessionStatus>(
    initialSession ? (initialSession.authenticated ? "authenticated" : "unauthenticated") : "loading"
  );
  const [user, setUser] = React.useState<AuthUser | null>(initialSession?.user ?? null);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setStatus((prev) => (prev === "loading" ? prev : "loading"));
    setError(null);
    try {
      const session = await getCurrentSession();
      if (session.authenticated && session.user) {
        setUser(session.user);
        setStatus("authenticated");
      } else {
        setUser(null);
        setStatus("unauthenticated");
      }
    } catch (err) {
      setUser(null);
      if (err instanceof ApiError && err.isAuthError) {
        // Signed out / expired session: not an infrastructure failure.
        setStatus("unauthenticated");
      } else {
        // Backend unreachable or unexpected error.
        setStatus("error");
        setError(
          err instanceof Error
            ? err.message
            : "Could not check your session. Verify the backend is running."
        );
      }
    }
  }, []);

  const loginReason = React.useMemo(() => {
    if (typeof window === "undefined") return null;
    const reason = new URLSearchParams(window.location.search).get("reason");
    return reason === "expired" || reason === "signed-out" ? reason : null;
  }, []);

  const logout = React.useCallback(async () => {
    // Clear client state even if the backend call fails, so the user is
    // never stuck in an authenticated-looking shell.
    setUser(null);
    setStatus("unauthenticated");
    try {
      await apiLogout();
    } catch (error) {
      // The backend session may already be gone; re-check the real state,
      // then rethrow so callers can show an actionable error.
      void refresh();
      throw error;
    }
  }, [refresh]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  // Mid-session 401s from any API call land here: mark signed-out so the
  // route guard redirects to login with the "expired" reason.
  React.useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setStatus("unauthenticated");
      window.location.assign("/login?reason=expired");
    });
    return () => setUnauthorizedHandler(() => {});
  }, []);

  const value = React.useMemo<SessionContextValue>(
    () => ({ status, user, loginReason, error, refresh, logout }),
    [status, user, loginReason, error, refresh, logout]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = React.useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used inside <SessionProvider>");
  }
  return ctx;
}
