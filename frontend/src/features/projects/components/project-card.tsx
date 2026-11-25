import Link from "next/link";
import { ChevronRight, GitBranch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AnalysisStateBadge } from "@/features/projects/components/analysis-state-badge";
import { ProviderBadge } from "@/features/projects/components/provider-badge";
import { formatDate, formatShortHash } from "@/lib/format";
import type { Project } from "@/types/api";

/**
 * Dashboard project card. Shows provider, repository/ref metadata, the
 * latest immutable snapshot, and the latest analysis state — all directly
 * from `Project` response fields. Visibility labels are informational
 * (access is verified server-side at import time).
 *
 * Renders as a single link for keyboard/screen-reader users, with all
 * metadata visible as text (not color-only).
 */
export function ProjectCard({ project }: { project: Project }) {
  const connection = project.github_connection ?? null;
  const snapshot = project.latest_snapshot ?? null;
  const provenance = snapshot?.github_provenance ?? null;
  const commitSha = provenance?.commit_sha ?? snapshot?.content_hash ?? null;

  return (
    <Card className="group transition-colors hover:border-primary/40">
      <CardContent className="p-4">
        <Link
          href={`/projects/${project.id}`}
          className="flex min-h-32 flex-col gap-2 focus-visible:outline-none"
        >
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-medium leading-tight group-hover:underline">{project.name}</h3>
            <ChevronRight aria-hidden="true" className="mt-1 size-4 shrink-0 text-muted-foreground" />
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <ProviderBadge provider={project.source_provider} />
            <AnalysisStateBadge state={project.latest_analysis?.state} />
          </div>

          {connection ? (
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{connection.full_name}</span>
              {" · "}
              <GitBranch aria-hidden="true" className="inline size-3" /> {connection.ref}
            </p>
          ) : snapshot ? (
            <p className="text-xs text-muted-foreground">
              Uploaded archive snapshot ({snapshot.file_count ?? 0} files)
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">No snapshot yet</p>
          )}

          <p className="mt-auto text-xs text-muted-foreground">
            {snapshot ? (
              <>
                Snapshot {formatDate(snapshot.created_at)} · {formatShortHash(commitSha, 10)}
              </>
            ) : (
              <>Created {formatDate(project.created_at)}</>
            )}
            {connection?.visibility ? (
              <>
                {" · "}
                <Badge variant="secondary" className="px-1.5 py-0 text-[11px]">
                  {connection.visibility}
                </Badge>
              </>
            ) : null}
          </p>
        </Link>
      </CardContent>
    </Card>
  );
}
