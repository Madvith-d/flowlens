# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam`
**Phase:** 4B complete — Analysis status, symbols, and project workspace shell
(Phases 2B/3B previously merged; built against Phase 2A+3A backend on this branch)
**Ownership:** `frontend/**` only. No files in `backend/**` or `contracts/openapi.yaml`
were modified in this phase.

## Completed in this session (Phase 4B)

All UI is built against the frozen `contracts/openapi.yaml` v0.1.0. Production paths call
the real backend only; stubbed fetch responses exist exclusively inside `tests/`.

### Shared foundation

- `src/types/api.ts` — contract types added: `SourceLocation`, `Symbol` (contract schema
  `Symbol`), `PaginatedSymbols`.
- `src/features/analysis/analysis-service.ts` (new) — typed wrappers:
  - `startAnalysis` → `POST /api/v1/snapshots/{snapshot_id}/analyses` (202 → `AnalysisRun`)
  - `getAnalysis` → `GET /api/v1/analyses/{analysis_id}`
  - `listSymbols` → `GET /api/v1/analyses/{analysis_id}/symbols` with `q`, `kind`,
    `page`, `per_page` query parameters (mapped/omitted exactly as documented)
  - `isPendingState` / `isTerminalState` helpers
- `src/features/analysis/use-analysis-status.ts` (new) — bounded polling hook:
  polls `GET /analyses/{id}` every 2s while `queued`/`running`; stops at terminal
  states, on unmount, on poll error (shows backend error + manual refresh), or after
  a 300-poll budget (~10 min) with an honest "Still running" + manual refresh — no
  fabricated progress.

### Components (`src/features/analysis/components/`, new)

- `analysis-card.tsx` — state badge (icon+text, never color-only), queued/running,
  failed (with `error_code`), completed-with-warnings; file/symbol/edge counters
  (`unknown` when the backend omits them); FlowLens/graph-schema versions; run id and
  timestamps; manual-refresh actions for poll error / budget exhaustion.
- `diagnostics-summary.tsx` — syntax errors / unresolved / ambiguous / skipped-files
  counts as icon+text chips; missing fields render "unknown", never 0.
- `symbol-browser.tsx` — searchable symbol catalog: debounced search (`q`), kind filter
  (`kind`), pagination with backend truth (`total_pages` gates the Next button; no
  fake page counts), keyboard-accessible table rows, and a selected-symbol detail view
  (kind, qualified name, snapshot-relative file path, line/column span, parent id).
  `ANALYSIS_NOT_READY` maps to an explicit "analysis still in progress" message.
  Empty state distinguishes "no matches for the filter" from "no symbols at all".

### Pages

- `/projects/[project_id]/workspace` (new) — project workspace shell:
  - Project header (name, provider badge, analysis-state badge) + links back to
    settings/dashboard.
  - Snapshot selector (defaults to the latest snapshot) with per-snapshot provenance
    (ref, resolved commit, content hash, file count); selection persistence is honest:
    switching snapshots switches which analysis state is shown.
  - Start analysis (`Analyze this snapshot` / `Retry analysis`) against the selected
    immutable snapshot id; duplicate submissions prevented while starting; errors
    surfaced from the backend envelope.
  - Status polling via `useAnalysisStatus`; after a terminal state the project is
    reloaded so `Project.latest_analysis` stays authoritative.
  - Per-snapshot honesty: the contract only exposes `Project.latest_analysis`, so for a
    snapshot without a known run the UI says so instead of inventing a status; a run
    started this session takes precedence over an older recorded run.
  - States: loading skeletons; no-source-snapshot empty state (with settings CTA);
    no-Python-files result state; failed-with-retry; completed-with-warnings with
    diagnostics; poll error/poll budget with manual refresh; project 404/not-owned.
- `/projects/[project_id]` (settings) — added "Open workspace" action and pointed the
  project-created notice at the workspace.

## Files added or changed (frontend/ only)

```
frontend/
├── IMPLEMENTATION_STATUS.md                              (this file)
├── src/types/api.ts                                      (Symbol/SourceLocation/PaginatedSymbols added)
├── src/features/analysis/
│   ├── analysis-service.ts                               (new)
│   ├── use-analysis-status.ts                            (new)
│   └── components/{analysis-card,diagnostics-summary,symbol-browser}.tsx (new)
├── src/app/(protected)/projects/[project_id]/workspace/page.tsx          (new)
├── src/app/(protected)/projects/[project_id]/page.tsx                    (workspace link + notice copy)
└── tests/
    ├── analysis-workspace.test.tsx                       (new: 10 tests)
    ├── symbol-browser.test.tsx                           (new: 6 tests)
    └── project-detail.test.tsx                            (+1 assertion: workspace link target)
```

## Commands run and observed results (Windows, Node 24 / npm 11)

- `npm run typecheck` (`tsc --noEmit`) — **pass, no errors**
- `npm run test` (`vitest run`) — **70 passed, 0 failed, 10 files**
  (54 pre-existing Phase 2B/3B tests still green; 16 new Phase 4B tests)
- `npm run lint` (`eslint .`) — **pass, no errors or warnings**
- `npm run build` (`next build`) — **pass**; routes now include
  `/projects/[project_id]/workspace` (dynamic server-rendered)

Notes from verification: fake timers drive the polling tests (queued → running →
completed transitions, poll failure + manual-refresh recovery, the 300-poll budget
stop). All API calls in tests are stubbed `fetch` responses only.

## Mocked vs real API

- Production code paths call the real backend exclusively
  (`NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`; no provider tokens of any
  kind in frontend code/env/storage).
- Tests only: stubbed global `fetch`; no MSW, no shipped fixtures, no mock results in
  product flow.

## Known gaps / integration notes for Madvith

1. **Analysis endpoints are Phase 4A backend scope** (`POST /snapshots/{id}/analyses`,
   `GET /analyses/{id}`, `GET /analyses/{id}/symbols`). The UI is contract-complete and
   tested against contract-shaped responses; live end-to-end verification (start →
   poll → symbols) must happen once Phase 4A merges into `main`. Until then the real
   backend will return 404 for these routes and no analysis UI state is fabricated.
2. **Per-snapshot analysis history gap (consumer view):** the contract has no way to
   list the latest analysis of an arbitrary (non-latest) snapshot — only
   `Project.latest_analysis` exists. The workspace therefore shows an honest "unknown /
   start a run" state for older snapshots. If a `GET /snapshots/{id}/analyses`-style
   endpoint (or per-snapshot latest analysis on `Snapshot`) is desired, coordinate the
   contract change and I will regenerate types + adapt the workspace.
3. Diagnostics are counts only (`DiagnosticsSummary`); there is no per-diagnostic detail
   endpoint in the contract, so the UI shows counts (and "unknown" when absent) rather
   than file-level lists. A details endpoint would be another coordination candidate.
4. Polling is client-side at 2s with a 300-attempt budget (~10 min) plus manual refresh;
   if the backend later offers push/progress mechanisms, the hook can be swapped.
5. `python_file_count === 0` renders an explicit "No Python files in this snapshot"
   state (no symbol browser) — correct per contract semantics; found nothing to fabricate.

## Next smallest actionable task

Phase 5B prerequisite check: once Phase 5A (resolver/graph APIs) lands, regenerate
types from `contracts/openapi.yaml` and start the Cytoscape.js graph workspace
(`/projects/[project_id]/graph`) using the bounded filtered graph/neighbors endpoints.
