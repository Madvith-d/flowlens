import {
  CheckCircle2,
  CircleSlash,
  Clock,
  Loader2,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { AnalysisState } from "@/types/api";

const STATE_META: Record<AnalysisState, { label: string; icon: LucideIcon; variant: "secondary" | "success" | "warning" | "destructive" }> = {
  queued: { label: "Queued", icon: Clock, variant: "secondary" },
  running: { label: "Running", icon: Loader2, variant: "secondary" },
  completed: { label: "Analyzed", icon: CheckCircle2, variant: "success" },
  completed_with_warnings: { label: "Analyzed with warnings", icon: TriangleAlert, variant: "warning" },
  failed: { label: "Analysis failed", icon: XCircle, variant: "destructive" },
};

/**
 * Analysis status badge: always icon + text label, never color alone.
 * Renders an explicit "No analysis yet" state when the project has no
 * analysis run — absence is a state, not an error.
 */
export function AnalysisStateBadge({ state }: { state?: AnalysisState }) {
  if (!state) {
    return (
      <Badge variant="outline">
        <CircleSlash aria-hidden="true" className="size-3.5" />
        No analysis yet
      </Badge>
    );
  }
  const meta = STATE_META[state];
  const Icon = meta.icon;
  return (
    <Badge variant={meta.variant}>
      <Icon aria-hidden="true" className="size-3.5" />
      {meta.label}
    </Badge>
  );
}
