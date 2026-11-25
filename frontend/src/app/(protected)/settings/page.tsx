"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AccountCard } from "@/components/layout/account-card";
import { useSession } from "@/features/auth/session-provider";

/**
 * Settings (Phase 2B scope: account and session). Installations/repositories,
 * graph limits and exclusions are appended in later phases backed by their
 * real API endpoints.
 */
export default function SettingsPage() {
  const { user, logout } = useSession();

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Account, session and FlowLens configuration.
        </p>
      </div>

      {user ? <AccountCard user={user} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>GitHub connection</CardTitle>
          <CardDescription>
            Repository installations and disconnection arrive with the GitHub
            integration phase. Disconnecting will never delete existing
            snapshots or reports.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>
            Sign out of FlowLens. You can return any time by signing in with
            GitHub.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <button
            className="text-sm text-destructive underline-offset-4 hover:underline"
            onClick={() => void logout()}
          >
            Sign out now
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
