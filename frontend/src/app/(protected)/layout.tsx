"use client";

import { RequireAuth } from "@/features/auth/require-auth";
import { AppHeader } from "@/components/layout/app-header";

/**
 * Layout for all authenticated screens. Any page inside this group is
 * guarded: unauthenticated visitors are redirected to /login, loading and
 * backend-unavailable states render inside the shell.
 */
export default function ProtectedLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-dvh flex-col">
      <AppHeader />
      <main id="main-content" className="container flex-1 py-6">
        <RequireAuth>{children}</RequireAuth>
      </main>
      <footer className="border-t py-4">
        <div className="container text-xs text-muted-foreground">
          FlowLens · Static analysis assistant — results are inferred
          relationships, not runtime proof.
        </div>
      </footer>
    </div>
  );
}
