"use client";

import * as React from "react";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listSymbols } from "@/features/analysis/analysis-service";
import { useAsync } from "@/lib/use-async";
import type { Symbol } from "@/types/api";

const SEARCH_DEBOUNCE_MS = 300;
const PER_PAGE = 10;

/**
 * Graph node search. The graph endpoint has no search parameter in the
 * contract, so search reuses the documented symbol catalog
 * (`GET /analyses/{id}/symbols?q=`) — symbol IDs are the node IDs — and the
 * picked symbol is then fetched/expanded through the node and neighbor
 * endpoints. Nothing is searched or deduced client-side beyond this.
 */
export function GraphSearch({
  analysisId,
  onPick,
}: {
  analysisId: string;
  onPick: (symbolId: string) => void;
}) {
  const [input, setInput] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");

  React.useEffect(() => {
    const trimmed = input.trim();
    const timer = setTimeout(() => setDebouncedQuery(trimmed), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  // Only search once at least one character is typed.
  const results = useAsync(
    async () => {
      if (!debouncedQuery) return null;
      return await listSymbols(analysisId, { q: debouncedQuery, perPage: PER_PAGE });
    },
    [analysisId, debouncedQuery]
  );

  const items: Symbol[] | null =
    debouncedQuery && results.data && results.data.items.length > 0 ? results.data.items : null;

  return (
    <div className="space-y-2">
      <div className="relative max-w-md">
        <Search
          aria-hidden="true"
          className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="graph-search"
          type="search"
          className="pl-8"
          placeholder="Search nodes by name"
          aria-label="Search graph nodes by name"
          aria-describedby="graph-search-status"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
      </div>
      <p id="graph-search-status" aria-live="polite" className="text-xs text-muted-foreground">
        {results.loading && debouncedQuery
          ? "Searching…"
          : results.error
            ? `Search failed: ${results.error}`
            : debouncedQuery
              ? items
                ? items.length === 1
                  ? "1 match"
                  : `${items.length} matches`
                : "No symbols match — check the spelling or clear the search."
              : "Search uses the analysis symbol catalog; pick a result to select and expand it in the graph."}
      </p>
      {items ? (
        <ul
          aria-label="Symbol search results"
          className="max-h-48 max-w-md space-y-1 overflow-y-auto rounded-md border p-1"
        >
          {items.map((symbol) => (
            <li key={symbol.id}>
              <Button
                variant="ghost"
                className="h-auto w-full justify-start gap-2 px-2 py-1.5 text-left"
                onClick={() => {
                  onPick(symbol.id);
                  setInput("");
                }}
              >
                <span className="text-xs text-muted-foreground">{symbol.kind}</span>
                <code className="text-xs">{symbol.qualified_name}</code>
                <span className="text-xs text-muted-foreground">{symbol.file_path}</span>
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
