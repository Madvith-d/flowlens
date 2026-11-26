# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam`
**Phase:** 6B complete — Impact visualization (Phases 2B/3B/4B/5B previously
merged; the impact panel is built strictly against the frozen impact endpoint
in `contracts/openapi.yaml`. Phase 6A backend — impact/risk API — is committed
on the backend workstream branch but **not merged to `main` yet**, so live
end-to-end verification against the real impact endpoint still has to happen
at integration time; nothing is fabricated in the meantime.)
**Ownership:** `frontend/**` only. No files in `backend/**` and no changes to
`contracts/openapi.yaml` were made in this phase.

---

## Completed in this session (Phase 6B)

All UI is built strictly against the frozen `contracts/openapi.yaml` impact
schemas (`ImpactRequest`, `ImpactResult`, `ImpactNode`, `RiskScore`,
`CoverageSummary`). Production paths call the real backend only; stubbed fetch
responses and a mocked Cytoscape module exist exclusively inside `tests/`.
The frontend never computes, recalculates, or estimates impact, hops, paths,
or risk — every displayed value comes from the impact response.

### Contract additions to the shared type module

- `src/types/api.ts` — added (1:1 with the contract schemas):
  `CoverageSummary`, `RiskFactorKey`, `RiskFactor`, `RiskScore`,
  `ImpactTargetRef`, `ImpactPath`, `ImpactNode`, `ImpactRequest`,
  `ImpactResult`. `RiskFactor.normalized_value` is typed `number | null` —
  excluded factors come back with `null` (verified against the Phase 6A
  backend behavior) and render as an em-dash, never as zero.

### Impact service (`src/features/impact/impact-service.ts`, new)

- `computeImpact` → `POST /api/v1/analyses/{analysis_id}/impact` with
  exactly `{ target_ids, direction, max_depth }`. Exported contract bounds:
  `IMPACT_MAX_TARGETS = 10`, depth 1–10, default 3.
- `impactRunError` maps known backend cases: 409 `ANALYSIS_NOT_READY` →
  actionable "still in progress" message; 404 `NOT_FOUND` with
  `details.missing_target_ids` → lists the stale target IDs and tells the
  user to remove them; anything else falls back to the shared error message.

### Components (`src/features/impact/components/`, new)

- `impact-panel.tsx` — target selection from the currently selected graph
  node (graph search drives selection), up to 10 target chips with remove
  action; traversal-direction radios (upstream/downstream/both, mirroring
  `ImpactDirection`) and a 1–10 hop depth select; run button disabled
  without targets; loading skeletons, retryable error state, no-impact
  empty state, `truncated` → partial-result alert, backend warnings list,
  static-reachability caveat. Changing the target set clears a stale result
  instead of keeping it on screen. In-flight requests abort on re-run and
  unmount. Publishes target/direct/indirect IDs and the focused path's edge
  IDs to the graph workspace for highlighting (all from the real response).
- `impact-results.tsx` — accessible impacted-symbol table: qualified name,
  kind, direct/indirect badge (text, not color-only), minimum hop distance,
  per-target attribution, keyboard-selectable rows; selecting a row picks
  the node in the graph (node detail + 1-hop neighbors are fetched there)
  and opens its representative paths.
- `risk-score-card.tsx` — score, version, "heuristic · not a failure
  probability" and coverage-inclusion badges in text; factor table with the
  backend-reported label, applied weight (fraction → percent, per the
  backend's renormalize-to-1 model), raw/normalized values (— when absent),
  included/excluded status, and factor descriptions; backend caveats listed
  verbatim. No client-side scoring of any kind.
- `impact-path-details.tsx` — representative paths per the response. Path
  edges are resolved against the currently visible graph edges; edges
  outside the visible graph are shown as bare edge IDs with an honest
  note — never reconstructed or guessed. Fully-resolvable chains get an
  orientation label only when it can be read off resolved endpoints
  ("runs impacted → target" / "runs target → impacted"); otherwise no
  orientation is claimed. Each resolved edge shows kind, confidence, and
  an evidence link that selects the edge in the graph.

### Graph integration (Phase 5B components extended)

- `graph-canvas.tsx` — optional impact props target/direct/indirect node
  outlines (distinct border style + color: solid blue / solid green /
  dashed amber) and path-edge highlighting (thick teal), restated as text
  in the legend — never color-only.
- `graph-legend.tsx` — "Impact highlighting" section (text descriptions of
  all four impact visuals), shown only while impact results are on screen.
- `graph-list-view.tsx` — "Impact" column in the accessible nodes table
  with text badges: `target`, `direct impact`, `indirect impact`,
  `not impacted` — the keyboard/AT-friendly mirror of the canvas encoding.
- `graph-workspace.tsx` — hosts the impact panel; memoized highlight sets
  feed the canvas/list view/legend; impact flows through the existing
  node/edge selection so node details, evidence, and neighbor expansion
  work for impacted nodes exactly like any other node. Highlighting is
  cleared when the panel unmounts.

### Pages

No new routes — the impact panel lives in the graph workspace
(`/projects/{id}/graph`), which is where targets are picked and results are
overlaid, per the Phase 6B tasks.

## Files added or changed (frontend/ only)

```
frontend/
├── IMPLEMENTATION_STATUS.md                      (this file)
├── src/types/api.ts                              (impact schemas added)
├── src/features/impact/
│   ├── impact-service.ts                         (new)
│   └── components/
│       ├── impact-panel.tsx                       (new)
│       ├── impact-results.tsx                     (new)
│       ├── risk-score-card.tsx                    (new)
│       └── impact-path-details.tsx                (new)
├── src/features/graph/components/
│   ├── graph-canvas.tsx                           (+impact highlighting)
│   ├── graph-legend.tsx                           (+impact legend section)
│   ├── graph-list-view.tsx                        (+impact status column)
│   └── graph-workspace.tsx                        (+impact panel hosting)
└── tests/
    ├── impact-service.test.ts                     (new: 5 tests)
    ├── impact-panel.test.tsx                       (new: 10 tests)
    └── graph-workspace.test.tsx                   (expansion depth/direction
                                                    query scoped to the
                                                    "Expand neighborhood"
                                                    group — the impact panel
                                                    adds a second labeled
                                                    depth/direction control)
```

## Commands run and observed results (Windows, Node 24 / npm 11)

- `npm run typecheck` (`tsc --noEmit`) — **pass, no errors**
- `npm run test` (`vitest run`) — **102 passed, 0 failed, 14 files**
  (86 pre-existing Phase 2B–5B tests still green; 16 new Phase 6B tests)
- `npm run lint` (`eslint .`) — **pass, 0 errors, 0 warnings**
- `npm run build` (`next build`) — **pass**; no route changes

Test notes: Cytoscape is mocked in `tests/impact-panel.test.tsx` and the
graph tests (the tests cover contract wiring and state handling, not pixel
layout); all API responses are stubbed `fetch` responses inside tests only.

## Mocked vs real API

- Production code paths call the real backend exclusively
  (`NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`; no provider tokens of
  any kind in frontend code/env/storage).
- Tests only: stubbed global `fetch` + a mocked `cytoscape` module; no MSW, no
  shipped fixtures, no mock results in the product flow.

## Known gaps / contract notes for Madvith (consumer view — no workaround invented)

1. **No per-impacted-node direction.** `ImpactNode` carries no
   upstream/downstream marker, so with `direction: both` the UI cannot label
   an impacted node as a caller vs a dependency. The UI shows the union list
   with hop distance, and states path orientation only when it is readable
   from resolved path endpoints. Candidate coordinated change: an optional
   `direction`/`orientation` field on `ImpactNode`.
2. **Paths are edge-ID sequences with no fetch-by-id.** `ImpactNode.paths[]`
   returns edge IDs, and the contract has no endpoint to fetch edges by ID,
   so the UI resolves them against the *currently visible* graph (graph +
   neighbor merges). Unresolvable edges are displayed as bare edge IDs with
   an honest note. Candidate change: an edge-detail endpoint, or embedding
   pre-resolved node chains in each path.
3. **`ImpactNode` has no source location or per-node confidence.** The
   impacted list cannot show file/line or resolution confidence without an
   extra `GET /nodes/{id}` call per node (the UI makes that call only when
   the user selects an impacted node). Low-confidence states are surfaced
   via backend `warnings` text and the confidence of resolved path edges
   only. Candidate change: optional `file_path`/`confidence` on
   `ImpactNode`.
4. **`ImpactResult.targets[]` echoes only `node_id` + `qualified_name`**
   (no kind), so target chips show qualified names only.
5. **`RiskScore.factors[].weight` is an untyped `number`.** The Phase 6A
   backend emits renormalized fractions summing to 1 (verified in
   `backend/app/services/analysis/risk.py`), which is what the percent
   rendering assumes; the contract would ideally document the 0–1 scale.
   `raw_value`/`description`/`caveats` are optional and render as
   "not reported" when absent.
6. Carried over from Phase 5B: no search/centered-graph parameter on the
   graph endpoint, no per-snapshot analysis history, counts-only
   diagnostics, repeated array query-param style confirmation.

## Next smallest actionable task

Phase 7B (diff, coverage and report UI): once Phase 7A merges, build the
diff paste/upload interface and changed-symbol summary against
`POST /analyses/{id}/diff`, the coverage overlay using
`ImpactResult.coverage_summary` / node `coverage_status` (`unknown` never
rendered as uncovered), and report generation/preview/download against
`POST /analyses/{id}/reports` + `GET /reports/{id}/download`.

---

# History

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
- Commands at the time: `npm run typecheck` pass; `npm run test` 86 passed
  (70 earlier + 16 new); `npm run lint` pass; `npm run build` pass with the
  `/projects/[project_id]/graph` route.
- Consumer-view gaps raised then (still open, see items above): no graph
  search parameter, no centered-subgraph request, repeated array
  query-param style, optional metrics/coverage fields, neighbor responses
  reusing the `GraphResponse` shape (only `nodes`/`edges`/`truncated`
  are merged).

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
