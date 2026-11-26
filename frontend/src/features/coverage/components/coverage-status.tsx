import { Badge } from "@/components/ui/badge";
import type { CoverageStatus, CoverageSummary } from "@/types/api";

/**
 * Shared coverage display primitives (Phase 7B).
 *
 * The four contract statuses are always rendered with their full text (never
 * color alone), and `unknown` is always explained as "no information", never
 * as zero coverage — missing coverage is not coverage.
 */

/** Text + status of each coverage status, used by panels and the legend. */
export function CoverageStatusBadge({ status }: { status?: CoverageStatus }) {
  const resolved: CoverageStatus = status ?? "unknown";
  return (
    <Badge
      variant={
        resolved === "covered"
          ? "success"
          : resolved === "uncovered" || resolved === "partially_covered"
            ? "warning"
            : "secondary"
      }
    >
      {resolved.replace("_", " ")}
    </Badge>
  );
}

/**
 * One-line summary of counted statuses, e.g. the attach response's
 * `summary` or an impact result's `coverage_summary`.
 */
export function CoverageSummaryRow({
  summary,
  label = "Coverage:",
}: {
  summary?: CoverageSummary | null;
  label?: string;
}) {
  if (!summary) return null;
  const total =
    summary.covered + summary.partially_covered + summary.uncovered + summary.unknown;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-3 text-sm">
      <span className="font-medium">{label}</span>
      <Badge variant="success">covered · {summary.covered}</Badge>
      <Badge variant="warning">partially covered · {summary.partially_covered}</Badge>
      <Badge variant="warning">uncovered · {summary.uncovered}</Badge>
      <Badge variant="secondary">unknown · {summary.unknown}</Badge>
      <span className="text-xs text-muted-foreground">
        out of {total} symbol{total === 1 ? "" : "s"} · unknown means no coverage information,
        never zero coverage.
      </span>
    </div>
  );
}

/** Static legend rows: every status explained in text. */
export const COVERAGE_STATUS_LEGEND: ReadonlyArray<{
  status: CoverageStatus;
  description: string;
}> = [
  { status: "covered", description: "all executable lines of the symbol ran" },
  {
    status: "partially_covered",
    description: "some executable lines of the symbol ran",
  },
  { status: "uncovered", description: "no executable line of the symbol ran" },
  {
    status: "unknown",
    description: "no coverage information — not zero coverage, just no data",
  },
];

/**
 * Coverage legend block. Rendered by the coverage panel and reused by the
 * graph legend so both explain the exact same statuses.
 */
export function CoverageLegend({ title = "Coverage statuses" }: { title?: string }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium">{title}</p>
      <ul className="space-y-1 text-sm">
        {COVERAGE_STATUS_LEGEND.map(({ status, description }) => (
          <li key={status} className="flex items-center gap-2">
            <CoverageStatusBadge status={status} />
            <span className="text-muted-foreground">{description}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-xs text-muted-foreground">
        Execution coverage does not measure assertion quality or behavioral
        completeness.
      </p>
    </div>
  );
}
