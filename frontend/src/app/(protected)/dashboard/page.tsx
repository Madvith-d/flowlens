"use client";

import { ProjectsDashboard } from "@/features/projects/components/projects-dashboard";

/**
 * Authenticated dashboard (Phase 3B): the current user's projects with
 * provider badges, repository/ref metadata, latest snapshot, and analysis
 * status, plus the create-project entry point.
 */
export default function DashboardPage() {
  return <ProjectsDashboard />;
}
