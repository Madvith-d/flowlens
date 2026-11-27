# FlowLens — Implementation Status

**Contributor:** Madvith (backend, GitHub integration, analysis engine)
**Current branch:** `madvith-phase8` (backend workstream, cut from `main`
`4dc8503` after the Phase 7A/7B merges)
**Phase:** 8 complete (stabilization and security hardening — backend side)

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


## Phase 7A — Diff, coverage and report services — done

- `app/services/analysis/diffmap.py`: unified diff parser (git-style headers
  or `---`/`+++` pairs, multiple files/hunks, added/deleted files) mapping
  changed lines (new- and old-side) onto stored symbol spans. Per-symbol
  classification added/modified/deleted; module symbols are deliberately not
  mapping targets so module-level changes are reported unmapped with an
  explicit reason; paths missing from the snapshot stay unmapped with a
  warning. Combined impact inherits the impact service (per-target
  attribution, deduplication, risk) with the mapped symbols capped to the
  10-target contract bound.
- `app/services/analysis/coverage.py`: strict Coverage.py JSON schema
  validation, conservative path normalization (exact, `a/`/`b/`/`./` prefixes,
  unique suffix match only) and per-symbol covered/partially_covered/
  uncovered/unknown classification. Missing coverage is `unknown`, never
  zero. Re-attachment replaces the previous mapping atomically.
- `coverage_files` / `symbol_coverage` tables (migration `e5b8f2a07c31`).
- `app/services/analysis/reports.py` + `ReportStorage`: deterministic
  Markdown reports generated from stored analysis/impact/coverage data with
  table-cell escaping (pipes/backslashes/newlines), deterministic ordering,
  metadata (project, provider, snapshot ref/commit, versions, direction,
  depth), targets, impacted nodes, risk factors and caveats, coverage
  section (summary + per-symbol rows, or explicit no-artifact state),
  diagnostics summary, exclusions/caveats. Same inputs produce
  byte-identical reports.
- Impact integration: `coverage_summary` is populated once coverage is
  attached; the risk `coverage_deficiency` factor (weight 0.15) activates,
  counting targets that are not fully covered (unknown stays deficient and is
  disclosed in a warning). Graph nodes expose real `coverage_status` (from
  `unknown` by default).
- New endpoints (frozen contract): `POST /analyses/{id}/diff` (422
  `DIFF_INVALID`), `POST /analyses/{id}/coverage` (400 `COVERAGE_INVALID`),
  `POST /analyses/{id}/reports` (201 `ReportInfo`),
  `GET /reports/{id}/download` (`text/markdown`, attachment filename). All
  enforce analysis ownership + completion; every existing test still passes.

## Next smallest actionable task

Phase 9 (merge + end-to-end integration): open the backend PR, then run the
integrated E2E journeys with Sameeksha on `main`.


## Phase 8 — Stabilization and security hardening (backend) — done

### Security audit results (reviewed, no defects found in these areas)

- Auth/session: one-time OAuth state (atomic conditional UPDATE), signed
  `HttpOnly` session cookie with server-side state, Origin validation on all
  unsafe methods, Fernet encryption at rest for access/refresh tokens,
  `secrets.compare_digest` signature checks. Existing tests already cover
  replayed/expired state, tampered cookies, revocation, and token leakage
  (`test_no_token_in_responses_or_cookies`).
- GitHub installation access: browser-supplied installation IDs are never
  trusted; every use re-verifies against the live user installation list.
  Installation tokens stay in memory only, are never persisted or returned.
- SSRF: API calls restricted to the configured API host with manually
  followed, allowlist-checked redirects (bounded); archive downloads were
  hardened this phase (below).
- Ownership: every project/snapshot/analysis/report route resolves ownership
  in the service layer and collapses "not yours" into "not found".
- Ingestion: ZIP/tar validation (traversal, symlinks, encrypted entries,
  duplicate names, count/size/ratio limits) was already complete and tested.

### Defects found and fixed

1. **Archive download redirects were dead code** — `download_archive` raised
   `ARCHIVE_DOWNLOAD_FAILED` for *every* redirect, even allowlisted ones,
   contradicting the documented behavior. Now follows redirects with the same
   bounded, allowlist-checked loop as API calls (`MAX_REDIRECT_HOPS`).
2. **User-supplied refs were interpolated into URLs unencoded** —
   `resolve_ref`/`download_archive` only replaced spaces, so `?`/`#` could
   alter the request URL and a `..` ref could walk the path to a different
   authenticated API endpoint. Refs are now validated (no `..`, no control
   chars, non-empty) and percent-encoded; `owner/repo` names are
   shape-checked before use.
3. **Expired credentials were used until GitHub rejected them** — the stored
   refresh token was never used. Added `refresh_token` to the provider
   interface (`grant_type=refresh_token`), and `active_access_token`
   (`services/auth/service.py`): expired access tokens are refreshed
   transparently and the rotated pair is re-encrypted and persisted; a failed
   refresh raises the stable 401 `GITHUB_TOKEN_ERROR` envelope.
4. **Unexpected analysis errors had no containment** — an exception mid-run
   aborted the request (500) and rolled the run row away. `_execute` now
   catches unexpected exceptions, records an `INTERNAL_ERROR` diagnostic, and
   finishes the run as `failed` with that stable error code.
5. **No retention for expired auth rows** — `oauth_states` and
   `user_sessions` grew without bound. Both repositories now purge rows
   expired beyond a 24 h grace window when new rows are created, backed by
   new `expires_at` indexes (migration `f7a3b9c1d204`).

### Additions

- Wall-clock analysis budget `ANALYSIS_MAX_WALL_SECONDS` (default 120 s):
  parsing stops with an explicit `ANALYSIS_TIME_BUDGET_EXCEEDED` diagnostic
  and the run finishes `completed_with_warnings` — results are never silently
  partial.
- `X-Content-Type-Options: nosniff` on every response.
- `.env.example`: documented that callback URLs derive from
  `BACKEND_PUBLIC_URL` (the previously listed `GITHUB_OAUTH_CALLBACK_URL`
  variable was never read); added `ANALYSIS_MAX_WALL_SECONDS`.
- `docs/architecture.md`: new "Phase 8 hardening notes" section.

### Profiling (synthetic 151-file / 1,801-symbol / 4,048-edge corpus, in-memory SQLite, mocked GitHub)

| Stage | Wall time |
|---|---|
| Upload + ZIP extraction (44 KiB zip) | ~28 ms |
| Analysis (parse + resolve + persist) | ~576–850 ms |
| Symbol search | ~7 ms |
| Graph API (filtered) | ~71 ms |
| Neighbor expansion | ~34 ms |
| Impact (hub symbol, 500-node cap hit, `truncated=true`) | ~95–170 ms |
| Report generation | ~52 ms |
| Report download | ~6 ms |

Analysis is the dominant cost and stays well inside the new wall-clock
budget; all query APIs are far below any latency concern. The impact/risk
path hit the configured `IMPACT_MAX_IMPACTED_NODES` bound correctly and
reported `truncated: true`.

### Files changed (Phase 8)

- `app/services/github/app_client.py` (redirect handling, URL hardening)
- `app/services/github/client.py` (provider `refresh_token`)
- `app/services/auth/service.py` (`active_access_token`)
- `app/services/github/service.py`, `app/services/projects/service.py`
  (refresh-aware token resolution; provider injection)
- `app/api/deps.py` (provider wiring for both bundles)
- `app/services/analysis/service.py` (failure containment, time budget)
- `app/core/config.py` (`analysis_max_wall_seconds`, docstring fix)
- `app/core/middleware.py` (nosniff header)
- `app/models/auth.py`, `app/repositories/auth.py` (retention + indexes)
- `alembic/versions/f7a3b9c1d204_phase8_expiry_indexes.py` (new migration)
- `.env.example`, `docs/architecture.md`, `IMPLEMENTATION_STATUS.md`
- Tests: `tests/unit/test_github_app_client.py` (+6),
  `tests/unit/test_oauth_state.py` (+2),
  `tests/integration/test_analysis_hardening.py` (new, 4),
  `tests/integration/test_token_refresh.py` (new, 3),
  `tests/conftest.py` (mock refresh support)

### Contract changes

None. No route, schema, or error-code changes; the new diagnostics are stored
rows only (the `diagnostics_summary` contract shape is unchanged).

## Exact commands executed and actual results (Phase 8)

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **227 passed** (212 pre-existing + 15 new), 1 starlette deprecation warning |
| `.venv/bin/python -m compileall -q app tests alembic/versions` | clean |
| `DATABASE_URL=sqlite:////tmp/fl_migrate_test.db .venv/bin/alembic upgrade head` | all 6 migrations applied cleanly on a fresh DB |
| `... alembic downgrade -1 && ... upgrade head` | new migration downgrades and re-upgrades cleanly; both indexes present |
| profiling scripts (scratchpad, mocked GitHub) | timings table above |

No lint/type-check tooling is configured for the backend (plain `pytest` +
`compileall` are the project's checks; `pyproject.toml` defines no ruff/mypy
config).

## Known issues, blockers, assumptions (Phase 8)

- Token refresh is verified against the mocked provider only; it follows
  GitHub's documented `grant_type=refresh_token` endpoint but has not been
  exercised against a real GitHub App (same caveat as all GitHub integration
  in this repo — mocked-provider tests only).
- Analysis remains synchronous in-request (documented MVP simplification);
  cancellation is therefore not applicable — the wall-clock budget bounds
  runtime instead. A worker-based runner can replace `_execute` without
  contract changes.
- Manual smoke test with a real development GitHub App remains outstanding
  (tracked since Phase 3A; requires real app credentials).


