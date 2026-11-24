# FlowLens — Parallel Implementation Phases

**Purpose:** Coordinate two contributors building FlowLens in independent branches after one shared scaffold commit.  
**Owners:** Madvith (backend, GitHub integration, analysis engine) and Sameeksha (frontend, visualization, user experience).  
**Source of truth:** `product.md` defines product behavior; `scope.md` defines MVP boundaries and acceptance gates; this file defines execution order and integration checkpoints.

## 0. Rules for both AI agents

1. Read `product.md`, `scope.md`, `phases.md`, and your assigned `agent-*.md` before editing code.
2. Inspect the repository and current branch before making changes. Do not assume the repository is empty.
3. Work only on the assigned branch and ownership area. Do not commit directly to `main`.
4. Do not silently change shared API contracts. Raise a contract change with the other contributor and update backend + frontend types together.
5. Keep code runnable. Prefer small, tested vertical slices over a large amount of disconnected scaffolding.
6. Never execute or install dependencies from an analyzed repository. FlowLens analysis is static.
7. Do not fabricate graph edges, analysis results, progress, test suggestions, or successful operations.
8. Use mocked GitHub/API responses only in tests or clearly labeled local UI development. Production paths must call real backend services.
9. Record actual commands and test results. Never report tests as passing unless they ran and passed.
10. Update `IMPLEMENTATION_STATUS.md` at the end of each work session with completed work, changed files, tests run, issues, and next task.

## 1. Target branch strategy

### Shared initial commit

The first commit on `main` is a scaffold/contract commit only:

`chore: scaffold FlowLens repository and shared API contracts`

It establishes the folder layout, package/config placeholders, `.gitignore`, environment examples, minimal app shells, tests directories, docs, and a versioned shared API contract. It must not contain the AST engine, GitHub auth implementation, graph UI, real analysis services, or fake demo behavior.

### Feature branches

Create both branches from the same initial commit:

- Madvith: `feature/madvith-backend-core`
- Sameeksha: `feature/sameeksha-frontend-app`

### Ownership

- Madvith owns `backend/**`, database/migrations, backend tests, GitHub App setup docs, and authoritative `contracts/openapi.yaml` changes.
- Sameeksha owns `frontend/**`, frontend tests, and frontend-specific documentation.
- Both can read shared docs/contracts. Sameeksha must not independently edit the API contract.
- Root configuration, Docker Compose, shared CI, and README changes require coordination. Avoid modifying them from both branches.

### Merge order

1. Madvith completes backend endpoints, schemas, security checks, and backend tests; open a PR into `main`.
2. Review and merge `feature/madvith-backend-core` after its API contract and tests are stable.
3. Sameeksha rebases or merges the updated `main` into `feature/sameeksha-frontend-app`, resolves any generated type/API changes, and runs frontend checks.
4. Merge the frontend PR.
5. Run the integrated E2E suite on `main`, fix cross-layer issues, and tag the MVP only after the complete journey passes.

## 2. Phase 0 — Initial scaffold commit (Madvith prepares; Sameeksha reviews)

### Objectives
Create one clean, predictable monorepo scaffold and freeze the integration boundary before either feature branch begins. This is the only shared setup commit before the work splits.

### Madvith tasks
- Confirm the repository root and current branch; preserve existing work.
- Create the directory structure described in `scope.md`.
- Add minimal frontend and backend app entry points that start successfully.
- Add `backend/pyproject.toml`, `frontend/package.json`, lint/type/test scripts, and `.env.example` files.
- Add `.gitignore`, README setup outline, and Docker Compose baseline if the project will use it.
- Add `contracts/openapi.yaml` covering authentication, GitHub installation/repositories, project ingestion, analysis, graph, impact, diff, coverage, and report endpoints.
- Define standard API error format, pagination shape, IDs, analysis states, graph node/edge shape, impact response, and auth/session response.
- Add `docs/architecture.md` and `docs/github-app-setup.md` outlines.
- Create empty tests/fixture folders; do not add fake test results or fake business functionality.
- Make the single scaffold commit on `main` with message `chore: scaffold FlowLens repository and shared API contracts`.

### Sameeksha review tasks (before the feature branches are created)
- Review the proposed frontend structure and confirm it supports the agreed screen/feature layout.
- Review the OpenAPI contract from the frontend consumer's perspective; identify missing fields or routes before it is frozen.
- Confirm the frontend install/start/type-check commands work. Do not begin product feature implementation on `main`.

### Deliverable
One structure-only commit on `main` with both frontend/backend bootstraps and a usable shared API contract.

### Exit gate
Both apps can start in minimal mode, health checks work, dependencies install from documented commands, and both contributors agree that the API contract is stable enough to branch. Only after this gate are the two feature branches created.

## 3. Phase 1 — Branch creation and contract freeze

### Tasks
- Create Madvith and Sameeksha branches from the same scaffold commit.
- Madvith confirms backend API routes, models, auth semantics, and source provider schema against the OpenAPI contract.
- Sameeksha generates TypeScript API types from the OpenAPI contract and creates an API client wrapper.
- Any missing field/route is discussed before implementation diverges.
- Add `IMPLEMENTATION_STATUS.md` with phase, ownership, and current test commands.

### Exit gate
Both branches build independently and use the same agreed API schema. No one is implementing against undocumented payload guesses.

## 4. Phase 2A — Madvith: backend foundation and account/session layer

### Objectives
Build the backend base and secure user identity/session model.

### Tasks
- Set up FastAPI application, typed settings, logging, request IDs, centralized exception handlers, and health/readiness endpoints.
- Set up SQLAlchemy models, Alembic migrations, database session management, and repository/service layering.
- Add user, session/token credential, GitHub installation, project, source snapshot, analysis, graph, and report persistence models as needed.
- Implement GitHub App user authorization start/callback.
- Validate one-time OAuth `state`; exchange the authorization code only on the backend.
- Fetch the authenticated GitHub user profile and upsert FlowLens user by GitHub numeric ID.
- Store GitHub access/refresh tokens encrypted at rest; do not log them or return them to the client.
- Implement secure `HttpOnly` application session cookie, session expiry, logout, and current-user endpoint.
- Add CSRF protection/Origin validation for state-changing cookie-authenticated requests and strict CORS settings.
- Add mocked-provider tests for valid callback, invalid/replayed state, token exchange failure, expired session, logout, and revoked authorization behavior.

### Deliverables
Working GitHub sign-in/session backend and migrated database schema.

### Exit gate
A configured local GitHub App can complete sign-in. The frontend receives only app session state, never a GitHub token. Authentication tests pass.

## 5. Phase 2B — Sameeksha: frontend foundation and authentication UX

### Objectives
Build the application shell and login/session experience against the frozen API contract.

### Tasks
- Set up Next.js/React + TypeScript app structure, Tailwind, shadcn/ui, fonts/theme, layouts, and responsive shell.
- Build shared components: navigation, buttons, dialogs, cards, forms, loading states, toast/alert patterns, empty states, and error states.
- Build login page with Continue with GitHub action that redirects to the backend `/auth/github/start` endpoint.
- Implement authenticated route handling based on `/auth/me` and cookie sessions.
- Implement logout and session-expired handling.
- Configure API client with base URL, `credentials: include`, typed request/response models, and central error handling.
- Use MSW or local fixtures only for isolated frontend development/tests; no mock analysis results in the normal product flow.
- Add component and route tests for unauthenticated, authenticated, loading, and error states.

### Deliverables
Runnable frontend shell, login/logout UX, session-aware routing, and typed API client.

### Exit gate
The frontend can complete the real backend sign-in redirect when the endpoint is available, or run its UI tests using mocks. It contains no GitHub client secret/token.

## 6. Phase 3A — Madvith: GitHub App installation and repository connection

### Objectives
Let authenticated users install FlowLens and import repositories they are authorized to access.

### Tasks
- Implement the GitHub App installation redirect and callback.
- Validate installation callback data and verify installation ownership/access through GitHub APIs; do not trust browser-provided installation IDs.
- List installations and repositories with pagination using the supported user/installation APIs.
- Request/assume only read-only `Contents` and `Metadata` permissions for the MVP.
- Generate short-lived installation access tokens server-side and restrict a token to the selected repository where supported.
- Implement repository/ref validation and server-side source retrieval from GitHub API/archive endpoints.
- Allow only documented GitHub API/archive hosts and validate redirects; prevent arbitrary URL fetching/SSRF.
- Avoid shelling out to `git clone` or executing Git hooks.
- Persist repository connection, owner/repo identifiers, default branch, visibility, selected ref, resolved commit SHA, and source provenance.
- Implement project refresh that creates a new immutable snapshot.
- Implement disconnect that removes future access but keeps existing snapshots/reports.
- Handle permission denial, removed installation, revoked authorization, missing repository, invalid ref, rate limits, API errors, and archive failures.
- Add mocked GitHub API tests for pagination, allowed/denied repos, token expiry, and source retrieval.

### Deliverables
GitHub App installation management, repository picker APIs, GitHub source ingestion, refresh/disconnect behavior.

### Exit gate
An authorized public/private repository can be imported to an immutable snapshot. An unselected or inaccessible repository is denied. No GitHub token is returned to the frontend.

## 7. Phase 3B — Sameeksha: project dashboard and source creation UX

### Objectives
Create the complete user workflow for starting projects from ZIP or GitHub.

### Tasks
- Build authenticated project dashboard with recent projects, provider badges, repository/ref metadata, latest snapshot, and analysis status.
- Build source chooser: Upload ZIP or Connect GitHub.
- Build GitHub installation/account selector, install FlowLens prompt, repository list with search/pagination, and branch/ref selection.
- Build ZIP upload with validation feedback, progress, and retry/error UI.
- Build project creation confirmation and redirect into project workspace.
- Build project detail/settings area showing source provenance and repository disconnect/refresh actions.
- Use only API contract response fields; do not infer access from a repository's visibility label.
- Add tests for empty dashboard, upload errors, no installation, no repositories, pagination, repository selection, and permission failures.

### Deliverables
Complete project creation and source selection UI for both providers.

### Exit gate
A logged-in user can create a project from ZIP or GitHub using real APIs; expected empty and failure states are visible and actionable.

## 8. Phase 4A — Madvith: secure ZIP ingestion and AST analysis

### Objectives
Create the parser and symbol catalogue for every immutable source snapshot.

### Tasks
- Implement safe ZIP inspection/extraction, compressed/uncompressed size limits, file count, per-file size, path normalization, traversal rejection, and exclusions.
- Treat all repository content as untrusted. Never import, execute, or install it.
- Parse Python files using `ast.parse`; continue when individual files have syntax errors.
- Extract modules, classes, functions, async functions, methods, nested definitions, decorators, bases, imports, and call expressions.
- Capture stable symbol IDs, qualified names, lexical parent, file path, line/column spans, and diagnostics.
- Store source file metadata and symbol records tied to snapshot/analysis versions.
- Expose project, snapshot, analysis creation/status, diagnostics, symbol search, and pagination APIs.
- Add parser and archive fixtures, including malicious archives and malformed source files.

### Deliverables
Safe source ingestion and a searchable symbol catalogue for GitHub and ZIP snapshots.

### Exit gate
Both source providers produce the same internal snapshot representation. Parser fixtures pass and unsafe archives are rejected.

## 9. Phase 4B — Sameeksha: analysis status, symbols and project workspace shell

### Objectives
Connect the UI to project/snapshot/analysis lifecycle.

### Tasks
- Build project workspace layout with project metadata, selected snapshot/ref/commit, analysis state, and diagnostics summary.
- Implement start-analysis action and status refresh/polling using actual API responses.
- Build symbol search/list panel and symbol detail view using qualified names and source locations.
- Display warnings, syntax errors, skipped files, and partial-analysis states.
- Add loading, no-Python-files, analysis-failed, completed-with-warnings, and retry states.
- Keep navigation and source metadata consistent when switching snapshots.

### Deliverables
Project analysis workspace shell connected to real analysis APIs.

### Exit gate
A user can start analysis and find symbols from a completed snapshot; failure and partial states are handled.

## 10. Phase 5A — Madvith: resolution, graph construction and graph APIs

### Objectives
Construct defensible typed dependency edges and efficient graph query APIs.

### Tasks
- Define a resolver interface independent of AST extraction.
- Resolve lexical local calls, imports, aliases, relative imports, module-qualified calls, and common class/method references where supported.
- Add optional Jedi adapter only where tested; LibCST is a source/CST utility, not a semantic resolver.
- Emit edge type, source/target IDs, source evidence, resolver name, and confidence.
- Record unresolved and ambiguous calls explicitly in diagnostics.
- Build per-analysis NetworkX graph with typed nodes/edges; keep `CONTAINS` separate from dependency edges.
- Calculate in-degree, out-degree, reachable counts, and normalized graph metrics.
- Expose filtered graph, node detail, neighbor expansion, graph summary, and path APIs with result/depth limits.
- Ensure stable sorting, deterministic IDs, cycle-safe logic, and graph schema versioning.
- Add test fixtures for aliases, circular imports, inheritance, method calls, unresolved dynamic calls, and duplicate symbol names.

### Deliverables
Dependency resolver, graph store/service, graph query APIs, metrics and diagnostics.

### Exit gate
Every returned dependency edge has source evidence. API results are deterministic and bounded. Unresolved calls are never silently guessed.

## 11. Phase 5B — Sameeksha: interactive dependency graph

### Objectives
Visualize real graph API results and support efficient exploration.

### Tasks
- Integrate Cytoscape.js as the sole MVP graph renderer.
- Build file/module, class, and function/method view controls using graph filters/grouping.
- Add zoom, pan, fit/reset, node selection, edge selection, search, node/edge filters, neighborhood expansion, and depth controls.
- Build selected-node details panel: qualified name, type, source location, metrics, callers/callees, edge evidence, and confidence.
- Add legend and clear direct/indirect/unresolved visual states.
- Add accessible list/table view for graph data.
- Add graph loading, no-results, too-large-to-render, partial graph, and API error states.
- Use server-side graph filters/neighbor queries rather than requesting unlimited project graphs.

### Deliverables
Interactive graph workspace driven by the actual graph APIs.

### Exit gate
A user can search/select a symbol, inspect its relationships, navigate graph levels, and use a list alternative. Large graph interactions remain bounded.

## 12. Phase 6A — Madvith: impact analysis and risk scoring

### Objectives
Calculate upstream/downstream impact with explainable outputs.

### Tasks
- Implement BFS traversal and shortest-hop distances with visited-set cycle protection.
- Separate upstream callers and downstream dependencies; make traversal edge types configurable and documented.
- Calculate direct vs indirect impacted nodes, hop distance, representative paths, and per-target attribution.
- Support one or multiple selected target symbols and maximum traversal depth.
- Add risk score 0–100 with versioned configurable factors: normalized upstream reachable dependents, in-degree/centrality, downstream breadth, public/entry-point indicator, and coverage deficiency when available.
- Renormalize weights when coverage is unavailable and report that coverage was not included.
- Expose factor breakdown and caveats. Do not call it a failure probability.
- Add tests for direction, direct/indirect, cycles, path validity, max depth, multi-target deduplication, and deterministic scoring.

### Deliverables
Impact API and explainable risk score.

### Exit gate
Impact response is reproducible and every path is a valid sequence of graph edges. Tests cover cycles and depth constraints.

## 13. Phase 6B — Sameeksha: impact visualization

### Objectives
Present impact results clearly and link them to graph selection.

### Tasks
- Build impact panel with target symbol(s), upstream/downstream/both direction, and depth controls.
- Render direct and indirect impact distinctly in the graph.
- Display affected node lists, hop distances, risk score, factor breakdown, and warnings.
- Allow selecting an impacted node to inspect the path from/to target.
- Display representative call/dependency chains and unresolved relationship warnings.
- Include empty/no-impact and low-confidence states.
- Avoid color-only encoding; provide labels/icons and accessible table view.

### Deliverables
Interactive impact simulation experience connected to the impact API.

### Exit gate
Changing target/direction/depth updates UI from real impact results. A user can inspect paths and score factors.

## 14. Phase 7A — Madvith: diff, coverage and report services

### Objectives
Complete change review and export capability.

### Tasks
- Parse unified diff headers/hunks and map changed lines to source symbol ranges.
- Mark added, modified, deleted, and unmapped changes; support multiple files/hunks.
- Calculate combined impact for mapped targets and retain per-target attribution.
- Parse documented Coverage.py JSON format with strict schema/path validation.
- Map executable/covered lines to symbol spans; distinguish covered, partial, uncovered, unknown.
- Implement conservative test-to-symbol mapping; report unknown rather than guessing.
- Generate Markdown report from structured result data with safe escaping and deterministic ordering.
- Include snapshot/provider/commit metadata, targets, impact nodes, paths, risk factors, coverage, diagnostics, exclusions, and caveats.
- Expose diff, coverage, report generation, and download APIs with ownership checks.
- Add tests for diff ranges, deleted files, module-level changes, path mismatches, malformed coverage, escaping, and report consistency.

### Deliverables
Diff/coverage/report backend features.

### Exit gate
Diff maps source changes accurately where possible, missing coverage remains unknown, and Markdown report matches stored analysis/impact data.

## 15. Phase 7B — Sameeksha: diff, coverage and report UI

### Objectives
Complete the review workflow and expose exported analysis results.

### Tasks
- Build diff paste/upload interface and changed file/symbol summary.
- Show mapped and unmapped changes and combined impact result.
- Add coverage status overlay and legend in graph/details/impact views.
- Build report generation action, Markdown preview, and download.
- Display report metadata, diagnostics, and limitations.
- Handle missing coverage, empty diff, unsupported diff, report generation errors, and download failures.
- Add frontend tests for diff, coverage states, report preview, and download.

### Deliverables
Diff review, coverage overlay, and report UI.

### Exit gate
All actions use real backend endpoints and provide correct status/error states. Export action downloads the generated Markdown report.

## 16. Phase 8 — Parallel stabilization and security hardening

### Madvith tasks
- Review authentication state/CSRF/session security, token encryption, token refresh/revocation, GitHub installation access, repository scoping, SSRF/redirect allowlist, source path validation, and user ownership checks.
- Profile ingestion/parser/resolver/graph/impact/report services.
- Add bounded timeouts, upload limits, analysis cancellation/cleanup where practical, and stable diagnostics.
- Review database indexes, transaction boundaries, token redaction, and snapshot retention.
- Ensure no credentials or server absolute paths appear in API responses/logs.

### Sameeksha tasks
- Review accessibility, keyboard navigation, focus handling, contrast, responsive layouts, graph fallback list, and error/empty states.
- Profile graph rendering with representative repository fixture data.
- Verify auth callback/redirect behavior, session expiry, logout, installation-required, and permission-denied states.
- Remove development-only mocked data from production paths.

### Shared exit gate
All security and performance requirements in `scope.md` are covered by tests or documented manual checks. No critical known issue remains.

## 17. Phase 9 — Merge and end-to-end integration

### Merge sequence
1. Madvith opens backend PR with API contract, migrations, auth/GitHub integration, services, and backend tests.
2. Review and merge backend PR into `main`.
3. Sameeksha rebases/merges latest `main` into the frontend branch and regenerates types if the contract changed.
4. Run frontend lint/type/test/production build; open frontend PR.
5. Review and merge frontend PR.
6. Run full end-to-end tests on integrated `main`.

### Integration tasks
- Validate browser cookie/session behavior across configured origins.
- Validate CORS, credentials, CSRF, and redirect URLs.
- Test login → install app → list repositories → import private repo → analyze → graph → impact → report.
- Test login → ZIP upload → analyze → graph → diff → coverage → report.
- Verify project isolation across two different test users.
- Resolve real integration defects without changing contract silently.

### Exit gate
Both primary source workflows pass end to end in a clean environment. No mock result is shown as a real analysis.

## 18. Phase 10 — Release preparation

### Tasks
- Verify fresh setup using README instructions.
- Complete `docs/github-app-setup.md` with app registration settings, callback URLs, installation URL, permissions, secrets, and local testing steps.
- Verify `.env.example` contains names and explanations but no secrets.
- Include a synthetic Python project and sample Markdown report.
- Run all backend unit/integration tests, frontend tests, lint, type checks, and production builds.
- Verify database migrations and source/report storage paths.
- Update `IMPLEMENTATION_STATUS.md` with implemented/partial/not implemented features and verified test output.
- Tag/release only after every applicable `scope.md` gate passes.

### Final deliverables
- Working FlowLens application.
- Reproducible setup and GitHub App configuration guide.
- Passing test/build results.
- Sample project/report and known limitations.

## 19. Recommended technical contracts

### API error envelope
Use one consistent shape, for example:

```json
{
  "error": {
    "code": "REPOSITORY_ACCESS_DENIED",
    "message": "FlowLens does not have access to this repository.",
    "details": {},
    "request_id": "..."
  }
}
```

Never return exception stack traces, secrets, or internal absolute paths.

### Authentication/session response
`GET /api/v1/auth/me` should return a minimal current-user object and authentication status. It must not return GitHub access or refresh tokens.

### Graph node
- `id`: stable ID within analysis.
- `kind`: module, class, function, or method.
- `name`, `qualified_name`, `file_path`.
- `start_line`, `end_line`, `start_column`, `end_column`.
- `parent_id`, metrics, coverage status, and bounded metadata when available.

### Graph edge
- `id`, `source`, `target`, `kind`.
- `confidence` and evidence locations.
- `resolver` and diagnostics where applicable.

### Impact result
- `target_ids`, `direction`, impacted nodes with direct/indirect status and hop distance.
- Representative edge-valid paths.
- Risk score, version, normalized factors, and whether coverage was included.
- Warnings and coverage summary.

## 20. Suggested risk-score starting point

Use a versioned heuristic, initially configurable around:

- 35% normalized upstream reachable dependents.
- 20% normalized in-degree/centrality.
- 15% downstream dependency breadth.
- 15% public API/entry-point indicator.
- 15% coverage deficiency, only when coverage is present.

When coverage is absent, renormalize the available weights and mark the score as computed without coverage. Document the normalization method and avoid false precision.

## 21. End-of-session handoff format

Each agent updates `IMPLEMENTATION_STATUS.md` with:

- Current branch and phase.
- Tasks completed.
- Files/modules added or changed.
- Exact commands executed and actual outcomes.
- Known issues, blockers, and assumptions.
- API/schema/database changes, if any.
- Next smallest actionable task.

At final handoff, clearly separate implemented, partially implemented, and not implemented requirements. Never claim unverified behavior.
