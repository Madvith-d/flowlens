# FlowLens — Scope and Acceptance Criteria

**Purpose:** Define the MVP boundary, ownership and security constraints, and measurable acceptance criteria.  
**Authority:** `product.md` describes expected product behavior. This file defines what must ship in the MVP and how completion is verified. `phases.md` defines implementation order and branch workflow.

## 1. Release definition

The MVP is a working Python code dependency and change-impact application with GitHub sign-in, GitHub App repository connection, ZIP upload, static analysis, interactive dependency graph, impact simulation, unified-diff mapping, optional Coverage.py overlay, and Markdown reports.

The user must be able to complete the main journey without manually modifying the database or calling undocumented endpoints:

**GitHub sign-in → connect/select repository or upload ZIP → analyze → explore graph → simulate impact → export report.**

## 2. In scope for MVP

### 2.1 Authentication and account ownership
- GitHub App-based user authorization / sign-in.
- Backend authorization-code exchange and account lookup by stable GitHub user ID.
- Secure server-side application session and logout.
- Expired/revoked token and session error handling.
- Basic user ownership isolation for projects, snapshots, analyses, and reports.
- No password-based authentication is required.

### 2.2 GitHub App and repository connection
- GitHub App installation flow for personal accounts and organizations where the user has sufficient permissions.
- Read-only repository permissions: Contents and Metadata.
- List installations and available repositories with pagination.
- Select a repository and branch/tag/commit ref.
- Verify repository/installation access on the backend.
- Fetch source through the GitHub API/archive endpoint using a short-lived, server-side installation token scoped to the selected repository.
- Create a project and immutable source snapshot with repository ID, owner/name, ref, resolved commit SHA, and timestamp.
- Refresh a connected project into a new immutable source snapshot.
- Disconnect a repository without deleting prior snapshots or reports.
- Support github.com only. GitHub Enterprise Server is excluded.

### 2.3 Local ZIP ingestion
- Create projects and upload ZIP archives.
- Validate archive type and enforce compressed/uncompressed size, file-count, and per-file limits.
- Reject traversal paths, absolute paths, and extraction escapes.
- Apply default exclusions and report ignored files.
- Store a safe immutable source snapshot.
- Never execute source code or install its dependencies.

### 2.4 Python analysis
- Parse files using `ast`.
- Extract modules, classes, functions, async functions, methods, nested functions where feasible, decorators, imports, inheritance, and call expressions.
- Preserve source locations.
- Resolve basic local and cross-file imports/calls, aliases, module-qualified names, and common method references where evidence supports it.
- Record unresolved/ambiguous references and confidence.
- Continue after per-file syntax errors.

### 2.5 Dependency graph and exploration
- Build typed graph nodes and edges.
- Expose file/module, class, and function/method views.
- Search symbols by short and qualified name.
- Filter by node/edge type and expand neighbors.
- Provide selected-node details and edge provenance.
- Show graph legend and a list/table alternative.

### 2.6 Change impact
- Analyze one or multiple selected symbols.
- Calculate upstream callers and downstream callees/dependencies.
- Distinguish direct and indirect impact and provide hop distance.
- Show representative paths and edge evidence.
- Support maximum traversal depth and prevent infinite loops in cyclic graphs.
- Provide a reproducible, explainable risk score with a factor breakdown.
- Deduplicate multi-target impact while preserving source-target attribution.

### 2.7 Diff analysis
- Accept pasted or uploaded unified diff.
- Parse changed files and hunk line ranges.
- Map changed ranges to symbols where possible.
- Mark added, modified, deleted, and unmapped changes.
- Calculate combined impact for mapped symbols.
- Do not claim native PR integration.

### 2.8 Coverage and test context
- Accept a supported Coverage.py JSON artifact.
- Match file paths to the source snapshot.
- Map covered/executable lines to symbols.
- Display covered, partially covered, uncovered, or unknown.
- Suggest tests only through a documented/defensible mapping.
- Missing coverage data must remain unknown.

### 2.9 Reporting
- Generate downloadable Markdown impact reports.
- Include source origin and snapshot provenance, changed/target symbols, direct/indirect impact, paths, risk factors, coverage context, diagnostics, and limitations.
- Ensure exported data matches the analysis result displayed in the UI.

### 2.10 Delivery and quality
- Backend unit/integration tests for auth, GitHub access, ingestion, parsing, resolution, graph, impact, diff, coverage, and reports.
- Frontend tests for auth states, project/source selection, graph and impact interactions, and reports.
- End-to-end test for GitHub source and ZIP source journeys.
- Setup documentation, environment examples, GitHub App setup guide, and troubleshooting.
- A synthetic Python fixture project and sample report.

## 3. Explicitly out of scope

1. Executing repository code, installing dependencies, running project tests, or executing arbitrary uploaded scripts.
2. Repository write permissions, push/commit operations, automated refactoring, or merge actions.
3. GitHub pull-request comments, webhook-driven analysis, CI checks, and full GitHub PR review UI.
4. GitLab, Bitbucket, GitHub Enterprise Server, or arbitrary Git provider support.
5. Multi-language analysis.
6. Team collaboration, shared projects, organization-level administration, billing, or enterprise SSO.
7. PDF export; Markdown is required.
8. LLM-based code interpretation and code modification.
9. Guaranteed resolution of reflection, monkey-patching, dynamic imports, or runtime dispatch.
10. A claim that heuristic risk scoring predicts the probability of a regression.

## 4. Two-person implementation model

### Initial shared commit

The first commit on `main` is a **scaffold and contract commit only**. Madvith prepares and creates this single shared commit; Sameeksha reviews the proposed structure and contract before the feature branches are created. It establishes directories, configuration placeholders, `.gitignore`, environment examples, minimal runnable app shells, test directories, and the shared API contract. It must not contain substantial product implementation or fabricated demo functionality.

Suggested commit:

`chore: scaffold FlowLens repository and shared API contracts`

After this commit, create both work branches from the same `main` commit:

- `feature/madvith-backend-core`
- `feature/sameeksha-frontend-app`

Both contributors must not develop directly on `main`.

### Ownership boundary

| Area | Madvith | Sameeksha |
|---|---|---|
| Backend API, database, models, migrations | Owner | No implementation |
| GitHub App auth, token lifecycle, repo access | Owner | Integrates UI only |
| ZIP/GitHub ingestion and source snapshots | Owner | Integrates UI only |
| AST parsing, resolver, NetworkX graph | Owner | No implementation |
| Impact, risk, diff, coverage, reports services | Owner | Consumes APIs and displays results |
| Frontend app shell, pages, components, styling | No implementation | Owner |
| GitHub login UI and repository picker | Backend contract support | Owner |
| Cytoscape graph and interactions | API support | Owner |
| Frontend validation, accessibility, E2E UI | Backend test support | Owner |
| Shared OpenAPI contract | Primary owner; changes coordinated | Consumer; do not edit independently |

Madvith owns the more complex backend/security/analysis work. Sameeksha owns the frontend. Each branch should keep changes within its assigned directories wherever possible.

## 5. Shared initial scaffold requirements

The initial commit should create a structure similar to:

```text
flowlens/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   └── services/
│   │       ├── auth/
│   │       ├── github/
│   │       ├── ingestion/
│   │       ├── analysis/
│   │       ├── resolution/
│   │       ├── graph/
│   │       ├── impact/
│   │       ├── diff/
│   │       ├── coverage/
│   │       └── reports/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── projects/
│   │   │   ├── github/
│   │   │   ├── graph/
│   │   │   ├── impact/
│   │   │   ├── diff/
│   │   │   ├── coverage/
│   │   │   └── reports/
│   │   ├── lib/
│   │   └── types/
│   ├── tests/
│   ├── package.json
│   └── .env.example
├── contracts/
│   └── openapi.yaml
├── docs/
│   ├── architecture.md
│   └── github-app-setup.md
├── sample-project/
├── .github/workflows/
├── .gitignore
├── docker-compose.yml
├── README.md
├── product.md
├── scope.md
├── phases.md
├── agent-madvith.md
└── agent-sameeksha.md
```

Empty directories may use `.gitkeep`. Do not create empty feature files with fake implementations. The initial contract must define request/response shapes and endpoint behavior sufficiently for parallel development.

## 6. Shared API contract

The initial contract should cover at least these routes. Exact naming can be finalized during scaffold, then frozen for parallel development.

### Authentication
- `GET /api/v1/auth/github/start` — initiates GitHub App user authorization and redirects to GitHub.
- `GET /api/v1/auth/github/callback` — backend callback; validates state, exchanges code, creates session, and redirects to the frontend.
- `GET /api/v1/auth/me` — returns the current FlowLens user/session state.
- `POST /api/v1/auth/logout` — invalidates the application session.

### GitHub installation and repositories
- `GET /api/v1/github/install/start` — redirects to GitHub App installation flow.
- `GET /api/v1/github/install/callback` — validates and records installation metadata.
- `GET /api/v1/github/installations` — returns installations accessible to the authenticated user.
- `GET /api/v1/github/installations/{installation_id}/repositories` — paginated repositories available through that installation.

### Projects and source snapshots
- `GET /api/v1/projects` — list current user's projects.
- `POST /api/v1/projects` — create a project where applicable.
- `POST /api/v1/projects/from-upload` — create project/snapshot from ZIP upload.
- `POST /api/v1/projects/from-github` — create project/snapshot from verified repository ID, installation ID, and ref.
- `POST /api/v1/projects/{project_id}/refresh` — refresh a connected GitHub project into a new snapshot.
- `DELETE /api/v1/projects/{project_id}/github-connection` — disconnect the provider link while retaining snapshots.
- `GET /api/v1/projects/{project_id}` — project details and source provenance.
- `GET /api/v1/projects/{project_id}/snapshots` — list immutable snapshots.

### Analysis, graph and impact
- `POST /api/v1/snapshots/{snapshot_id}/analyses` — start analysis.
- `GET /api/v1/analyses/{analysis_id}` — analysis status and summary.
- `GET /api/v1/analyses/{analysis_id}/symbols` — paginated/searchable symbol catalog.
- `GET /api/v1/analyses/{analysis_id}/graph` — filtered graph/subgraph.
- `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}` — node details.
- `GET /api/v1/analyses/{analysis_id}/nodes/{node_id}/neighbors` — neighborhood expansion.
- `POST /api/v1/analyses/{analysis_id}/impact` — impact query for one or more targets.

### Diff, coverage and reports
- `POST /api/v1/analyses/{analysis_id}/diff` — submit unified diff and return changed-symbol/impact result.
- `POST /api/v1/analyses/{analysis_id}/coverage` — upload/attach Coverage.py JSON.
- `POST /api/v1/analyses/{analysis_id}/reports` — generate Markdown report.
- `GET /api/v1/reports/{report_id}/download` — download report.

All endpoints require explicit schemas, user ownership checks, bounded pagination/limits, and a consistent error shape. Browser-facing API responses must never contain GitHub credentials or server filesystem paths.

## 7. Branch and merge rules

1. Both feature branches start from the exact initial scaffold commit.
2. Madvith owns `backend/**` and the authoritative `contracts/openapi.yaml`; Sameeksha owns `frontend/**`.
3. Shared root configuration and workflow changes require coordination. Avoid editing shared root files on both branches.
4. Sameeksha may generate TypeScript types from `contracts/openapi.yaml`, but should not independently change the API contract. If a change is necessary, raise it with Madvith and update both sides together.
5. Frontend development may use mocked API responses in tests/story states only. Production UI must use real API calls and must not show mock data as analysis results.
6. Merge order: merge Madvith's backend/API branch first after its tests pass; then rebase/merge Sameeksha's frontend branch and resolve any contract integration issues; finally run full end-to-end tests on the integrated branch.
7. Neither agent should force-push over the other branch or make unrelated formatting changes outside their ownership area.
8. Each PR must include the exact test/build commands run and any unverified areas.

## 8. Acceptance gates

### Gate A — Scaffold and shared contract
- Initial commit contains the agreed directory structure, app shells, environment examples, ignore rules, documentation, and API contract.
- Both contributors can create branches from the same commit.
- Frontend and backend have minimal health/start commands.
- No substantial feature implementation or fake data is present.

### Gate B — GitHub authentication and repository access
- User can sign in with GitHub App authorization.
- OAuth `state` is validated and one-time.
- Session cookie is secure and token credentials are never exposed to frontend code.
- User can install FlowLens GitHub App and list accessible installations/repositories.
- Repository import validates user, installation, repository ID, and ref.
- Private repository import works only when the installation and user permissions allow it.
- Access/installation revocation is handled with a clear error.
- Project ownership is enforced.

### Gate C — Local/GitHub ingestion
- ZIP validation and path traversal protections pass.
- GitHub import records source provenance and resolves the selected ref to a commit SHA.
- GitHub refresh creates a new snapshot and preserves older snapshots.
- No repository code is executed.

### Gate D — Analysis engine
- Parser extracts supported definitions and records syntax errors per file.
- Resolved edges carry evidence and confidence.
- Ambiguous/unresolved calls are not fabricated.
- Graph IDs and query results are deterministic.

### Gate E — Impact engine
- Tests validate upstream/downstream direction, direct/indirect levels, cycle safety, paths, depth limits, and multi-target deduplication.
- Risk score factors are visible and reproducible.
- Missing coverage is unknown.

### Gate F — Frontend workspace
- Login/logout and expired-session states work.
- User can create project using ZIP or GitHub repository source.
- User can observe analysis status and diagnostics.
- Graph search/filter/selection/neighbor expansion work.
- Impact panel reflects real API results.
- Diff, coverage, report actions show loading/error/empty/success states.
- A non-canvas list alternative is available.

### Gate G — Integrated release
- ZIP and GitHub end-to-end journeys pass.
- Exported Markdown matches the displayed impact result.
- Tests, lint, type checks, and production builds pass.
- Fresh setup instructions work.
- No known critical security issue remains.

## 9. Definition of done

A requirement is done only when:

- The behavior is implemented end to end in its owning layer.
- The frontend/backend contract is documented and synchronized.
- Success, empty, validation failure, and unexpected failure are handled.
- Relevant unit/integration/E2E tests exist and pass.
- No placeholder button, fake success message, or production mock result remains.
- Security and resource limits are respected.
- Documentation and `IMPLEMENTATION_STATUS.md` are updated.
- The contributor reports only tests and behaviors they actually verified.

## 10. Required test fixture matrix

Include fixtures for same-file calls, cross-file imports, aliases, relative imports, module-qualified calls, classes/methods/inheritance, async functions, nested functions, decorators, circular imports, dynamic calls such as `getattr`, duplicate symbol names, syntax errors, ignored folders, diff hunks, deleted/added files, module-level changes, mismatched coverage paths, malformed coverage, malicious ZIP paths, and resource-limit violations.

GitHub tests must cover OAuth state mismatch/replay, callback failure, token refresh/expiry/revocation, inaccessible installation, unselected repository, private repository permission denial, pagination, invalid ref, archive fetch failure, and user-to-project authorization boundaries. Use mocked GitHub API responses in automated tests; keep at least one documented manual integration test for a real GitHub App configured in a developer environment.

## 11. Release checklist

- [ ] Initial scaffold commit is on `main` and both feature branches are based on it.
- [ ] GitHub App setup instructions and required callback URLs are documented.
- [ ] `.env.example` lists required variables without secrets.
- [ ] Token encryption/session secrets are configured securely.
- [ ] CORS and cookie settings match the frontend/backend deployment origins.
- [ ] Database migrations or schema initialization are reproducible.
- [ ] ZIP and GitHub source journeys pass end to end.
- [ ] Analyzed project code is never executed.
- [ ] Project ownership checks pass.
- [ ] Backend and frontend tests/builds pass.
- [ ] Known analysis and GitHub limitations are documented.
- [ ] Sample project and report are included.
- [ ] No secret, credential, or developer-local absolute path is committed.
