import { FileWarning, FileX2, HelpCircle, Shuffle, type LucideIcon } from "lucide-react";

import type { DiagnosticsSummary as DiagnosticsSummaryData } from "@/types/api";

/**
 * Diagnostics summary (counts only, per the contract). Always icon + text;
 * zero counts read as "none", missing fields render "unknown" — never as 0.
 */
const ITEMS: ReadonlyArray<{
  key: keyof DiagnosticsSummaryData;
  label: string;
  icon: LucideIcon;
}> = [
  { key: "syntax_errors", label: "Syntax errors", icon: FileX2 },
  { key: "unresolved_references", label: "Unresolved references", icon: HelpCircle },
  { key: "ambiguous_references", label: "Ambiguous references", icon: Shuffle },
  { key: "skipped_files", label: "Skipped files", icon: FileWarning },
];

export function DiagnosticsSummaryList({
  summary,
}: {
  summary: DiagnosticsSummaryData | undefined;
}) {
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Analysis diagnostics counts">
      {ITEMS.map(({ key, label, icon: Icon }) => {
        const value = summary?.[key];
        return (
          <li
            key={key}
            className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs"
          >
            <Icon aria-hidden="true" className="size-3.5 text-muted-foreground" />
            <span title={value === undefined ? "Not reported" : undefined}>
              {label}: {value === undefined ? "unknown" : value}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
