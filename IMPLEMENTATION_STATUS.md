# FlowLens — Implementation Status

**Contributor:** Madvith (backend, GitHub integration, analysis engine)
**Current branch:** `madvith` (backend workstream, based on `main` `1013aeb`
after the Phase 5A and 5B merges)
**Phase:** 6A complete (impact analysis and explainable risk scoring)

## Completed work

### Phase 0 — Scaffold commit (on `main`, commit `9256538`) — done

Structure-only scaffold + shared `contracts/openapi.yaml`, verified: health
endpoints live, backend tests passed, frontend build/typecheck passed.

### Phase 2A — Backend foundation and account/session layer (merged to `main`) — done

FastAPI app factory with typed settings, JSON logging with credential
redaction, request IDs, stable error envelope, SQLAlchemy 2 models + Alembic,
Fernet token encryption, signed `HttpOnly` session cookies, Origin/CSRF
validation, GitHub App OAuth sign-in with one-time state, mocked-provider
tests. Commit `fbc4ec3`.

### Phase 3A — GitHub App installation and repository connection (merged to `main`) — done

RS256 app JWT, short-lived repository-scoped installation tokens, paginated
installations/repositories, ref→SHA resolution, allowlisted archive download
with SSRF guards, ownership-enforced import/refresh/disconnect. Migration
`a1c74f9d3e02`. Commit `439e6e6` (merged in `66ec9bc`).

### Phase 4A — Secure ZIP ingestion and AST analysis (merged to `main`) — done

Safe ZIP validation, streamed uploads, `ast` extraction with deterministic
symbol IDs, analysis runs and symbol catalogue APIs. Migration `b7f31c8e5a41`.
Commit `108b567` (merged in `11aafc6`).

### Phase 5A — Resolution, graph construction and graph APIs (merged to `main`) — done

`DependencyResolver` protocol + `StaticResolver` (lexical, imports/aliases,
relative imports, module-qualified calls, self/inherited methods, inheritance;
unresolved/ambiguous recorded, never guessed), `dependency_edges` with bounded
evidence, NetworkX graph service with module/class/function views, CONTAINS
kept structural, SCC-condensation reachability, bounded `/graph` + `/nodes` +
`/neighbors` APIs with ownership/409/404/400 envelopes. Migration
`c3d9e2ab5c71`. Commit `5976241` (merged in `34afcb2`).

### Phase 6A — Impact analysis and risk scoring (branch `madvith`)

**Traversal** (`app/services/analysis/impact.py`, new)
- `POST /api/v1/analyses/{analysis_id}/impact` per the frozen contract
  (`ImpactRequest`: 1–10 target IDs, direction `upstream`/`downstream`/`both`,
  `max_depth` 1–10 default 3).
- BFS over stored dependency edges only (never `CONTAINS`), visited-set cycle
  protection, shortest-hop distances, direct-vs-transitive classification.
- Multi-target: request IDs deduplicated; impacted nodes merged with exact
  `min_hops`, union `attributed_to`, no duplicates.
- Representative shortest paths: ordered sequences of the *same edge IDs the
  graph API exposes* (shared `view_edge_id`; representative kind per pair is
  CALLS > INHERITS > IMPORTS > REFERENCES), ordered target→impacted
  (downstream) or impacted→target (upstream), at most one per orientation.
- `IMPACT_MAX_IMPACTED_NODES` (500) bound with `truncated` flag + warning.
- Ownership enforced; 409 `ANALYSIS_NOT_READY` for unfinished runs; 404
  `ANALYSIS_NOT_FOUND`/`NOT_FOUND` (with `missing_target_ids` details) for
  missing analyses/targets; 400 `VALIDATION_ERROR` for bad requests.
- Warning strings disclose unresolved/ambiguous references excluded from the
  graph.

**Risk score** (`app/services/analysis/risk.py`, new)
- Versioned heuristic (`RISK_SCORE_VERSION`), configurable weights
  (default 35/20/15/15/15 per phases.md §20): upstream reachable dependents
  (normalized against `RISK_NORMALIZATION_CAP`), in-degree centrality
  (relative to graph max), downstream breadth, structural public/entry-point
  indicator (module-level def/module fraction), coverage deficiency.
- No coverage data exists before Phase 7A → factor excluded, weights
  renormalized over included factors, `coverage_included: false`, explicit
  caveat. Metrics-budget exemption removes reachability factors instead of
  estimating them. Every factor reports raw/normalized values and the applied
  (renormalized) weight; caveats state the score is a prioritization heuristic
  and NOT a failure probability.

## Files/modules added or changed (Phase 6A)

- Added: `app/services/analysis/impact.py`, `app/services/analysis/risk.py`,
  `app/api/v1/impact.py`, `tests/unit/test_impact_internals.py`,
  `tests/integration/test_impact_api.py`.
- Changed: `app/core/config.py` (impact/risk settings),
  `backend/.env.example`, `app/api/deps.py` (ImpactBundle),
  `app/main.py` (impact router), `app/services/analysis/graph.py`
  (extracted shared `view_edge_id` so impact path edge IDs match graph edge IDs),
  `docs/architecture.md`, `IMPLEMENTATION_STATUS.md`.
- No frontend files touched; no database changes; **no contract changes**
  (the impact route/schemas were already frozen in `contracts/openapi.yaml`).

## Exact commands executed and actual results

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **156 passed** (132 pre-existing + 24 new: 9 impact/risk unit, 15 impact API integration; 1 starlette deprecation warning). Baseline before this phase: 132 passed. |
| `.venv/bin/python -m compileall -q app tests` | clean |

(No migration this phase: impact is computed from stored analysis records.)

## Known issues, blockers, assumptions

- Risk is computed from *full*-graph metrics of the target set, independent of
  the requested direction/depth — by design: the factors characterize the
  targets, not the query. This is disclosed in factor descriptions.
- When the graph exceeds `GRAPH_METRICS_MAX_NODES`, reachability factors are
  excluded (score still served, with caveat) rather than estimated.
- Coverage deficiency is structurally wired but always excluded until Phase 7A
  attaches Coverage.py data; renormalization and disclosure are implemented and
  tested now.
- Impact runs on demand (no result persistence); `ImpactNode.paths` carries at
  most one representative path per orientation to keep payloads bounded.

## API/schema/database changes

- New endpoint (already in the frozen contract): `POST
  /api/v1/analyses/{analysis_id}/impact` → `ImpactResult` shape exactly per
  `contracts/openapi.yaml` (`targets`, `direction`, `max_depth`, `impacted`
  with `direct`/`min_hops`/`paths`/`attributed_to`, `truncated`, `risk` with
  factor breakdown and caveats, `warnings`, `coverage_summary: null`).
- Path edge IDs and graph edge IDs now come from one shared function, so
  clients can correlate impact paths with graph edges. No schema changes.

## Next smallest actionable task

Phase 7A start: unified diff parsing (headers/hunks, line-range mapping to
symbol spans, added/modified/deleted/unmapped classification) feeding the
combined-impact calculation with per-target attribution.


