"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuthUser } from "@/types/api";

/** Signed-in identity summary, rendered from the safe /auth/me payload only. */
export function AccountCard({ user }: { user: AuthUser }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Signed in</CardTitle>
        <CardDescription>Your FlowLens account is linked to this GitHub identity.</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-4">
        <Avatar className="size-10">
          {user.avatar_url ? <AvatarImage src={user.avatar_url} alt="" /> : null}
          <AvatarFallback>{user.github_login.slice(0, 2)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">@{user.github_login}</p>
          <p className="text-xs text-muted-foreground">GitHub account</p>
        </div>
        <Badge variant="success" className="ml-auto">
          ✓ Active session
        </Badge>
      </CardContent>
    </Card>
  );
}
