"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ApiError } from "@/lib/api-error";
import { errorMessage, useAsync } from "@/lib/use-async";
import { listSymbols, type Symbol } from "@/features/analysis/analysis-service";
import type { NodeKind, Pagination } from "@/types/api";

/**
 * Symbol browser for a completed analysis: search by short/qualified name,
 * filter by kind, paginate, and inspect one symbol's source location.
 * All data comes from `GET /api/v1/analyses/{analysis_id}/symbols`.
 */

const PER_PAGE = 25;
const SEARCH_DEBOUNCE_MS = 300;

const KIND_OPTIONS: ReadonlyArray<NodeKind> = ["module", "class", "function", "method"];

export function SymbolBrowser({ analysisId }: { analysisId: string }) {
  const [searchInput, setSearchInput] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const [kind, setKind] = React.useState<NodeKind | "">("");
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<Symbol | null>(null);

  // Debounce the search box; typing does not hammer the API per keystroke.
  React.useEffect(() => {
    const trimmed = searchInput.trim();
    const timer = setTimeout(() => {
      setDebouncedQuery(trimmed);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // New query/kind restarts the result set.
  React.useEffect(() => {
    setPage(1);
    setSelected(null);
  }, [analysisId]);

  const symbols = useAsync(
    async () => {
      try {
        return await listSymbols(
          analysisId,
          { q: debouncedQuery || undefined, kind: kind || undefined, page, perPage: PER_PAGE },
        );
      } catch (cause) {
        // Re-throw with the browser-specific message (e.g. ANALYSIS_NOT_READY)
        // so `useAsync` surfaces an actionable, code-aware error.
        throw new Error(symbolLoadError(cause));
      }
    },
    [analysisId, debouncedQuery, kind, page]
  );

  const items = symbols.data?.items ?? null;
  const pagination: Pagination | undefined = symbols.data?.pagination;

  return (
    <Card>
      <CardHeader>
        <CardTitle id="symbols-title">Symbols</CardTitle>
        <CardDescription>
          Search modules, classes, functions, and methods extracted from the
          snapshot by short or qualified name.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-56 flex-1">
            <Search
              aria-hidden="true"
              className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id="symbol-search"
              type="search"
              className="pl-8"
              placeholder="Search by name or qualified name"
              aria-label="Search symbols by name or qualified name"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </div>
          <select
              aria-label="Filter symbols by kind"
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as NodeKind | "");
                setPage(1);
                setSelected(null);
              }}
            >
              <option value="">All kinds</option>
              {KIND_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
        </div>

        {symbols.loading ? (
          <div className="space-y-2" aria-busy="true" aria-label="Loading symbols">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : symbols.error ? (
          <SymbolBrowserError message={symbols.error} onRetry={symbols.reload} />
        ) : !items ? null : items.length === 0 ? (
          <EmptyState
            title="No symbols found"
            description={
              debouncedQuery || kind
                ? "No symbols match the current search and kind filter. Adjust or clear them."
                : "This analysis did not find any Python symbols in the snapshot."
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  Symbols extracted from the analyzed snapshot
                </caption>
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th scope="col" className="py-2 pr-4 font-medium">Kind</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Name</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Qualified name</th>
                    <th scope="col" className="py-2 font-medium">File</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((symbol) => {
                    const isSelected = selected?.id === symbol.id;
                    return (
                      <tr
                        key={symbol.id}
                        aria-selected={isSelected}
                        className={`cursor-pointer border-b transition-colors hover:bg-muted/50 ${
                          isSelected ? "bg-accent" : ""
                        }`}
                        tabIndex={0}
                        onClick={() => setSelected(isSelected ? null : symbol)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelected(isSelected ? null : symbol);
                          }
                        }}
                      >
                        <td className="py-2 pr-4 align-top">{symbol.kind}</td>
                        <td className="py-2 pr-4 align-top font-medium">{symbol.name}</td>
                        <td className="py-2 pr-4 align-top">
                          <code className="whitespace-nowrap text-xs">{symbol.qualified_name}</code>
                        </td>
                        <td className="py-2 align-top text-xs">
                          {symbol.file_path}
                          {symbol.location
                            ? ` · lines ${symbol.location.start_line}–${symbol.location.end_line}`
                            : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground" aria-live="polite">
                {pagination
                  ? `Page ${pagination.page} of ${Math.max(pagination.total_pages ?? 1, 1)} · ${pagination.total} symbol${pagination.total === 1 ? "" : "s"}`
                  : null}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => {
                    setPage((current) => Math.max(current - 1, 1));
                    setSelected(null);
                  }}
                >
                  <ChevronLeft aria-hidden="true" className="size-4" /> Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isLastPage(pagination, page)}
                  onClick={() => {
                    setPage((current) => current + 1);
                    setSelected(null);
                  }}
                >
                  Next <ChevronRight aria-hidden="true" className="size-4" />
                </Button>
              </div>
            </div>

            {selected ? <SymbolDetail symbol={selected} /> : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Next-page disabled logic: trusted only when the backend reports
 * `total_pages`; without it the next page is allowed and an empty result
 * simply renders the empty state.
 */
function isLastPage(pagination: Pagination | undefined, page: number): boolean {
  if (!pagination || pagination.total_pages === undefined) return false;
  return page >= pagination.total_pages;
}

function SymbolBrowserError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <ErrorState
      title="Could not load symbols"
      message={message}
      onRetry={onRetry}
    />
  );
}

/** One symbol's detail: qualified identity plus source location. */
export function SymbolDetail({ symbol }: { symbol: Symbol }) {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="font-mono text-base">{symbol.qualified_name}</CardTitle>
        <CardDescription>
          Selected symbol — details from the completed analysis.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Kind</dt>
          <dd>{symbol.kind}</dd>
          <dt className="text-muted-foreground">File</dt>
          <dd>
            <code className="text-xs">{symbol.file_path}</code>
          </dd>
          {symbol.location ? (
            <>
              <dt className="text-muted-foreground">Lines</dt>
              <dd>{`${symbol.location.start_line}–${symbol.location.end_line}`}</dd>
              {symbol.location.start_column !== undefined &&
              symbol.location.end_column !== undefined ? (
                <>
                  <dt className="text-muted-foreground">Columns</dt>
                  <dd>{`${symbol.location.start_column}–${symbol.location.end_column}`}</dd>
                </>
              ) : null}
            </>
          ) : (
            <>
              <dt className="text-muted-foreground">Lines</dt>
              <dd className="text-muted-foreground">unknown</dd>
            </>
          )}
          {symbol.parent_id ? (
            <>
              <dt className="text-muted-foreground">Defined within</dt>
              <dd>
                <code className="text-xs">{symbol.parent_id}</code>
              </dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Symbol ID</dt>
          <dd>
            <code className="text-xs">{symbol.id}</code>
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

/**
 * Map an API error to a browser-specific message. `ANALYSIS_NOT_READY`
 * (symbols requested for a still-pending analysis) is the known case.
 */
export function symbolLoadError(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === "ANALYSIS_NOT_READY") {
    return "Symbols are not available yet — the analysis is still in progress.";
  }
  return errorMessage(cause);
}
