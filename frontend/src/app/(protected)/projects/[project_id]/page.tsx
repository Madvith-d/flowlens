"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, LayoutDashboard, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { ApiError } from "@/lib/api-error";
import { formatDateTime, formatShortHash } from "@/lib/format";
import { errorMessage, useAsync } from "@/lib/use-async";
import { AnalysisStateBadge } from "@/features/projects/components/analysis-state-badge";
import { ProviderBadge } from "@/features/projects/components/provider-badge";
import { DisconnectDialog } from "@/features/projects/components/disconnect-dialog";
import {
  disconnectGithubConnection,
  getProject,
  listSnapshots,
  refreshProject,
} from "@/features/projects/projects-service";
import type { Project, Snapshot } from "@/types/api";

/**
 * Project detail / settings screen (Phase 3B): source provenance, snapshot
 * history, and GitHub connection management (refresh / disconnect).
 */
export default function ProjectDetailPage() {
  const params = useParams<{ project_id: string }>();
  const projectId = params.project_id;

  const project = useAsync(() => getProject(projectId), [projectId]);
  const snapshots = useAsync(() => listSnapshots(projectId, { perPage: 50 }), [projectId]);

  const [createdNotice, setCreatedNotice] = React.useState(false);
  // sessionStorage guard so the notice does not reappear on in-app revisits.
  React.useEffect(() => {
    const key = `flowlens.created-notice.${projectId}`;
    const isFresh =
      new URLSearchParams(window.location.search).get("created") === "1" &&
      !window.sessionStorage.getItem(key);
    if (isFresh) {
      window.sessionStorage.setItem(key, "1");
      setCreatedNotice(true);
    }
  }, [projectId]);

  const projectData = project.data;

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/dashboard">
          <ArrowLeft aria-hidden="true" className="size-4" /> Back to projects
        </Link>
      </Button>

      {createdNotice ? (
        <Alert variant="success">
          <AlertTitle>Project created</AlertTitle>
          <AlertDescription>
            Its first immutable source snapshot is stored. Open the workspace to
            analyze it and browse its symbols.
          </AlertDescription>
        </Alert>
      ) : null}

      {project.loading ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading project">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : project.error ? (
        /does not exist|not owned by you|not found/i.test(project.error) ? (
          <ErrorState
            title="Project not found"
            message="This project does not exist or is not owned by you. Check the dashboard for your projects."
          />
        ) : (
          <ErrorState
            title="Could not load this project"
            message={project.error}
            onRetry={project.reload}
          />
        )
      ) : projectData ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{projectData.name}</h1>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <ProviderBadge provider={projectData.source_provider} />
                <AnalysisStateBadge state={projectData.latest_analysis?.state} />
              </div>
            </div>
            <Button asChild size="sm">
              <Link href={`/projects/${projectId}/workspace`}>
                <LayoutDashboard aria-hidden="true" className="size-4" />
                Open workspace
              </Link>
            </Button>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ProvenanceCard data={projectData} />
            <SnapshotHistoryCard
              loading={snapshots.loading}
              error={snapshots.error}
              onRetry={snapshots.reload}
              items={snapshots.data?.items ?? null}
            />
          </div>

          {projectData.source_provider === "github" ? (
            projectData.github_connection ? (
              <ConnectionActionsCard
                projectId={projectData.id}
                repositoryFullName={projectData.github_connection.full_name}
                currentRef={projectData.github_connection.ref}
                onRefreshed={() => {
                  project.reload();
                  snapshots.reload();
                }}
                onDisconnected={() => {
                  project.reload();
                  snapshots.reload();
                }}
              />
            ) : (
              <Alert variant="warning">
                <AlertTitle>Repository disconnected</AlertTitle>
                <AlertDescription>
                  This project&apos;s GitHub repository link was removed. Existing snapshots and
                  reports below are retained, but the source can no longer be refreshed.
                </AlertDescription>
              </Alert>
            )
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Source origin card: provider metadata + latest snapshot provenance. */
function ProvenanceCard({ data }: { data: Project }) {
  const snapshot = data.latest_snapshot;
  const provenance = snapshot?.github_provenance ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Source origin</CardTitle>
        <CardDescription>Where this project&apos;s source came from.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {data.github_connection ? (
            <>
              <dt className="text-muted-foreground">Repository</dt>
              <dd className="font-medium">{data.github_connection.full_name}</dd>
              <dt className="text-muted-foreground">Ref</dt>
              <dd>{data.github_connection.ref}</dd>
              {data.github_connection.visibility ? (
                <>
                  <dt className="text-muted-foreground">Visibility</dt>
                  <dd>
                    <Badge variant="secondary">{data.github_connection.visibility}</Badge>{" "}
                    <span className="text-xs text-muted-foreground">(informational)</span>
                  </dd>
                </>
              ) : null}
              <dt className="text-muted-foreground">Connected</dt>
              <dd>{formatDateTime(data.github_connection.connected_at)}</dd>
            </>
          ) : (
            <>
              <dt className="text-muted-foreground">Source</dt>
              <dd className="font-medium">ZIP upload</dd>
            </>
          )}
          {snapshot ? (
            <>
              <dt className="text-muted-foreground">Latest snapshot</dt>
              <dd>
                {formatDateTime(snapshot.created_at)} · {formatShortHash(snapshot.content_hash)}
                {typeof snapshot.file_count === "number" ? ` · ${snapshot.file_count} files` : ""}
              </dd>
            </>
          ) : (
            <>
              <dt className="text-muted-foreground">Latest snapshot</dt>
              <dd>None yet</dd>
            </>
          )}
          {provenance ? (
            <>
              <dt className="text-muted-foreground">Resolved commit</dt>
              <dd title={provenance.commit_sha}>{formatShortHash(provenance.commit_sha, 10)}</dd>
              <dt className="text-muted-foreground">Imported at</dt>
              <dd>{formatDateTime(provenance.imported_at)}</dd>
            </>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}

/** Immutable snapshot history, newest first (backend ordering). */
function SnapshotHistoryCard({
  items,
  loading,
  error,
  onRetry,
}: {
  items: Snapshot[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Snapshots</CardTitle>
        <CardDescription>
          Immutable source versions. Refreshing never changes a historical snapshot.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2" aria-busy="true" aria-label="Loading snapshots">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : error ? (
          <ErrorState title="Could not load snapshots" message={error} onRetry={onRetry} />
        ) : !items || items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No snapshots yet.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((snapshot) => (
              <li
                key={snapshot.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2.5 text-sm"
              >
                <span title={snapshot.content_hash}>
                  {formatDateTime(snapshot.created_at)} · {formatShortHash(snapshot.content_hash, 10)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {snapshot.github_provenance
                    ? `${snapshot.github_provenance.ref} @ ${formatShortHash(snapshot.github_provenance.commit_sha, 8)}`
                    : `${snapshot.provider} upload`}
                  {typeof snapshot.file_count === "number" ? ` · ${snapshot.file_count} files` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * GitHub connection management: refresh into a new snapshot (optionally a
 * different ref) and disconnect. Both actions only succeed through the
 * backend; permission failures are shown with their server messages.
 */
function ConnectionActionsCard({
  projectId,
  repositoryFullName,
  currentRef,
  onRefreshed,
  onDisconnected,
}: {
  projectId: string;
  repositoryFullName: string;
  currentRef: string;
  onRefreshed: () => void;
  onDisconnected: () => void;
}) {
  const [ref, setRef] = React.useState("");
  const [working, setWorking] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const refresh = async () => {
    setActionError(null);
    setWorking(true);
    try {
      const snapshot = await refreshProject(projectId, ref.trim() || undefined);
      toast.success("Snapshot refreshed", {
        description: `A new immutable snapshot (${
          snapshot.github_provenance
            ? `${snapshot.github_provenance.ref} @ ${formatShortHash(snapshot.github_provenance.commit_sha, 8)}`
            : formatShortHash(snapshot.content_hash, 8)
        }) was created.`,
      });
      setRef("");
      onRefreshed();
    } catch (cause) {
      setActionError(errorMessage(cause));
      if (cause instanceof ApiError && cause.status === 403) {
        setActionError(
          `${cause.message} The FlowLens App may have lost access to this repository. Check the installation and repository selection on GitHub, then try again.`
        );
      }
    } finally {
      setWorking(false);
    }
  };

  const disconnect = async () => {
    setActionError(null);
    await disconnectGithubConnection(projectId);
    onDisconnected();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>GitHub connection</CardTitle>
        <CardDescription>
          Connected to {repositoryFullName} (currently tracking{" "}
          <code>{currentRef}</code>).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="refresh-ref" className="text-sm font-medium">
            Refresh ref{" "}
            <span className="font-normal text-muted-foreground">
              (leave empty to re-snapshot <code>{currentRef}</code>)
            </span>
          </label>
          <div className="flex max-w-md gap-2">
            <Input
              id="refresh-ref"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              placeholder={`e.g. ${currentRef}`}
              disabled={working}
            />
            <Button onClick={() => void refresh()} disabled={working}>
              <RefreshCw aria-hidden="true" className="size-4" />
              {working ? "Refreshing…" : "Refresh snapshot"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Refreshing fetches the current state of the ref from GitHub and creates a new
            immutable snapshot. Existing snapshots and their analyses are never changed.
          </p>
        </div>

        {actionError ? (
          <p role="alert" className="text-sm text-destructive">
            {actionError}
          </p>
        ) : null}

        <div className="border-t pt-4">
          <DisconnectDialog
            repositoryFullName={repositoryFullName}
            onConfirm={disconnect}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Disconnecting removes future source access but keeps every existing snapshot and
            report in this project.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
