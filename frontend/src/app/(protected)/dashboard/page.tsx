"use client";

import { AccountCard } from "@/components/layout/account-card";
import { EmptyState } from "@/components/ui/states";
import { useSession } from "@/features/auth/session-provider";

export default function DashboardPage() {
  const { user } = useSession();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          Welcome{user ? `, @${user.github_login}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          Your projects and analyses will appear here.
        </p>
      </div>

      {user ? <AccountCard user={user} /> : null}

      <EmptyState
        title="No projects yet"
        description="Project creation from a ZIP upload or a GitHub repository arrives in the next milestone. Your account and session are fully working."
      />
    </div>
  );
}
