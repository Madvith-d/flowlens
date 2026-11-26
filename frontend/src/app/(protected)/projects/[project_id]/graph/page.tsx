"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Network, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/lib/use-async";
import { getProject } from "@/features/projects/projects-service";
import { GraphWorkspace } from "@/features/graph/components/graph-workspace";

/**
 * Dependency graph page (Phase 5B). The analysis id comes from the
 * `?analysis=` query parameter (linked from the workspace after a completed
 * run) or falls back to the project's latest completed analysis. Without a
 * completed analysis there is nothing to draw — the page says so instead of
 * rendering an empty fake graph.
 */
export default function ProjectGraphPage() {
  return (
    <React.Suspense fallback={<GraphPageSkeleton />}>
      <ProjectGraphPageContent />
    </React.Suspense>
  );
}

function GraphPageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading dependency graph page">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-[420px] w-full" />
    </div>
  );
}

function ProjectGraphPageContent() {
  const params = useParams<{ project_id: string }>();
  const projectId = params.project_id;
  const searchParams = useSearchParams();
  const analysisParam = searchParams.get("analysis");

  const project = useAsync(() => getProject(projectId), [projectId]);

  if (project.loading) {
    return <GraphPageSkeleton />;
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

  // Latest analysis may be used only when it has actually completed; a
  // pending/failed run has no graph to show.
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
          <Network aria-hidden="true" className="mr-2 inline size-5" />
          Dependency graph — {projectData.name}
        </h1>
        {latest ? (
          <EmptyState
            icon={TriangleAlert}
            title="Analysis not finished"
            description={`The latest analysis for this project is ${latest.state.replace("_", " ")}. The graph becomes available after an analysis completes successfully.`}
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
            description="Run an analysis on a snapshot in the project workspace first; the dependency graph is drawn from real analysis results."
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
    <GraphWorkspace projectId={projectId} analysisId={analysisId} projectName={projectData.name} />
  );
}
