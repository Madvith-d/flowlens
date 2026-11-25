"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FileArchive, GitBranch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { GithubSourceForm } from "@/features/github/components/github-source-form";
import { ZipUploadForm } from "@/features/projects/components/zip-upload-form";
import type { Project } from "@/types/api";

type SourceKind = "zip" | "github";

/**
 * Create-project source chooser (Phase 3B): pick ZIP upload or GitHub
 * repository connection. Both panes call real backend endpoints only.
 */
export default function NewProjectPage() {
  const router = useRouter();
  const [source, setSource] = React.useState<SourceKind>("zip");

  const openProject = (project: Project) => {
    router.push(`/projects/${project.id}?created=1`);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Create a project</h1>
        <p className="text-sm text-muted-foreground">
          FlowLens analyzes a snapshot of your source code — a ZIP archive you upload, or a
          GitHub repository the FlowLens App can read. Snapshots are immutable and your code
          is never executed.
        </p>
      </div>

      <div
        role="tablist"
        aria-label="Project source"
        className="inline-flex rounded-md border bg-card p-1"
      >
        <SourceTab
          active={source === "zip"}
          kind="zip"
          label="Upload ZIP"
          icon={<FileArchive aria-hidden="true" className="size-4" />}
          onSelect={setSource}
        />
        <SourceTab
          active={source === "github"}
          kind="github"
          label="Connect GitHub"
          icon={<GitBranch aria-hidden="true" className="size-4" />}
          onSelect={setSource}
        />
      </div>

      <div>
        {source === "zip" ? (
          <section aria-label="Create a project from a ZIP upload">
            <Card>
              <CardHeader>
                <CardTitle>Upload a ZIP archive</CardTitle>
                <CardDescription>
                  The archive is validated server-side (format, size, and safe paths) and
                  stored as an immutable first snapshot.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ZipUploadForm onCreated={openProject} />
              </CardContent>
            </Card>
          </section>
        ) : (
          <section aria-label="Create a project from a GitHub repository">
            <Card>
              <CardHeader>
                <CardTitle>Connect a GitHub repository</CardTitle>
                <CardDescription>
                  Pick an installation with the FlowLens App, choose a repository it can
                  read, then pick the branch, tag, or commit to snapshot.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <GithubSourceForm onCreated={openProject} />
              </CardContent>
            </Card>
          </section>
        )}
      </div>
    </div>
  );
}

function SourceTab({
  active,
  kind,
  label,
  icon,
  onSelect,
}: {
  active: boolean;
  kind: SourceKind;
  label: string;
  icon: React.ReactNode;
  onSelect: (kind: SourceKind) => void;
}) {
  return (
    <Button
      type="button"
      role="tab"
      aria-selected={active}
      variant={active ? "default" : "ghost"}
      size="sm"
      className="rounded-[5px]"
      onClick={() => onSelect(kind)}
    >
      {icon}
      {label}
    </Button>
  );
}
