# FlowLens — Implementation Status

**Contributor:** Madvith (backend, GitHub integration, analysis engine)
**Current branch:** `madvith` (backend workstream, based on merged `main` 11aafc6)
**Phase:** 5A complete (resolver, graph construction, graph APIs)

## Completed work

### Phase 0 — Scaffold commit (on `main`, commit `9256538`) — done

Structure-only scaffold + shared `contracts/openapi.yaml`, verified: health
endpoints live, backend tests passed, frontend build/typecheck passed.

### Phase 2A — Backend foundation and account/session layer (merged to `main`) — done

FastAPI app factory with typed settings, JSON logging with credential redaction,
request IDs, stable error envelope, SQLAlchemy 2 models + Alembic, Fernet token
encryption, signed `HttpOnly` session cookies, Origin/CSRF validation, GitHub App
OAuth sign-in with one-time state, mocked-provider tests. Commit `fbc4ec3`.

### Phase 3A — GitHub App installation and repository connection (merged to `main`) — done

RS256 app JWT (hand-rolled with `cryptography`), short-lived repository-scoped
installation tokens, paginated installations/repositories, ref→SHA resolution,
allowlisted `codeload` archive download with bounded validated redirects (SSRF
guard), projects import/refresh/disconnect with server-side installation and
repository verification, ownership enforcement, `GITHUB_API_ERROR` /
`GITHUB_APP_NOT_CONFIGURED` contract codes, migration `a1c74f9d3e02`.
Commit `439e6e6` (merged in `66ec9bc`).

### Phase 4A — Secure ZIP ingestion and AST analysis (merged to `main`) — done

Real-ZIP validation (magic bytes, traversal/symlink/duplicate/zip-bomb
defenses), `POST /projects/from-upload` with streaming size cap, `ast`-based
extraction of modules/classes/functions/methods/nested defs/decorators/bases/
imports/calls with deterministic symbol IDs, analysis runs
(`queued`→`running`→`completed[+with_warnings]`/`failed`) and searchable symbol
catalogue APIs. Migration `b7f31c8e5a41`. Commit `108b567` (merged in `11aafc6`).

### Phase 5A — Resolution, graph construction and graph APIs (branch `madvith`)

**Resolver** (`app/services/analysis/resolver.py`, new)
- `DependencyResolver` protocol over plain records (symbols/calls/imports), fully
  independent of AST extraction; `StaticResolver` implements it.
- Resolves: lexical module-local calls, `from m import n` / `import x.y as z`
  bindings (incl. pre-5A stored import rows), relative imports (`from .` /
  `from ..` in modules and package `__init__` files), module-qualified calls of
  any depth (`pkg.mod.func()`), `self.method()` against the lexically enclosing
  class, inherited methods through resolvable bases (cycle-safe BFS),
  `ClassName.method()` calls, and class bases → INHERITS edges. External
  (stdlib/third-party) imports are out of scope: no edge, no diagnostic.
- Never guesses: duplicate symbol names (`AMBIGUOUS_REFERENCE`), dynamic calls
  (`getattr(...)()`), and local-variable receivers (`svc = Service()`;
  `svc.run()`) stay unresolved with `UNRESOLVED_REFERENCE` diagnostics and exact
  occurrence counters stored on the run. Diagnostic rows are capped
  (`ANALYSIS_MAX_REFERENCE_DIAGNOSTICS`); counters stay exact and an
  `UNRESOLVED_LIMIT_REACHED` warning reports the truncation.
- Edges are deduplicated per `(source, target, kind)` with stable IDs; stored
  confidence is the most conservative contribution, `resolver` names the
  strongest strategy; evidence is bounded and ordered.
- Parser import records now carry `bindings` (`asname`-aware) — the JSON shape
  is backward-compatible with pre-5A rows.

**Graph store/service/API** (`app/services/analysis/graph.py`,
`app/api/v1/graph.py`, new)
- Per-analysis NetworkX DiGraph; `CONTAINS` derived from `Symbol.parent_id`,
  structural, never stored in `dependency_edges` and never traversed as a
  dependency.
- `GET /analyses/{id}/graph` — views `module`/`class`/`function` (deterministic
  collapse), `node_kinds`/`edge_kinds` filters (OpenAPI `form` collection
  format), `limit` ≤ 2000, `truncated` + `total_nodes`/`total_edges`/
  `unresolved_count` per the contract.
- `GET /analyses/{id}/nodes/{node_id}` — metrics
  (`in_degree`, `out_degree`, `upstream_reachable`, `downstream_reachable`)
  and `coverage_status: "unknown"` (coverage is Phase 7A).
- `GET /analyses/{id}/nodes/{node_id}/neighbors` — depth 1–3,
  `upstream`/`downstream`/`both`, `limit` ≤ 500, at symbol granularity with
  an extra `query` block describing the expansion.
- Reachability via SCC condensation (cycle-safe, exact) and only computed up to
  `GRAPH_METRICS_MAX_NODES` (10k): beyond it, degrees are served and reachable
  counts are omitted rather than estimated.
- Graph/node/neighbors answer 409 `ANALYSIS_NOT_READY` before the run completes
  (tested by flipping a live run to `running`), 404 `ANALYSIS_NOT_FOUND` /
  `NOT_FOUND` for missing or foreign-owned analyses, 400 envelope for invalid
  filters. Ownership is enforced on every endpoint.

**Analysis service integration** (`app/services/analysis/service.py`)
- `_execute` now runs the resolver after persisting symbols/calls, stores the
  edges (`ANALYSIS_MAX_EDGES` budget) and reference diagnostics, and finishes
  the run with the real `edge_count` and the exact unresolved/ambiguous
  counters. `diagnostics_summary` now includes `unresolved_references` and
  `ambiguous_references` per the contract's `DiagnosticsSummary`.

## Files/modules added or changed (Phase 5A)

- Added: `app/services/analysis/resolver.py`, `app/services/analysis/graph.py`,
  `app/api/v1/graph.py`,
  `alembic/versions/c3d9e2ab5c71_dependency_edges.py`,
  `tests/unit/test_resolver.py`, `tests/unit/test_graph_internals.py`,
  `tests/integration/test_graph_api.py`.
- Changed: `app/models/analysis.py` (`DependencyEdge` model, diagnostic codes),
  `app/models/projects.py` (`unresolved_reference_count`,
  `ambiguous_reference_count` on `AnalysisRun`), `app/models/__init__.py`,
  `app/repositories/analysis.py` (edge repo, symbol/call listing,
  `finish(...)` counters), `app/services/analysis/parser.py` (import
  `bindings`), `app/services/analysis/service.py` (resolver integration),
  `app/core/config.py` + `backend/.env.example` (resolver/graph bounds),
  `app/api/deps.py` (graph bundle), `app/main.py` (graph router),
  `backend/pyproject.toml` (`networkx>=3.0`), `contracts/openapi.yaml`
  (documented 409 on nodes/neighbors — additive, see below),
  `docs/architecture.md`, `IMPLEMENTATION_STATUS.md`,
  `tests/integration/test_upload_and_analysis.py` (updated the Phase 4A
  placeholder `edge_count == 0` to the real assertion).
- No frontend files touched; no root config touched.

## Exact commands executed and actual results

| Command | Result |
|---|---|
| `uv pip install --python .venv/bin/python "networkx>=3.0"` | Installed `networkx==3.7` |
| `.venv/bin/python -m pytest -q` | **132 passed** (107 pre-existing + 25 new: 6 resolver unit, 5 graph-internals unit, 14 graph API integration; 1 starlette deprecation warning). Pre-change baseline was 107 passed. |
| `DATABASE_URL=sqlite:////tmp/flowlens_5a.db .venv/bin/python -m alembic upgrade head` (clean DB) | All four migrations applied (`48e88e749069` → `a1c74f9d3e02` → `b7f31c8e5a41` → `c3d9e2ab5c71`); new table `dependency_edges` + both counters verified via `PRAGMA table_info` |
| `DATABASE_URL=… .venv/bin/python -m alembic check` | "No new upgrade operations detected" — no model/migration drift |
| `.venv/bin/python -m compileall -q app tests` | clean |

## Known issues, blockers, assumptions

- Resolver is deliberately conservative: local-variable receivers
  (`x = Class(); x.run()`) are unresolved because assignments are not tracked;
  dotted base classes (`class X(pkg.Base)`) are unresolved; `REFERENCES` edges
  are reserved but not produced (no non-call attribute references are recorded
  by the 4A extractor). All are documented limitations, never guesses.
- Analysis runs still execute inline; resolution adds one parse of the stored
  rows per run (no cross-request graph cache yet — Phase 8 profiling target).
  Both source providers produce the same resolver inputs by construction.
- The dependency-edge budget (`ANALYSIS_MAX_EDGES`, 200k) truncates stored
  edges with an explicit `UNRESOLVED_LIMIT_REACHED` diagnostic; counters and
  `truncated` flags remain honest.
- `GraphResponse.unresolved_count` sums unresolved + ambiguous references per
  the contract field description; the run's `diagnostics_summary` keeps them
  separate.

## API/schema/database changes

- **Contract (additive):** documented the already-implemented 409 conflict
  response on `GET /nodes/{node_id}` and `GET /nodes/{node_id}/neighbors`
  (409 was already listed for `/graph`). No schema shapes changed; no routes
  added or removed. **Heads-up for Sameeksha:** nothing to regenerate —
  `GraphResponse`/`GraphNode`/`GraphEdge` match the frozen schemas, and your
  graph UI's `ANALYSIS_NOT_READY` (409) mapping now matches the backend for
  all three endpoints.
- New table `dependency_edges` (migration `c3d9e2ab5c71`, down revision
  `b7f31c8e5a41`); `analysis_runs` gained `unresolved_reference_count` /
  `ambiguous_reference_count`. Stored per-symbol import JSON now includes a
  positional `bindings` array; old rows (without it) keep working.
- `AnalysisRun.edge_count` is now the real number of stored dependency edges
  (was always 0 before Phase 5A).

## Next smallest actionable task

Phase 6A start: impact API — BFS traversal over the stored dependency graph
with shortest-hop distances, direct vs indirect classification, representative
edge-valid paths, per-target attribution, and the versioned configurable risk
score (renormalized without coverage and reported as such).
