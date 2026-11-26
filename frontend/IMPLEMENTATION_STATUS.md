# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam`
**Phase:** 7B complete — Diff review, coverage overlay, and report UI (Phases
2B/3B/4B/5B/6B previously merged on this branch). Phase 7A backend —
diff/coverage/report services — is **not built yet on this branch**, so the
new screens could only be verified against stubbed responses in tests and the
frozen `contracts/openapi.yaml`. At integration time (after Phase 7A merges),
the UI must be exercised against the real endpoints end to end; nothing was
fabricated or hard-coded in the meantime.
**Ownership:** `frontend/**` only. No files in `backend/**` were touched and
`contracts/openapi.yaml` was not modified.

---

## Completed in this session (Phase 7B)

Everything is built strictly against the frozen diff, coverage, and report
endpoint group in `contracts/openapi.yaml` (`analyzeDiff`, `attachCoverage`,
`generateReport`, `downloadReport` and the `DiffResult`/`CoverageResult`/
`ReportInfo` schemas). Production code paths call the real backend only;
stubbed responses exist exclusively inside `tests/`. The frontend never parses
a diff, validates a Coverage.py schema, maps lines to symbols, or generates a
report — it transmits input and renders responses.

### Contract additions to the shared type module

- `src/types/api.ts` — added (1:1 with the contract schemas): `DiffChangeType`,
  `ChangedSymbol`, `DiffFile`, `DiffResult`, `CoverageResult`, `ReportFormat`,
  `ReportRequest`, `ReportInfo`.

### API client

- `src/lib/api-client.ts` — added `apiClient.getText(path, signal)` returning
  the raw response body as text with the same cookie/timeout/401/error
  handling as JSON calls, plus an `Accept: text/markdown` header (the report
  download endpoint responds `text/markdown`).

### Diff review (`src/features/diff/`, new)

- `diff-service.ts` — `analyzeDiff` → `POST /api/v1/analyses/{analysis_id}/diff`
  with exactly `{ unified_diff }`; `diffRunError` maps `DIFF_INVALID` (422)
  and `ANALYSIS_NOT_READY` (409) to actionable messages.
- `components/diff-review-panel.tsx` — paste/upload unified diff (the uploaded
  file is read client-side as text and placed in the textarea; the diff itself
  is parsed only on the backend), loading, retryable error, and empty states.
  Renders changed files with text change-type badges, per-file mapped symbols
  with ids/kinds, the unmapped line count and the backend's `unmapped_reason`,
  and response warnings. The combined impact section reuses the Phase 6B
  `RiskScoreCard` plus a read-only impacted-symbol table (direct/indirect, hop
  distance, per-target attribution), the `coverage_summary` when present, a
  truncated alert, and an explicit "no impacted symbols — not a claim that
  the change is safe" empty state. Editing the diff clears a stale result;
  in-flight requests abort on re-run and unmount.

### Coverage overlay (`src/features/coverage/`, new)

- `coverage-service.ts` — `attachCoverage` → `POST /api/v1/analyses/{analysis_id}/coverage`
  with the **raw** Coverage.py JSON object as the body (the contract takes the
  artifact itself, not a wrapper); `coverageAttachError` maps `COVERAGE_INVALID`.
- `components/coverage-panel.tsx` — paste/upload artifact (only "is this JSON
  and is it an object" is checked client-side — schema/path validation is the
  backend's job and its errors are surfaced), summary counts as text badges,
  `unmatched_file_count` alert + response warnings, and a coverage legend
  that states `unknown` means no information, never zero coverage, and that
  execution coverage does not measure assertion quality.
- `components/coverage-status.tsx` — shared primitives: `CoverageStatusBadge`
  (full text, never color-only), `CoverageSummaryRow`, and `CoverageLegend`
  driven by one `COVERAGE_STATUS_LEGEND` source.

### Reports (`src/features/reports/`, new)

- `reports-service.ts` — `generateReport` → `POST /api/v1/analyses/{analysis_id}/reports`
  (201 → `ReportInfo`, optional `{ target_ids, direction, max_depth }` body),
  `downloadReportMarkdown` → `GET /api/v1/reports/{report_id}/download` as raw
  Markdown text, and `saveReportFile` which fetches credentialed, creates a
  Blob with the server-provided filename, and triggers the browser download.
- `components/reports-panel.tsx` — generate action with two scopes: entire
  analysis (empty body) or "changed symbols from the diff review" (enabled
  only when a real diff result with mapped symbols exists; sends the mapped
  `symbol_id` list with the diff response's `direction`/`max_depth` — all
  values echoed from real responses). Shows report metadata (filename, format,
  created_at, id), preview rendered verbatim from the downloaded Markdown,
  retryable preview/download error states, and an honest note that the
  contract exposes no report listing, so only reports generated in this
  session can be previewed/downloaded here.

### Review page and navigation

- `src/app/(protected)/projects/[project_id]/review/page.tsx` (new route
  `/projects/{id}/review`) — hosts the three panels for one completed
  analysis, selected via `?analysis=` or fall-back to the project's latest
  completed analysis (same rule as the graph page). Shows honest
  "analysis not finished" / "no completed analysis yet" empty states instead
  of inert tools. The diff result flows into the report scope only; panels
  never feed each other client-computed data.
- Workspace page — added a "Review changes & reports" CTA next to the graph
  CTA (completed analyses only).
- Graph workspace — added a "Review changes & reports" link in the header.

### Coverage overlay in graph/details/impact views (Phase 7B)

- `components/graph-canvas.tsx` — when coverage data exists in the graph
  response, a text marker is appended to node labels (`✓` covered, `◑`
  partially, `✗` uncovered, `?` unknown); markers are part of the label
  text and restated in the legend (never color-only).
- `components/graph-legend.tsx` — "Coverage overlay" section (shown only
  while at least one visible node reports a coverage status) explaining all
  four markers and that exhaustion-quality caveats apply.
- `components/graph-list-view.tsx` — "Coverage" column with full text badges
  (`covered`, `partially covered`, `uncovered`, `unknown`), the keyboard/AT
  mirror of the canvas markers.
- Node details panel already showed `coverage_status` as a text badge
  (Phase 5B); the diff combined-impact card and Phase 6B risk card show the
  coverage summary / "computed without coverage" badges.

## Files added or changed (frontend/ only)

```
frontend/
├── IMPLEMENTATION_STATUS.md                      (this file)
├── src/
│   ├── app/(protected)/projects/[project_id]/
│   │   ├── review/page.tsx                       (new route)
│   │   └── workspace/page.tsx                    (+review CTA)
│   ├── features/
│   │   ├── coverage/
│   │   │   ├── coverage-service.ts               (new)
│   │   │   └── components/
│   │   │       ├── coverage-panel.tsx            (new)
│   │   │       └── coverage-status.tsx           (new, shared primitives)
│   │   ├── diff/
│   │   │   ├── diff-service.ts                  (new)
│   │   │   └── components/
│   │   │       └── diff-review-panel.tsx         (new)
│   │   ├── reports/
│   │   │   ├── reports-service.ts                (new)
│   │   │   └── components/
│   │   │       └── reports-panel.tsx             (new)
│   │   └── graph/components/
│   │       ├── graph-canvas.tsx                  (+coverage label markers)
│   │       ├── graph-legend.tsx                 (+coverage overlay section)
│   │       ├── graph-list-view.tsx              (+coverage column)
│   │       └── graph-workspace.tsx              (+review link, +overlay flag)
│   ├── lib/api-client.ts                         (+getText for text/markdown)
│   └── types/api.ts                               (+diff/coverage/report types)
└── tests/
    ├── review-services.test.ts                    (new: 11 tests)
    ├── diff-review.test.tsx                        (new: 7 tests)
    ├── coverage-panel.test.tsx                     (new: 10 tests)
    ├── reports-panel.test.tsx                      (new: 8 tests)
    └── review-page.test.tsx                        (new: 4 tests)
```

## Commands run and observed results (Windows, Node 24 / npm 11)

- `npm run typecheck` (`tsc --noEmit`) — **pass, no errors**
- `npm run test` (`vitest run`) — **142 passed, 0 failed, 19 files**
  (102 pre-existing Phase 2B–6B tests still green; 40 new Phase 7B tests)
- `npm run lint` (`eslint .`) — **pass, 0 errors, 0 warnings**
- `npm run build` (`next build`) — **pass**; new route
  `/projects/[project_id]/review` (9.09 kB)

Test notes: all API responses are stubbed `fetch` responses inside tests only;
the reports download test stubs `URL.createObjectURL/revokeObjectURL` because
jsdom has no blob URL implementation. No Cytoscape mock was needed for the
new tests (they do not render the canvas).

## Mocked vs real API

- Production code paths call the real backend exclusively
  (`NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`; no provider tokens of
  any kind in frontend code/env/storage).
- Tests only: stubbed global `fetch`; no MSW, no shipped fixtures, no mock
  results in the product flow.

## Known gaps / contract notes for Madvith (consumer view — no workaround invented)

1. **No report listing endpoint.** The contract has report generate + download
   only, so the UI cannot show previously generated reports after navigation
   or reload; only reports generated in the current session are previewed/
   downloaded, and this is stated in the UI. Candidate: `GET
   /api/v1/analyses/{analysis_id}/reports` or `GET /api/v1/reports`.
2. **CoverageResult carries only summary counts.** There is no per-file or
   per-symbol coverage detail in the attach response (only `summary`,
   `unmatched_file_count`, `warnings`), so the UI cannot show *which* files
   failed to match; it reports the count and the consequence. Per-symbol
   status is available only through `GraphNode.coverage_status`. Candidate:
   optional `unmatched_files[]` on `CoverageResult`.
3. **No GET for the attached coverage state.** Coverage attach is write-only
   in the contract; after a reload the panel has no way to show that an
   artifact is attached (the graph/impact responses are the only evidence).
   Candidate: `GET /api/v1/analyses/{analysis_id}/coverage`.
4. **No Markdown rendering contract.** `downloadReport` returns
   `text/markdown` only; the preview shows it verbatim in monospace rather
   than rendered HTML. There is no deal-breaker here — just a UX note that a
   future HTML/JSON report-content endpoint would improve presentation.
5. **DiffResult has no per-hunk detail.** `DiffFile` exposes counts
   (`changed_line_count`, `unmapped_line_count`) and `unmapped_reason`, but no
   hunk line ranges or per-hunk mapping, so the UI cannot show exactly which
   ranges mapped to which symbol. Also `combined_impact` is a required field,
   so the UI relies on `impacted: []` (not a missing field) to mean "no
   impact".
6. **Report scoping semantics.** The reports request body accepts
   `target_ids/direction/max_depth`; the UI scopes it to the diff's mapped
   symbol ids with the diff response's own direction/depth. Exact semantics of
   "stored analysis/impact data" versus the diff's combined impact should be
   confirmed at integration time.
7. Carried over from Phase 6B: no per-impacted-node direction, no edge fetch-by-id,
   no `file_path`/`confidence` on `ImpactNode`, untyped `RiskFactor` scales,
   no graph search parameter, no per-snapshot analysis history, counts-only
   diagnostics.

## Next smallest actionable task

Phase 8 stabilization (accessibility/responsive/error-state review, mock-free
verification against the Phase 7A backend once it merges, and removing any
development-only conveniences from production paths), or, if Phase 7A is still
in flight, wait for the merge and then run the integrated end-to-end journey
(login → analyze → graph → diff → coverage → report) before requesting the
frontend merge.

---

# History

## Phase 6B complete — Impact visualization

(Kept for handoff context; the impact panel is built against the frozen
`POST /analyses/{id}/impact` endpoint in `contracts/openapi.yaml`.)

- `computeImpact` + `impactRunError` in `src/features/impact/impact-service.ts`;
  the impact panel (target chips, direction/depth, impacted table with
  min-hops and per-target attribution), risk score card (versioned factor
  table, coverage-included badge, caveats verbatim), and path details resolved
  strictly against visible graph edges.
- Graph integration: target/direct/indirect outlines (also restated as text
  in the legend and the accessible list view) and focused-path edge
  highlighting.
- Commands at the time: `npm run typecheck` pass; `npm run test` 102 passed;
  `npm run lint` pass; `npm run build` pass; no new routes.

## Phase 5B complete — Interactive dependency graph (Cytoscape.js)

(Kept for handoff context; the graph UI is built against the graph endpoint
group in `contracts/openapi.yaml`.)

- `getGraph`/`getNode`/`getNodeNeighbors` + `graphLoadError` in
  `src/features/graph/graph-service.ts`; bounded filtered base graph with
  additive neighbor expansion; canvas/table/legend; node and edge details
  with evidence, confidence, and resolver; `ANALYSIS_NOT_READY`/partial/
  unresolved-diagnostics states; no invented nodes or edges.
- `src/lib/api-client.ts` — repeated array query params
  (`?node_kinds=module&node_kinds=class`), the OpenAPI `form` style.
- Graph page `/projects/[project_id]/graph` with `?analysis=` parameter;
  workspace "Open dependency graph" CTA for completed analyses.
- Commands at the time: `npm run typecheck` pass; `npm run test` 86 passed;
  `npm run lint` pass; `npm run build` pass with the
  `/projects/[project_id]/graph` route.
- Consumer-view gaps raised then (still open, see items above).

## Phase 4B complete — Analysis status, symbols, and project workspace shell

(Kept for handoff context.)

- Analysis lifecycle UI: start analysis against a selected immutable snapshot
  (`POST /snapshots/{id}/analyses`), bounded 2s polling to terminal states,
  diagnostics summary, searchable symbol catalog, analysis-state badge,
  retry for failed runs, honest per-snapshot status.
- Commands at the time: `npm run typecheck` pass; `npm run test` 70 passed;
  `npm run lint` pass; `npm run build` pass with the
  `/projects/[project_id]/workspace` route.

## Phases 2B/3B (merged earlier)

Login/session UX, project dashboard, ZIP upload with real progress, GitHub
installation/repository/ref picker, project settings with refresh/disconnect.
See git history for the full 2B/3B session notes.
