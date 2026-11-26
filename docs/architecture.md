# FlowLens Architecture

**Status:** outline — completed on `feature/madvith-backend-core` (backend sections)
and `feature/sameeksha-frontend-app` (frontend sections).

## Overview

FlowLens is a two-tier application:

- **Backend** (`backend/`): FastAPI service providing authentication, GitHub App
  integration, source ingestion, static AST analysis, dependency resolution,
  graph construction, impact analysis, diff/coverage mapping and Markdown
  report generation.
- **Frontend** (`frontend/`): Next.js + React + TypeScript application consuming
  the versioned API in `contracts/openapi.yaml`.

The shared integration boundary is the OpenAPI contract. All cross-team payload
changes must be made there first, coordinated between contributors.

## Backend layers (owner: Madvith)

- `app/api/` — HTTP routes, request/response schemas, error envelope.
- `app/core/` — typed settings, logging, request IDs, security helpers.
- `app/db/` — SQLAlchemy session management and Alembic migrations.
- `app/models/` — ORM models: User, GitHubCredential, GitHubInstallation,
  GitHubRepositoryConnection, Project, SourceSnapshot, AnalysisRun, Symbol,
  DependencyEdge, Report.
- `app/repositories/` — data access with ownership checks.
- `app/services/` — domain services:
  - `auth/` — GitHub App user authorization, sessions, CSRF.
  - `github/` — installations, repository access verification, source fetch.
  - `ingestion/` — safe ZIP extraction and snapshot creation.
  - `analysis/` — AST parsing and symbol catalog.
  - `resolution/` — name/cross-file resolution (AST resolver, optional Jedi adapter).
  - `graph/` — NetworkX graph storage and query APIs.
  - `impact/` — BFS upstream/downstream traversal and risk scoring.
  - `diff/` — unified diff parsing and changed-symbol mapping.
  - `coverage/` — Coverage.py JSON mapping.
  - `reports/` — deterministic Markdown report generation.

## Frontend structure (owner: Sameeksha)

- `src/app/` — Next.js App Router pages/layouts.
- `src/components/` — shared UI components.
- `src/features/` — feature modules (auth, projects, github, graph, impact,
  diff, coverage, reports).
- `src/lib/` — API client, utilities.
- `src/types/` — TypeScript types generated from `contracts/openapi.yaml`.

## Data flow

1. User signs in with GitHub (GitHub App user authorization, backend code exchange).
2. Project creation from a verified GitHub repository or a validated ZIP upload
   produces an immutable source snapshot.
3. An analysis run parses and resolves the snapshot, producing symbols and typed
   dependency edges with evidence and confidence.
4. Graph APIs serve bounded, filtered subgraphs; impact APIs compute
   upstream/downstream effects with explainable risk scoring.
5. Diff/coverage data can be attached to an analysis; reports export the
   results as Markdown.

## Ingestion and static analysis (implemented: Phases 3A + 4A)

- **Snapshots are provider-agnostic.** GitHub imports (`services/github`) and ZIP
  uploads (`services/ingestion/zip_archive.py`) both produce the same internal
  representation: an immutable `SourceSnapshot` row plus a snapshot directory
  under `STORAGE_ROOT/snapshots/{snapshot_id}/`. Analysis code never branches on
  the provider.
- **Extraction is bounded and safe.** Archive entries are normalized and
  validated (no absolute paths, no `..`, no links, no duplicates), then written
  with file-count, per-file, total-uncompressed, and compression-ratio limits.
  Excluded directories (`.git`, `__pycache__`, virtualenvs, …) are skipped and
  reported. Uploaded/GitHub source is never imported, executed, or installed.
- **Analysis is per-run and immutable.** `POST /snapshots/{id}/analyses` creates
  an `AnalysisRun` (`queued` → `running` → `completed` /
  `completed_with_warnings` / `failed`) and parses every `*.py` file with the
  standard library `ast` module: modules, classes (bases), functions, async
  functions, methods, nested definitions, decorators, imports, and call
  expressions, each with file-relative line/column spans.
- **Symbols are deterministic within a run.** IDs hash the structural key
  (analysis, file, kind, qualified name, span), qualified names use
  `module:Class.method` / `module:function` / `module:function.nested`, and
  catalogue queries are deterministically ordered by
  `(file_path, start_line, start_column, qualified_name)`.
- **Diagnostics, not guesses.** Syntax errors, encoding errors, oversized files,
  and the symbol budget are recorded as diagnostics per file; a broken file never
  stops the rest of the snapshot from being analysed. Call expressions are stored
  as expressions only — resolution (with evidence and confidence) is Phase 5A.

## Resolution and dependency graph (implemented: Phase 5A)

- **Resolution happens after extraction, on stored records.** The resolver
  (`services/analysis/resolver.py`) consumes plain symbol/call/import records —
  not ASTs and not ORM rows — so any future extraction pipeline can reuse it
  (`DependencyResolver` protocol). It resolves lexical module-local calls,
  imports and aliases (`import x as y`, `from m import n as z`, relative
  imports), module-qualified calls, `self.method()` against the lexical class,
  inherited methods through resolvable bases, unsuffixed class-method calls,
  and class bases (INHERITS). External imports (stdlib/third-party) are out of
  scope: they produce no edge and no diagnostic.
- **Every edge is typed, evidenced, and deduplicated.** Edges are unique per
  `(source, target, kind)` with a stable ID; each stores the producing resolver
  name, the most conservative contributing confidence, and bounded evidence
  locations (file, line, column, expression). Ambiguous references (duplicate
  symbol names) and unresolved references (dynamic calls, unknown receivers)
  are recorded as diagnostics with exact occurrence counters on the run —
  nothing is ever silently guessed.
- **`CONTAINS` is structural, never a dependency.** It is derived from
  `Symbol.parent_id` at graph-build time and excluded from traversals and
  metrics; `dependency_edges` stores only CALLS / IMPORTS / INHERITS /
  REFERENCES.
- **Graph queries are bounded and deterministic.** `services/analysis/graph.py`
  builds a per-analysis NetworkX graph and serves three views (`module`,
  `class`, `function` collapse, each documented in the service), node-kind and
  edge-kind filters, node limits with explicit `truncated`, node detail with
  in/out-degree and reachable counts, and depth/direction-limited neighborhood
  expansion. Reachability is computed via SCC condensation over the dependency
  graph (cycle-safe) and only while the graph is within the configured metrics
  budget (`GRAPH_METRICS_MAX_NODES`); beyond it, degrees are still served and
  reachability is omitted rather than estimated. Graph endpoints answer 409
  `ANALYSIS_NOT_READY` until the analysis completes.

## Impact and risk scoring (implemented: Phase 6A)

- **Impact is BFS with shortest-hop distances and cycle protection**
  (`services/analysis/impact.py`). `POST /analyses/{id}/impact` traverses
  only stored dependency edges (never `CONTAINS`) from one or more targets
  (1–10, deduplicated), in `upstream` (callers/dependents), `downstream`
  (dependencies), or `both` directions, bounded by `max_depth` (1–10).
  Impacted nodes are classified direct (hop distance 1) vs transitive, carry
  per-target attribution, an exact `min_hops`, and representative shortest
  paths — ordered sequences of the same edge IDs the graph API exposes, so
  clients can correlate them. Beyond `IMPACT_MAX_IMPACTED_NODES` the list is
  truncated, flagged, and warned about.
- **The risk score is a versioned, explainable prioritization heuristic**
  (`services/analysis/risk.py`) — explicitly not a failure probability, per
  the contract. Configurable weights (default 35/20/15/15/15) cover normalized
  upstream reachable dependents, in-degree centrality, downstream breadth, a
  structural public/entry-point indicator, and coverage deficiency; with no
  coverage attached (until Phase 7A) the coverage factor is excluded, the
  remaining weights are renormalized, and the fact is disclosed via
  `coverage_included: false` plus caveats. Every factor reports its raw value,
  normalized value, and applied weight; unresolvable reachability (metrics
  budget exceeded) removes factors rather than estimating them.

## Security invariants

- Analyzed source is never executed or imported.
- GitHub credentials stay server-side, encrypted at rest.
- Origin/CSRF validation for cookie-authenticated state-changing requests.
- Strict CORS origins; SSRF allowlist for GitHub API/archive hosts.
- Per-user ownership checks on every project/snapshot/analysis/report resource.
- No server paths, secrets, or stack traces in API responses.
