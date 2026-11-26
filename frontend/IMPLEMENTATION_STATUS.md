# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam`
**Phase:** 5B complete — Interactive dependency graph (Cytoscape.js)
(Phases 2B/3B/4B previously merged; graph UI is built against the graph
endpoint group in `contracts/openapi.yaml`. Phase 5A backend — resolver/graph
APIs — is **not** merged yet, so the live backend currently returns 404 for
`/graph`, `/nodes/{id}`, `/nodes/{id}/neighbors`; no graph state is fabricated
in the meantime.)
**Ownership:** `frontend/**` only. No files in `backend/**` and no changes to
`contracts/openapi.yaml` were made in this phase.

---

## Completed in this session (Phase 5B)

All UI is built strictly against the frozen `contracts/openapi.yaml` v0.1.0
graph endpoints. Production paths call the real backend only; stubbed fetch
responses and a mocked Cytoscape module exist exclusively inside `tests/`.

### Contract additions to the shared type module

- `src/types/api.ts` — added: `EdgeKind`, `ImpactDirection`, `Confidence`,
  `CoverageStatus`, `GraphView`, `GraphNodeMetrics`, `GraphNode`,
  `EdgeEvidence`, `GraphEdge`, `GraphResponse` (1:1 with the contract schemas).
- `src/lib/api-client.ts` — query values now support `readonly string[]`,
  serialized as repeated params (`?kinds=a&kinds=b`, the OpenAPI `form`
  collection format) for the contract's `node_kinds` / `edge_kinds` arrays.
  No behavior change for scalar params.

### Graph service (`src/features/graph/graph-service.ts`, new)

- `getGraph` → `GET /api/v1/analyses/{analysis_id}/graph` with `view`
  (module/class/function), repeated `node_kinds`, repeated `edge_kinds`,
  and `limit` (contract max 2000) — sent only when the user picks filters;
  empty kind lists are omitted (backend default: all kinds).
- `getNode` → `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}`.
- `getNodeNeighbors` → `GET .../nodes/{node_id}/neighbors` with `depth`
  (1–3), `direction` (upstream/downstream/both), optional `limit` (max 500).
- `graphLoadError` maps `ANALYSIS_NOT_READY` (409) to an actionable message.

### Components (`src/features/graph/components/`, new)

- `graph-canvas.tsx` — Cytoscape.js (the sole MVP renderer, added as the only
  new runtime dependency, v3.35 with bundled TS types). Dynamically imported
  so SSR/prerendering never touches browser rendering APIs. Zoom in/out,
  fit-to-view, layout reset, click-to-select for nodes and edges,
  click-background-to-deselect. Node kind is encoded with shape + color +
  short label; low-confidence edges are dashed; `CONTAINS` uses square arrows
  and a lighter gray to stay visually distinct from dependency edges; the
  selected element gets a blue highlight. Honest render-failure message with
  a table-view fallback.
- `graph-filters.tsx` — view level (module/class/function), node-kind and
  edge-kind checkboxes (with the contract's "CONTAINS is structural" note),
  and the node-limit select (100/500/1000/2000). Every control maps 1:1 to a
  documented query parameter; the server applies all filtering.
- `graph-legend.tsx` — every visual distinction restated in text (never
  color-only), including the low-confidence and CONTAINS semantics and a
  static-inference caveat.
- `graph-search.tsx` — node search through the documented symbol catalog
  (`GET /analyses/{id}/symbols?q=`; symbol IDs are the node IDs per the
  contract's PathNodeId description); picking a result selects and expands
  that node via the real graph endpoints. The graph endpoint itself has no
  search parameter (see gaps).
- `graph-list-view.tsx` — accessible table alternative: nodes table
  (kind/name/qualified name/file + lines) and relationships table
  (kind with structural marker, from → to, confidence text badge);
  keyboard-selectable rows sharing the same selection state as the canvas.
- `node-details-panel.tsx` — selected node's qualified name, kind, source
  location, node ID, in/out-degree and reachable counts ("unknown" when the
  backend omits metrics), coverage status badge (`unknown` when absent, never
  zero), direct callers / callees derived only from returned-and-merged
  server edges with per-edge kind, confidence and evidence links, an
  edge-evidence panel (resolver, every evidence file:line:column with the
  bounded source expression), and the bounded expansion controls
  (depth 1–3, direction, server-truncation notice).
- `graph-workspace.tsx` — composition: bounded base graph fetch driven by
  the filter key, additive merge of neighbor-expansion responses (reset on
  any base-filter change), selection coordination (node XOR edge), server
  `truncated` → "Partial graph" alert with the returned `total_nodes`,
  `unresolved_count` shown as a diagnostics note, loading/empty/error
  states (with `ANALYSIS_NOT_READY` mapping and retry), canvas/table display
  toggle, and honest visible node/edge counts.

### Pages

- `/projects/[project_id]/graph` (new) — graph page wrapped in Suspense for
  `useSearchParams`. The analysis id comes from `?analysis=` (linked from the
  workspace) or falls back to `Project.latest_analysis` only when it is in a
  completed state. Without a completed analysis the page explains that there
  is no graph to draw and points to the workspace — no empty fake graph.
- `/projects/[project_id]/workspace` — added an "Open dependency graph" action
  shown only for completed/completed-with-warnings analyses with Python files,
  linking to `/projects/{id}/graph?analysis={analysis_id}`.

### Header/summary honesty rules honored

- `view` defaults to the contract default (`function`) and is always sent.
- No node/edge is invented: callers/callees lists derive exclusively from
  edges returned by the graph and neighbors endpoints.
- Truncation flags, counts, metrics, coverage, confidence, resolver, and
  evidence all come from API responses; absent values render as "unknown".

## Files added or changed (frontend/ only)

```
frontend/
├── IMPLEMENTATION_STATUS.md                      (this file)
├── package.json / package-lock.json              (+ cytoscape ^3.35.0)
├── src/types/api.ts                              (graph schemas added)
├── src/lib/api-client.ts                         (repeated array query params)
├── src/features/graph/
│   ├── graph-service.ts                          (new)
│   └── components/
│       ├── graph-canvas.tsx                       (new)
│       ├── graph-filters.tsx                      (new)
│       ├── graph-legend.tsx                       (new)
│       ├── graph-search.tsx                       (new)
│       ├── graph-list-view.tsx                    (new)
│       ├── node-details-panel.tsx                 (new)
│       └── graph-workspace.tsx                    (new)
├── src/app/(protected)/projects/[project_id]/graph/page.tsx        (new)
├── src/app/(protected)/projects/[project_id]/workspace/page.tsx    (+graph CTA)
└── tests/
    ├── graph-service.test.ts                     (new: 6 tests)
    └── graph-workspace.test.tsx                  (new: 10 tests)
```

## Commands run and observed results (Windows, Node 24 / npm 11)

- `npm install cytoscape` — installed `cytoscape@3.35.0` (bundled TS types).
- `npm run typecheck` (`tsc --noEmit`) — **pass, no errors**
- `npm run test` (`vitest run`) — **86 passed, 0 failed, 12 files**
  (70 pre-existing Phase 2B/3B/4B tests still green; 16 new Phase 5B tests)
- `npm run lint` (`eslint .`) — **pass, 0 errors, 0 warnings**
- `npm run build` (`next build`) — **pass**; routes now include
  `/projects/[project_id]/graph` (dynamic server-rendered)

Test notes: Cytoscape is mocked in `tests/graph-workspace.test.tsx` (the tests
cover contract wiring and state handling, not pixel layout); all API responses
are stubbed `fetch` responses inside tests only.

## Mocked vs real API

- Production code paths call the real backend exclusively
  (`NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`; no provider tokens of
  any kind in frontend code/env/storage).
- Tests only: stubbed global `fetch` + a mocked `cytoscape` module; no MSW, no
  shipped fixtures, no mock results in the product flow.

## Known gaps / contract notes for Madvith (consumer view — no workaround invented)

1. **Graph endpoints are Phase 5A scope and not merged yet** — the UI is
   contract-complete and tested against contract-shaped responses; live
   end-to-end verification must happen once Phase 5A lands on `main`.
2. **No search on the graph endpoint:** `GET /analyses/{id}/graph` has no
   `q`/search parameter. The UI searches the documented symbol catalog
   (`GET /analyses/{id}/symbols?q=` — symbol IDs are node IDs per the
   contract) and then selects/expands via `GET /nodes/{id}` +
   `/nodes/{id}/neighbors`. Optional improvement to consider: a `q` (or
   `focus_node_id`) parameter on `/graph` so result sets can stay server-bounded.
3. **No centered-subgraph request:** the contract offers no way to request a
   graph centered on a node (`center_node_id` + `hops`), so a focused first
   view of a very large graph must rely on `limit` + neighbor expansion. The
   neighbors endpoint covers exploration, but a centered-graph parameter
   would keep initial views bounded for big repositories.
4. **Array query-param style assumption:** `node_kinds`/`edge_kinds` are
   OpenAPI-form arrays; the frontend sends repeated params
   (`?node_kinds=module&node_kinds=class`), which FastAPI parses by default.
   Please confirm the 5A implementation expects this style during integration.
5. **`GraphNode.metrics`/`coverage_status` are optional** — the UI renders
   "unknown" when they are absent; no value is ever defaulted client-side.
6. Neighbor-expansion responses reuse the `GraphResponse` shape (with its own
   `view` value); the UI merges only `nodes`/`edges`/`truncated` from them.
7. Carried over from earlier phases: no per-snapshot analysis history, and
   diagnostics are counts only (see Phase 4B notes below).

## Next smallest actionable task

Phase 6B (impact visualization): once Phase 6A (impact/risk API) merges,
regenerate types if needed and build the impact panel against
`POST /api/v1/analyses/{analysis_id}/impact` — direction/depth controls,
direct/indirect rendering, hop distances, representative paths, backend risk
score + factor breakdown (all displayed from backend values, never
recalculated client-side), linked to graph node selection.

---

# History

## Phase 4B complete — Analysis status, symbols, and project workspace shell

(Kept for handoff context; superseded work entries above.)

- Analysis lifecycle UI: start analysis against a selected immutable snapshot
  (`POST /snapshots/{id}/analyses`), bounded 2s polling to terminal states
  (`use-analysis-status.ts`, 300-poll budget ~10 min with manual refresh),
  diagnostics summary (`syntax_errors`, `unresolved_references`,
  `ambiguous_references`, `skipped_files`; "unknown" when absent), searchable
  symbol catalog (`GET /analyses/{id}/symbols` with `q`/`kind`/pagination and
  backend-truth `total_pages`), analysis-state badge with masked/unknown
  handling, retry for failed runs, honest per-snapshot status (the contract
  only exposes `Project.latest_analysis`, so older snapshots show an honest
  unknown state rather than an invented status).
- Commands at the time: `npm run typecheck` pass; `npm run test` 70 passed
  (54 earlier + 16 new); `npm run lint` pass; `npm run build` pass with the
  `/projects/[project_id]/workspace` route.
- Consumer-view gaps raised then (still open): per-snapshot analysis history is
  not exposed by the contract; diagnostics detail is counts-only. Both remain
  candidates for a coordinated contract change.

## Phases 2B/3B (merged earlier)

Login/session UX, project dashboard, ZIP upload with real progress, GitHub
installation/repository/ref picker, project settings with refresh/disconnect.
See git history for the full 2B/3B session notes.
