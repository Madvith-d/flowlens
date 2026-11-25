"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { useSession } from "@/features/auth/session-provider";
import { ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { NetworkError } from "@/lib/api-error";

/**
 * Authenticated route guard. Renders the appropriate state for each
 * session condition:
 * - loading → skeleton
 * - authenticated → children
 * - unauthenticated → redirect to /login
 * - error (backend unavailable) → actionable error state
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, error, refresh } = useSession();
  const router = useRouter();

  React.useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login?reason=expired");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="container space-y-4 py-10" aria-busy="true" aria-label="Checking your session">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="container max-w-xl py-16">
        <ErrorState
          title="Cannot reach FlowLens"
          message={
            error ??
            "The FlowLens backend did not respond. Check that it is running and try again."
          }
          onRetry={() => {
            void refresh();
          }}
        />
      </div>
    );
  }

  if (status === "unauthenticated") {
    // Redirect is in flight; render nothing to avoid flashing protected UI.
    return null;
  }

  return <>{children}</>;
}

/** Re-exported for tests: detectable network failure class name. */
export { NetworkError };
