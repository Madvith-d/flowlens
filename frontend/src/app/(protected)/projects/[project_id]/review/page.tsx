"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, FileDiff, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/lib/use-async";
import { getProject } from "@/features/projects/projects-service";
import { CoveragePanel } from "@/features/coverage/components/coverage-panel";
import { DiffReviewPanel } from "@/features/diff/components/diff-review-panel";
import { ReportsPanel } from "@/features/reports/components/reports-panel";
import type { DiffResult } from "@/types/api";

/**
 * Review page (Phase 7B): coverage attach, diff review, and report export
 * for one completed analysis. The analysis id comes from `?analysis=` or
 * falls back to the project's latest completed analysis — the same rule as
 * the graph page. Without a completed analysis there is nothing to review:
 * the page says so instead of rendering inert actions.
 */
export default function ProjectReviewPage() {
  return (
    <React.Suspense fallback={<ReviewPageSkeleton />}>
      <ProjectReviewPageContent />
    </React.Suspense>
  );
}

function ReviewPageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading review page">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-52 w-full" />
      <Skeleton className="h-52 w-full" />
    </div>
  );
}

function ProjectReviewPageContent() {
  const params = useParams<{ project_id: string }>();
  const projectId = params.project_id;
  const searchParams = useSearchParams();
  const analysisParam = searchParams.get("analysis");

  const project = useAsync(() => getProject(projectId), [projectId]);

  // Latest real diff result flows from the diff panel into the reports
  // panel (target scoping) — never the other way around.
  const [diffResult, setDiffResult] = React.useState<DiffResult | null>(null);

  if (project.loading) {
    return <ReviewPageSkeleton />;
  }

  if (project.error) {
    return /does not exist|not owned by you|not found/i.test(project.error) ? (
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
    );
  }

  const projectData = project.data;
  if (!projectData) return null;

  // Only a completed analysis can have coverage attached, diffs mapped, or
  // reports generated (the backend enforces this too — 409 ANALYSIS_NOT_READY).
  const latest = projectData.latest_analysis;
  const latestCompleted =
    latest && (latest.state === "completed" || latest.state === "completed_with_warnings")
      ? latest
      : null;

  const analysisId = analysisParam ?? latestCompleted?.id ?? null;

  if (!analysisId) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight">
          <FileDiff aria-hidden="true" className="mr-2 inline size-5" />
          Review changes — {projectData.name}
        </h1>
        {latest ? (
          <EmptyState
            icon={TriangleAlert}
            title="Analysis not finished"
            description={`The latest analysis for this project is ${latest.state.replace("_", " ")}. Diff review, coverage, and reports become available after an analysis completes successfully.`}
            action={{
              label: "Open the workspace",
              onClick: () => {
                window.location.assign(`/projects/${projectId}/workspace`);
              },
            }}
          />
        ) : (
          <EmptyState
            title="No completed analysis yet"
            description="Run an analysis on a snapshot in the project workspace first — diff review, coverage, and reports all operate on real analysis results."
            action={{
              label: "Open the workspace",
              onClick: () => {
                window.location.assign(`/projects/${projectId}/workspace`);
              },
            }}
          />
        )}
        <Button asChild variant="ghost" size="sm">
          <Link href="/dashboard">All projects</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={`/projects/${projectId}/workspace`}>
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to workspace
          </Link>
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/projects/${projectId}/graph?analysis=${analysisId}`}>
              Open dependency graph
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="-mr-2">
            <Link href="/dashboard">All projects</Link>
          </Button>
        </div>
      </div>

      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          <FileDiff aria-hidden="true" className="mr-2 inline size-5" />
          Review changes — {projectData.name}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Attach Coverage.py data, review a unified diff against this analysis, and export a
          Markdown report.{" "}
          <code className="text-xs" title={analysisId}>
            analysis {analysisId.slice(0, 8)}
          </code>
        </p>
      </div>

      <CoveragePanel analysisId={analysisId} />

      <DiffReviewPanel analysisId={analysisId} onResult={setDiffResult} />

      <ReportsPanel analysisId={analysisId} diffScope={diffResult} />
    </div>
  );
}
