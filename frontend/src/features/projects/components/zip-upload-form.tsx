"use client";

import * as React from "react";
import { FileArchive, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  createProjectFromUpload,
  type UploadProgress,
} from "@/features/projects/projects-service";
import { errorMessage } from "@/lib/use-async";
import type { Project } from "@/types/api";

/**
 * ZIP source creation form.
 *
 * - Client checks only what the browser can honestly check (a `.zip` file
 *   was chosen); size/content limits are enforced by the backend and its
 *   `UPLOAD_INVALID` / `UPLOAD_TOO_LARGE` errors are shown verbatim.
 * - Progress is the real XMLHttpRequest upload percentage — never a fake
 *   spinner-as-progress. After the body is sent, an indeterminate
 *   "processing server-side" state is shown.
 * - Duplicate submissions are prevented; failures keep the form fillable
 *   so the user can retry.
 */
export function ZipUploadForm({
  onCreated,
}: {
  /** Called with the created project; the page redirects to its workspace. */
  onCreated?: (project: Project) => void;
}) {
  const [name, setName] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [clientError, setClientError] = React.useState<string | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [progress, setProgress] = React.useState<UploadProgress | null>(null);
  const [sending, setSending] = React.useState(false);
  const [processing, setProcessing] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);

  const busy = sending || processing;

  const pickFile = (candidate: File | null | undefined) => {
    setUploadError(null);
    setProgress(null);
    if (!candidate) {
      setFile(null);
      setClientError(null);
      return;
    }
    const looksZip =
      candidate.name.toLowerCase().endsWith(".zip") ||
      candidate.type === "application/zip" ||
      candidate.type === "application/x-zip-compressed";
    if (!looksZip) {
      setFile(null);
      setClientError("Choose a ZIP archive (.zip). Other archive or file types are not accepted.");
      return;
    }
    setClientError(null);
    setFile(candidate);
  };

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
    setProcessing(false);
    setProgress(null);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setUploadError(null);
    if (!file) {
      setClientError("Choose a ZIP archive (.zip) to upload.");
      return;
    }
    setClientError(null);
    setSending(true);
    setProcessing(false);
    setProgress({ loaded: 0, total: file.size || 1 });
    const controller = new AbortController();
    abortRef.current = controller;

    // When the request body is fully sent, honestly switch to the
    // server-side processing phase (duration unknown → indeterminate).
    const handleProgress = (p: UploadProgress) => {
      setProgress(p);
      if (p.loaded >= p.total) {
        setSending(false);
        setProcessing(true);
      }
    };

    try {
      const project = await createProjectFromUpload({
        file,
        name: name.trim() || undefined,
        signal: controller.signal,
        onProgress: handleProgress,
      });
      toast.success("Project created", {
        description: "Your first immutable snapshot was created from the upload.",
      });
      onCreated?.(project);
    } catch (cause) {
      if (controller.signal.aborted) {
        // User-cancelled upload; nothing to report as an error.
        return;
      }
      setUploadError(errorMessage(cause));
      setProgress(null);
    } finally {
      if (!controller.signal.aborted) {
        setSending(false);
        setProcessing(false);
      }
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  // Report XHR progress with an honest phase split: body upload → server processing.
  const percent =
    progress && progress.total > 0 ? (progress.loaded / progress.total) * 100 : 0;

  return (
    <form className="space-y-5" onSubmit={submit} noValidate>
      <div className="space-y-2">
        <Label htmlFor="project-name">Project name (optional)</Label>
        <Input
          id="project-name"
          value={name}
          maxLength={200}
          placeholder="e.g. my-python-service"
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
          aria-describedby="project-name-hint"
        />
        <p id="project-name-hint" className="text-xs text-muted-foreground">
          Defaults to the archive name if left empty.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="zip-file">ZIP archive</Label>
        <div className="flex items-center gap-2">
          <Input
            id="zip-file"
            type="file"
            accept=".zip,application/zip,application/x-zip-compressed"
            onChange={(e) => pickFile(e.target.files?.[0])}
            disabled={busy}
            aria-describedby={clientError ? "zip-file-error" : "zip-file-hint"}
            aria-invalid={Boolean(clientError)}
          />
          <FileArchive aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
        </div>
        {file ? (
          <p className="text-xs text-muted-foreground">
            {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
          </p>
        ) : null}
        <p id="zip-file-hint" className="text-xs text-muted-foreground">
          A ZIP of a Python project. Max size and file-count limits are verified by FlowLens
          during upload; generated folders such as <code>.git</code> or <code>__pycache__</code>{" "}
          are skipped. Your code is analyzed statically and never executed.
        </p>
        {clientError ? (
          <p id="zip-file-error" role="alert" className="text-sm text-destructive">
            {clientError}
          </p>
        ) : null}
      </div>

      {uploadError ? (
        <Alert variant="destructive" role="alert">
          <AlertTitle>Upload failed</AlertTitle>
          <AlertDescription>
            {uploadError} You can try again — your selection is kept.
          </AlertDescription>
        </Alert>
      ) : null}

      {busy ? (
        <Progress
          value={sending ? percent : undefined}
          label={sending ? "Uploading archive" : "FlowLens is processing the archive server-side"}
        />
      ) : null}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? (
            <>
              <Loader2 aria-hidden="true" className="size-4 animate-spin" /> Working…
            </>
          ) : (
            <>
              <Upload aria-hidden="true" className="size-4" /> Create project from ZIP
            </>
          )}
        </Button>
        {sending ? (
          <Button type="button" variant="outline" onClick={cancel}>
            Cancel upload
          </Button>
        ) : null}
      </div>
      {busy ? (
        <p className="text-xs text-muted-foreground">
          {sending
            ? "Uploading — keep this tab open. You can cancel before the archive is sent."
            : "The archive is being processed by FlowLens; this usually takes a few seconds."}
        </p>
      ) : null}
    </form>
  );
}
