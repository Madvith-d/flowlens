"use client";

import * as React from "react";
import { CircleAlert, Download, GitBranch, Search, Users } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  githubInstallUrl,
  listInstallationRepositories,
  listInstallations,
} from "@/features/github/github-service";
import { createProjectFromGithub } from "@/features/projects/projects-service";
import { errorMessage, useAsync } from "@/lib/use-async";
import type {
  GitHubInstallation,
  Project,
  RepositorySummary,
} from "@/types/api";

/**
 * GitHub source creation flow (Phase 3B):
 * installation/account → repository (search + pagination) → branch/tag/commit
 * ref → import. Every step renders real API data; access is never inferred
 * from a visibility label (the backend verifies at import time).
 */
export function GithubSourceForm({ onCreated }: { onCreated?: (project: Project) => void }) {
  const installations = useAsync(() => listInstallations(), []);
  const [installationId, setInstallationId] = React.useState<number | null>(null);

  const items = installations.data?.items ?? [];
  const selectedInstallation =
    items.find((i) => i.id === installationId) ?? null;

  return (
    <div className="space-y-6">
      <InstallFlowCard onInstalled={() => installations.reload()} />

      <section aria-labelledby="installation-heading" className="space-y-3">
        <h2 id="installation-heading" className="text-sm font-semibold">
          1. Choose an account or organization
        </h2>
        {installations.loading ? (
          <Skeleton className="h-10 w-full max-w-sm" aria-busy="true" />
        ) : installations.error ? (
          <ErrorState
            title="Could not list installations"
            message={installations.error}
            onRetry={installations.reload}
          />
        ) : items.length === 0 ? (
          <EmptyState
            title="FlowLens isn't installed anywhere yet"
            description="Install the FlowLens GitHub App on your personal account or an organization you administer, then return here. Repository access can be granted when installing or later from the installation settings on GitHub."
            icon={Users}
          />
        ) : (
          <div className="space-y-2">
            <Label htmlFor="installation-select">Installation</Label>
            <select
              id="installation-select"
              className="h-9 w-full max-w-sm rounded-md border border-border bg-card px-3 text-sm"
              value={installationId ?? ""}
              onChange={(e) => setInstallationId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Select an installation…</option>
              {items.map((installation: GitHubInstallation) => (
                <option key={installation.id} value={installation.id}>
                  {installation.account_login} ({installation.account_type})
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Only repositories the installation was granted access to are listed.
            </p>
          </div>
        )}
      </section>

      {selectedInstallation ? (
        <RepositoryStep
          installation={selectedInstallation}
          onImported={onCreated}
        />
      ) : null}
    </div>
  );
}

/** Install / manage FlowLens App link — full-page navigation to the backend. */
function InstallFlowCard({ onInstalled }: { onInstalled?: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="space-y-1">
          <p className="text-sm font-medium">Need to install or update the FlowLens GitHub App?</p>
          <p className="text-xs text-muted-foreground">
            FlowLens requests read-only Contents and Metadata permissions. After installing on
            GitHub you&apos;ll be redirected back — return to this page and reload to see the new
            account.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <a href={githubInstallUrl()}>
              <GitBranch aria-hidden="true" className="size-4" /> Install
            </a>
          </Button>
          <Button variant="outline" onClick={onInstalled}>
            Reload installations
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Steps 2–3 of the GitHub flow: repository selection for a fixed
 * installation, then ref entry and import.
 */
function RepositoryStep({
  installation,
  onImported,
}: {
  installation: GitHubInstallation;
  onImported?: (project: Project) => void;
}) {
  const [page, setPage] = React.useState(1);
  const [repoId, setRepoId] = React.useState<number | null>(null);
  const repositories = useAsync(
    () => listInstallationRepositories(installation.id, { page }),
    [installation.id, page]
  );

  const repos = repositories.data?.items ?? [];
  const pagination = repositories.data?.pagination;
  const totalPages = pagination?.total_pages ?? 1;
  const selected = repos.find((r) => r.id === repoId) ?? null;

  // Reset the chosen repository when the installation changes.
  React.useEffect(() => {
    setRepoId(null);
    setPage(1);
  }, [installation.id]);

  return (
    <>
      <section aria-labelledby="repository-heading" className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="repository-heading" className="text-sm font-semibold">
            2. Choose a repository
          </h2>
          <p className="text-xs text-muted-foreground">
            Repositories accessible to {installation.account_login}
          </p>
        </div>

        {repositories.loading ? (
          <div className="space-y-2" aria-busy="true" aria-label="Loading repositories">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : repositories.error ? (
          <ErrorState
            title="Could not list repositories"
            message={repositories.error}
            onRetry={repositories.reload}
          />
        ) : repos.length === 0 ? (
          <EmptyState
            title="No accessible repositories"
            description={`No repositories were granted to the FlowLens App installation for ${installation.account_login}. Open the installation settings on GitHub, select repositories for FlowLens, then reload this list.`}
            action={{ label: "Reload repositories", onClick: repositories.reload }}
          />
        ) : (
          <RepositoryList
            repos={repos}
            selectedId={repoId}
            onSelect={(id) => setRepoId(id === repoId ? null : id)}
          />
        )}

        {repos.length > 0 && totalPages > 1 ? (
          <nav aria-label="Repositories pagination" className="flex items-center justify-end gap-2">
            <span className="mr-auto text-xs text-muted-foreground">
              Page {pagination?.page} of {totalPages} · {pagination?.total} repositories
            </span>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </nav>
        ) : null}
      </section>

      {selected ? <RefAndImportStep installation={installation} repo={selected} onImported={onImported} /> : null}
    </>
  );
}

/** Accessible radio list of repositories with a within-page filter. */
function RepositoryList({
  repos,
  selectedId,
  onSelect,
}: {
  repos: RepositorySummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const [filter, setFilter] = React.useState("");

  const visible = React.useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return repos;
    return repos.filter((r) => r.full_name.toLowerCase().includes(needle));
  }, [repos, filter]);

  return (
    <div className="space-y-3">
      <div className="relative max-w-sm">
        <Search
          aria-hidden="true"
          className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter the visible page…"
          className="pl-8"
          aria-label="Filter repositories shown on this page"
        />
      </div>
      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground" role="status">
          No repositories on this page match &quot;{filter}&quot;. Clear the filter or go to another page.
        </p>
      ) : (
        <ul className="space-y-2">
          {visible.map((repo) => (
            <li key={repo.id}>
              <label
                className={
                  "flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:checked]:border-primary" +
                  (selectedId === repo.id ? " border-primary bg-accent/40" : " border-border")
                }
              >
                <input
                  type="radio"
                  name="repository-choice"
                  className="mt-1"
                  checked={selectedId === repo.id}
                  onChange={() => onSelect(repo.id)}
                  aria-label={`Select repository ${repo.full_name}`}
                />
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{repo.full_name}</span>
                    <Badge variant="secondary">{repo.visibility}</Badge>
                  </span>
                  {repo.description ? (
                    <span className="block truncate text-xs text-muted-foreground">
                      {repo.description}
                    </span>
                  ) : null}
                  <span className="block text-xs text-muted-foreground">
                    Default branch: {repo.default_branch}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        The visibility label is informational. FlowLens verifies your actual access on the
        server when importing — a repository you cannot access is rejected with a clear error.
      </p>
    </div>
  );
}

/**
 * Step 3: ref (pre-filled with the repository's default branch) and import
 * submit. The ref is validated server-side; invalid refs surface the
 * backend's message rather than a client-side guess.
 */
function RefAndImportStep({
  installation,
  repo,
  onImported,
}: {
  installation: GitHubInstallation;
  repo: RepositorySummary;
  onImported?: (project: Project) => void;
}) {
  const [ref, setRef] = React.useState(repo.default_branch);
  const [name, setName] = React.useState("");
  const [importing, setImporting] = React.useState(false);
  const [importError, setImportError] = React.useState<string | null>(null);

  // Keep the ref prefilled as the repository selection changes.
  React.useEffect(() => {
    setRef(repo.default_branch);
    setImportError(null);
  }, [repo.id, repo.default_branch]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setImportError(null);
    if (!ref.trim()) {
      setImportError("Enter a branch, tag, or commit SHA to import.");
      return;
    }
    setImporting(true);
    try {
      const project = await createProjectFromGithub({
        repository_id: repo.id,
        installation_id: installation.id,
        ref: ref.trim(),
        name: name.trim() || undefined,
      });
      toast.success("Project created", {
        description: `${repo.full_name} was imported into an immutable snapshot.`,
      });
      onImported?.(project);
    } catch (cause) {
      setImportError(errorMessage(cause));
    } finally {
      setImporting(false);
    }
  };

  return (
    <section aria-labelledby="ref-heading">
      <form className="space-y-4" onSubmit={submit} noValidate>
        <h2 id="ref-heading" className="text-sm font-semibold">
          3. Choose a ref and import
        </h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="ref-input">Branch, tag, or commit SHA</Label>
            <Input
              id="ref-input"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              disabled={importing}
              aria-describedby="ref-hint"
              placeholder="e.g. main"
            />
            <p id="ref-hint" className="text-xs text-muted-foreground">
              Pre-filled with {repo.default_branch}, the repository&apos;s default branch. FlowLens
              verifies the ref on the server and records the resolved commit SHA.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="github-project-name">Project name (optional)</Label>
            <Input
              id="github-project-name"
              value={name}
              maxLength={200}
              placeholder="Defaults to the repository name"
              onChange={(e) => setName(e.target.value)}
              disabled={importing}
            />
          </div>
        </div>

        {importError ? (
          <Alert variant="destructive" role="alert">
            <CircleAlert aria-hidden="true" className="size-4" />
            <AlertTitle>Import failed</AlertTitle>
            <AlertDescription>{importError}</AlertDescription>
          </Alert>
        ) : null}

        <Button type="submit" disabled={importing}>
          <Download aria-hidden="true" className="size-4" />
          {importing ? "Importing repository…" : `Import ${repo.full_name}`}
        </Button>
      </form>
    </section>
  );
}
