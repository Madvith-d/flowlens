"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/features/auth/session-provider";
import { LogoutButton } from "@/features/auth/components/logout-button";
import { Box } from "lucide-react";

/**
 * Application header shown on authenticated screens. Displays only data
 * from the safe `/auth/me` current-user response.
 */
export function AppHeader() {
  const { user, status } = useSession();
  const router = useRouter();

  const initials = user?.github_login?.slice(0, 2) ?? "?";

  return (
    <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur">
      <div className="container flex h-14 items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" className="px-2 font-semibold" onClick={() => router.push("/dashboard")}>
            <Box aria-hidden="true" className="text-primary" />
            FlowLens
          </Button>
        </div>

        <div className="flex items-center gap-3">
          {status === "error" ? (
            <Badge variant="warning" aria-label="Backend connection error">
              ⚠ Backend unreachable
            </Badge>
          ) : null}
          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                aria-label={`Account menu for ${user.github_login}`}
                className="rounded-full"
              >
                <Avatar>
                  {user.avatar_url ? <AvatarImage src={user.avatar_url} alt="" /> : null}
                  <AvatarFallback>{initials}</AvatarFallback>
                </Avatar>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium">@{user.github_login}</p>
                  <p className="text-xs text-muted-foreground">Signed in with GitHub</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => router.push("/settings")}>
                  Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <div className="w-full">
                    <LogoutButton variant="ghost" />
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>
    </header>
  );
}
