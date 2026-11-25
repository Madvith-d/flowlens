"use client";

import * as React from "react";
import { Link2Off } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

/**
 * Confirmation dialog for disconnecting a GitHub repository. The effect of
 * the action is stated explicitly: future access is removed; existing
 * snapshots and reports are retained (backend-enforced).
 */
export function DisconnectDialog({
  repositoryFullName,
  onConfirm,
  onDone,
}: {
  repositoryFullName: string;
  onConfirm: () => Promise<void>;
  /** Invoked after a confirmed disconnect (e.g. reload project data). */
  onDone?: () => void;
}) {
  const [working, setWorking] = React.useState(false);
  const [failure, setFailure] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);

  const confirm = async (event: React.MouseEvent) => {
    event.preventDefault();
    setFailure(null);
    setWorking(true);
    try {
      await onConfirm();
      toast.success("Repository disconnected", {
        description: "Existing snapshots and reports have been kept.",
      });
      setOpen(false);
      onDone?.();
    } catch (cause) {
      // Leave the dialog open with the actionable backend message.
      setFailure(
        cause instanceof Error ? cause.message : "Disconnecting failed. Try again."
      );
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); setFailure(null); }}>
      <DialogTrigger asChild>
        <Button variant="destructive">
          <Link2Off aria-hidden="true" className="size-4" /> Disconnect repository
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Disconnect {repositoryFullName}?</DialogTitle>
          <DialogDescription>
            This removes FlowLens&apos;s link to the repository. You will not be able to
            refresh sources from it until you connect it again, but all existing
            snapshots, analyses, and reports for this project are kept.
          </DialogDescription>
        </DialogHeader>
        {failure ? (
          <p role="alert" className="text-sm text-destructive">
            {failure}
          </p>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={working}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="destructive" onClick={confirm} disabled={working}>
            {working ? "Disconnecting…" : "Disconnect repository"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
