"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ProjectCard } from "@/features/projects/components/project-card";
import { listProjects } from "@/features/projects/projects-service";
import { useAsync } from "@/lib/use-async";

/**
 * Projects dashboard: the current user's projects with provider badges,
 * repository/ref metadata, latest snapshot, and latest analysis status
 * (Phase 3B). Loading, error, empty, and multi-page list states are real,
 * backend-driven states.
 */
export function ProjectsDashboard() {
  const [page, setPage] = React.useState(1);
  const { data, loading, error, reload } = useAsync(() => listProjects({ page }), [page]);

  const totalPages = data?.pagination.total_pages ?? 1;
  const hasProjects = (data?.items.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Your analysis workspaces — created from a GitHub repository or a ZIP upload.
          </p>
        </div>
        <Button asChild>
          <Link href="/projects/new">
            <Plus aria-hidden="true" className="size-4" /> New project
          </Link>
        </Button>
      </div>

      {loading ? (
        <div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          aria-busy="true"
          aria-label="Loading projects"
        >
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="space-y-3 p-4">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState
          title="Could not load your projects"
          message={error}
          onRetry={reload}
          retryLabel="Try again"
        />
      ) : !hasProjects ? (
        <EmptyState
          title="No projects yet"
          description="Create your first project by uploading a ZIP archive of a Python project or by connecting a GitHub repository through the FlowLens app."
        />
      ) : data ? (
        <>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((project) => (
              <li key={project.id}>
                <ProjectCard project={project} />
              </li>
            ))}
          </ul>

          <div className="border-t pt-4">
            {totalPages > 1 ? (
              <nav aria-label="Projects pagination" className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Page {data.pagination.page} of {totalPages} · {data.pagination.total} projects
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                  >
                    <ChevronLeft aria-hidden="true" className="size-4" /> Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                  >
                    Next <ChevronRight aria-hidden="true" className="size-4" />
                  </Button>
                </div>
              </nav>
            ) : (
              <p className="text-sm text-muted-foreground">
                {data.pagination.total} {data.pagination.total === 1 ? "project" : "projects"}
              </p>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
