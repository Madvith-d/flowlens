"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useSession } from "@/features/auth/session-provider";
import { ApiError } from "@/lib/api-error";

/** Logout action with a confirmation dialog and explicit error state. */
export function LogoutButton({ variant = "ghost" }: { variant?: "ghost" | "outline" | "default" }) {
  const { logout } = useSession();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handleLogout() {
    setPending(true);
    setError(null);
    try {
      await logout();
      setOpen(false);
      router.replace("/login?reason=signed-out");
    } catch (err) {
      // Keep the dialog open so the failure is visible and retryable.
      setError(
        err instanceof ApiError
          ? err.message
          : "Sign out failed. Check your connection and try again."
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant}>Sign out</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sign out of FlowLens?</DialogTitle>
          <DialogDescription>
            You will need to sign in with GitHub again to return to your projects.
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={() => void handleLogout()} disabled={pending}>
            {pending ? "Signing out…" : "Sign out"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
