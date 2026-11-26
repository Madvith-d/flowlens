"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Network, PlayCircle, Settings2, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatShortHash } from "@/lib/format";
import { errorMessage, useAsync } from "@/lib/use-async";
import { AnalysisStateBadge } from "@/features/projects/components/analysis-state-badge";
import { ProviderBadge } from "@/features/projects/components/provider-badge";
import { getProject, listSnapshots } from "@/features/projects/projects-service";
import { startAnalysis } from "@/features/analysis/analysis-service";
import { AnalysisCard } from "@/features/analysis/components/analysis-card";
import { SymbolBrowser } from "@/features/analysis/components/symbol-browser";
import { useAnalysisStatus } from "@/features/analysis/use-analysis-status";
import type { AnalysisRun, Snapshot } from "@/types/api";

/**
 * Project workspace (Phase 4B): project metadata, immutable snapshot
 * selection, the analysis lifecycle (start, bounded status polling,
 * diagnostics), and the symbol catalog of a completed run.
 *
 * Rules honored here:
 * - No fabricated progress or results; every state value is an API response.
 * - Analyses are started against a specific immutable snapshot id.
 * - Older snapshots have no server-known "latest analysis" state (the
 *   contract only exposes `Project.latest_analysis`), so their status shows
 *   as unknown rather than invented.
 */
export default function ProjectWorkspacePage() {
  const params = useParams<{ project_id: string }>();
  const projectId = params.project_id;

  const project = useAsync(() => getProject(projectId), [projectId]);
  const snapshots = useAsync(() => listSnapshots(projectId, { perPage: 50 }), [projectId]);

  const snapshotItems = snapshots.data?.items ?? null;

  // Selected snapshot defaults to the project's latest; the user can pick any
  // other immutable snapshot from the selector.
  const [selectedSnapshotId, setSelectedSnapshotId] = React.useState<string | null>(null);
  const selectedSnapshot: Snapshot | null = React.useMemo(() => {
    if (selectedSnapshotId) {
      return snapshotItems?.find((item) => item.id === selectedSnapshotId) ?? null;
    }
    return project.data?.latest_snapshot ?? snapshotItems?.[0] ?? null;
  }, [selectedSnapshotId, snapshotItems, project.data?.latest_snapshot]);

  // If the selected snapshot disappears (e.g. list reload), fall back to latest.
  React.useEffect(() => {
    if (selectedSnapshotId && snapshotItems && !snapshotItems.some((s) => s.id === selectedSnapshotId)) {
      setSelectedSnapshotId(null);
    }
  }, [selectedSnapshotId, snapshotItems]);

  // Analysis runs started in this session, keyed by snapshot id. Runs not
  // started here are only known through `Project.latest_analysis`.
  const [sessionRuns, setSessionRuns] = React.useState<Record<string, AnalysisRun>>({});

  const latestAnalysis = project.data?.latest_analysis ?? null;
  const latestBelongsToSelected =
    latestAnalysis !== null && selectedSnapshot !== null &&
    latestAnalysis.snapshot_id === selectedSnapshot.id;

  const effectiveRun: AnalysisRun | null = React.useMemo(() => {
    if (!selectedSnapshot) return null;
    const sessionRun = sessionRuns[selectedSnapshot.id];
    const candidate = sessionRun ?? (latestBelongsToSelected ? latestAnalysis : null);
    // Prefer whichever run is newer (a fresh start supersedes an old one).
    if (sessionRun && latestBelongsToSelected && latestAnalysis) {
      return latestAnalysis.created_at > sessionRun.created_at ? latestAnalysis : sessionRun;
    }
    return candidate;
  }, [selectedSnapshot, sessionRuns, latestBelongsToSelected, latestAnalysis]);

  const status = useAnalysisStatus(effectiveRun);
  const analysis = status.analysis;

  const [starting, setStarting] = React.useState(false);
  const [startError, setStartError] = React.useState<string | null>(null);

  // A run is in progress for the selected snapshot when its state is pending.
  const pendingRun = analysis !== null && (analysis.state === "queued" || analysis.state === "running");

  const startAnalysisRun = async () => {
    if (!selectedSnapshot) return;
    setStartError(null);
    setStarting(true);
    try {
      const run = await startAnalysis(selectedSnapshot.id);
      setSessionRuns((current) => ({ ...current, [selectedSnapshot.id]: run }));
      toast.success("Analysis started", {
        description: "The snapshot analysis was queued. Status updates automatically.",
      });
    } catch (cause) {
      setStartError(errorMessage(cause));
    } finally {
      setStarting(false);
    }
  };

  // Refresh project data when a polled run reaches a terminal state so
  // `Project.latest_analysis` stays authoritative. `finishedRef` guards
  // against repeat reloads when the effect re-runs.
  const finishedRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (
      analysis &&
      (analysis.state === "completed" ||
        analysis.state === "completed_with_warnings" ||
        analysis.state === "failed") &&
      finishedRef.current !== analysis.id
    ) {
      finishedRef.current = analysis.id;
      project.reload();
    }
  }, [analysis, project]);

  const projectData = project.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={`/projects/${projectId}`}>
            <ArrowLeft aria-hidden="true" className="size-4" /> Project settings
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="-mr-2">
          <Link href="/dashboard">
            All projects
          </Link>
        </Button>
      </div>

      {project.loading ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading project workspace">
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
              <p className="mt-1 text-sm text-muted-foreground">
                Workspace — analyze a snapshot and browse its symbols.
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <ProviderBadge provider={projectData.source_provider} />
                <AnalysisStateBadge state={analysis?.state} />
              </div>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href={`/projects/${projectId}`}>
                <Settings2 aria-hidden="true" className="size-4" /> Settings &amp; snapshots
              </Link>
            </Button>
          </div>

          {!selectedSnapshot ? (
            <EmptyState
              title="No source snapshot yet"
              description={
                projectData.source_provider === "github"
                  ? "This project has no source snapshot. Refresh the GitHub connection from the project settings to import one."
                  : "This project has no source snapshot. Create it again with a ZIP upload to add one."
              }
              action={{
                label: "Open project settings",
                onClick: () => {
                  window.location.assign(`/projects/${projectId}`);
                },
              }}
            />
          ) : (
            <>
              <SnapshotSelectCard
                snapshots={snapshotItems ?? []}
                selectedId={selectedSnapshot.id}
                onSelect={setSelectedSnapshotId}
                snapshotsError={snapshots.error}
                loading={snapshots.loading}
                onRetrySnapshots={snapshots.reload}
              >
                <SnapshotMetadata snapshot={selectedSnapshot} />
              </SnapshotSelectCard>

              <div className="space-y-4">
                {analysis ? (
                  <AnalysisCard
                    analysis={analysis}
                    pollLimitReached={status.pollLimitReached}
                    pollError={status.pollError}
                    onManualRefresh={status.refresh}
                  />
                ) : (
                  <NoAnalysisCard
                    hasLatestForOther={
                      latestAnalysis !== null && !latestBelongsToSelected
                    }
                    onStart={() => void startAnalysisRun()}
                    starting={starting}
                    startError={startError}
                    selectedSnapshotId={selectedSnapshot.id}
                  />
                )}

                {/* Retry a failed analysis (same immutable snapshot). */}
                {analysis && analysis.state === "failed" ? (
                  <Card>
                    <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
                      <p className="text-sm text-muted-foreground">
                        The last run for this snapshot failed. You can start a new
                        analysis — the snapshot is immutable, so conditions are identical.
                      </p>
                      <Button onClick={() => void startAnalysisRun()} disabled={starting}>
                        <PlayCircle aria-hidden="true" className="size-4" />
                        {starting ? "Starting…" : "Retry analysis"}
                      </Button>
                    </CardContent>
                  </Card>
                ) : null}

                {startError ? (
                  <Alert variant="destructive">
                    <AlertTitle>Could not start the analysis</AlertTitle>
                    <AlertDescription>{startError}</AlertDescription>
                  </Alert>
                ) : null}

                {analysis &&
                (analysis.state === "completed" || analysis.state === "completed_with_warnings") ? (
                  analysis.python_file_count === 0 ? (
                    <EmptyState
                      icon={TriangleAlert}
                      title="No Python files in this snapshot"
                      description="The analysis completed without parsing any Python files. Nothing to browse — check that the snapshot contains Python source."
                    />
                  ) : (
                    <>
                      <Card>
                        <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-1">
                          <p className="text-sm text-muted-foreground">
                            Explore statically inferred dependencies between the analyzed
                            symbols at module, class, and function level.
                          </p>
                          <Button asChild>
                            <Link href={`/projects/${projectId}/graph?analysis=${analysis.id}`}>
                              <Network aria-hidden="true" className="size-4" />
                              Open dependency graph
                            </Link>
                          </Button>
                        </CardContent>
                      </Card>
                      <SymbolBrowser analysisId={analysis.id} />
                    </>
                  )
                ) : pendingRun ? (
                  <p className="text-sm text-muted-foreground">
                    Symbols become searchable once the analysis completes.
                  </p>
                ) : null}
              </div>
            </>
          )}
        </>
      ) : null}
    </div>
  );
}

/** Snapshot picker plus the selected snapshot's provenance. */
function SnapshotSelectCard({
  snapshots,
  selectedId,
  onSelect,
  loading,
  snapshotsError,
  onRetrySnapshots,
  children,
}: {
  snapshots: Snapshot[];
  selectedId: string;
  onSelect: (snapshotId: string | null) => void;
  loading: boolean;
  snapshotsError: string | null;
  onRetrySnapshots: () => void;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Snapshot</CardTitle>
        <CardDescription>
          Analyses run against one immutable snapshot. Switching snapshots
          never changes historical results.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <Skeleton className="h-9 w-full max-w-md" />
        ) : snapshotsError ? (
          <ErrorState
            title="Could not load snapshots"
            message={snapshotsError}
            onRetry={onRetrySnapshots}
          />
        ) : snapshots.length === 0 ? (
          <p className="text-sm text-muted-foreground">No snapshots available.</p>
        ) : (
          <div className="max-w-md">
            <label htmlFor="snapshot-select" className="text-sm font-medium">
              Analyzed snapshot
            </label>
            <select
              id="snapshot-select"
              className="mt-1 h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={selectedId}
              onChange={(event) => onSelect(event.target.value)}
            >
              {snapshots.map((snapshot) => (
                <option key={snapshot.id} value={snapshot.id}>
                  {formatDateTime(snapshot.created_at)}
                  {snapshot.github_provenance
                    ? ` · ${snapshot.github_provenance.ref} @ ${formatShortHash(snapshot.github_provenance.commit_sha, 8)}`
                    : ` · ${formatShortHash(snapshot.content_hash, 8)}`}
                </option>
              ))}
            </select>
          </div>
        )}
        {children}
      </CardContent>
    </Card>
  );
}

/** Metadata of the selected snapshot (from the API, never inferred). */
function SnapshotMetadata({ snapshot }: { snapshot: Snapshot }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      <dt className="text-muted-foreground">Snapshot</dt>
      <dd>
        {formatDateTime(snapshot.created_at)} ·{" "}
        <code className="text-xs" title={snapshot.content_hash}>
          {formatShortHash(snapshot.content_hash, 10)}
        </code>
        {typeof snapshot.file_count === "number" ? ` · ${snapshot.file_count} files` : ""}
      </dd>
      {snapshot.github_provenance ? (
        <>
          <dt className="text-muted-foreground">Repository</dt>
          <dd>{snapshot.github_provenance.full_name}</dd>
          <dt className="text-muted-foreground">Ref</dt>
          <dd>{snapshot.github_provenance.ref}</dd>
          <dt className="text-muted-foreground">Commit</dt>
          <dd title={snapshot.github_provenance.commit_sha}>
            {formatShortHash(snapshot.github_provenance.commit_sha)}
          </dd>
        </>
      ) : (
        <>
          <dt className="text-muted-foreground">Source</dt>
          <dd>ZIP upload</dd>
        </>
      )}
    </dl>
  );
}

/**
 * Honest "no known analysis" state. For the project's latest snapshot this
 * simply means none exists yet; for older snapshots the status is unknown
 * because the contract exposes no per-snapshot analysis history.
 */
function NoAnalysisCard({
  hasLatestForOther,
  onStart,
  starting,
  startError,
  selectedSnapshotId,
}: {
  hasLatestForOther: boolean;
  onStart: () => void;
  starting: boolean;
  startError: string | null;
  selectedSnapshotId: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Analysis</CardTitle>
        <CardDescription>
          {hasLatestForOther
            ? "The project's latest analysis belongs to a different snapshot. No status is recorded for this snapshot; start a new run to analyze it."
            : "This snapshot has no analysis run yet. Start one to extract its symbols."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={onStart} disabled={starting}>
          <PlayCircle aria-hidden="true" className="size-4" />
          {starting ? "Starting…" : "Analyze this snapshot"}
        </Button>
        <p className="text-xs text-muted-foreground">
          FlowLens statically parses the snapshot&apos;s Python files — it never
          executes or installs the analyzed project.
        </p>
        {startError ? (
          <p role="alert" className="text-sm text-destructive">
            {startError}
          </p>
        ) : null}
        {/* Snapshot id surfaced for support/debugging context */}
        <p className="font-mono text-xs text-muted-foreground/70" title={selectedSnapshotId}>
          snapshot {selectedSnapshotId}
        </p>
      </CardContent>
    </Card>
  );
}
