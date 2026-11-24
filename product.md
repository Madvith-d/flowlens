# FlowLens — Product Definition

**Product:** FlowLens — Code Dependency & Change Impact Visualizer  
**Document role:** Product requirements and behavior contract  
**Release target:** MVP / first usable release  
**Primary language analyzed:** Python

## 1. Product overview

FlowLens is a developer tool that analyzes Python repositories, maps code dependencies, visualizes those dependencies, and estimates the impact of a proposed code change. Users can sign in with GitHub, connect repositories that the FlowLens GitHub App is permitted to access, or upload a local ZIP archive. FlowLens analyzes a source snapshot without executing the analyzed project.

The core user journey is:

1. Sign in using GitHub.
2. Create a project by selecting an accessible GitHub repository or uploading a ZIP archive.
3. For GitHub, choose an installation/account, repository, and branch or commit reference.
4. Run static analysis and inspect diagnostics.
5. Explore the dependency graph at module/file, class, and function/method levels.
6. Select a symbol or a set of changed symbols as the change target.
7. Inspect direct and indirect impact, dependency paths, risk factors, and available test coverage.
8. Export a Markdown impact report.

FlowLens is an **analysis assistant**, not a proof of program behavior. Its graph represents statically inferred relationships. Dynamic Python behavior can make some dependencies unresolved or ambiguous; the product must show this uncertainty instead of inventing edges.

## 2. Goals

### 2.1 Primary goals

- Provide GitHub sign-in and a secure way to connect repositories through a GitHub App.
- Support repository source import from GitHub and local ZIP uploads.
- Analyze Python projects without importing or executing their code.
- Extract modules, classes, functions, methods, imports, inheritance, and statically identifiable calls.
- Resolve common same-file and cross-file references with confidence and provenance.
- Build a directed, typed dependency graph.
- Visualize relationships interactively and support file/module, class, and function/method views.
- Calculate upstream callers and downstream dependencies for a selected symbol.
- Trace paths between a changed symbol and potentially impacted symbols.
- Present explainable risk indicators rather than an unexplained score.
- Map unified diffs to symbols and calculate combined change impact.
- Optionally overlay Coverage.py results and suggest relevant tests where mappings are defensible.
- Export reproducible Markdown reports.

### 2.2 Secondary goals

- Refresh a connected GitHub project from a selected branch or commit.
- Compare analysis snapshots from different commits.
- Improve cross-file resolution through a replaceable Jedi-based resolver.
- Support larger repositories through bounded graph queries, filtering, and incremental improvements.

## 3. Non-goals for the MVP

- Executing uploaded or connected repository code, installing its dependencies, or running its tests.
- Guaranteeing complete resolution of reflection, `getattr`, dynamic imports, monkey-patching, runtime-generated code, or arbitrary dynamic dispatch.
- Automatically changing source code, creating commits, or merging pull requests.
- Native GitHub pull-request comments, webhooks, CI status checks, or GitLab/Bitbucket support.
- Multi-language analysis.
- Team collaboration, shared workspaces, organization billing, enterprise SSO, or a full SaaS administration console.
- PDF export; Markdown is the required report format for the first release.
- LLM-based code interpretation or automatic code modifications.
- Claiming that a risk score is a probability of a regression.

## 4. Target users and jobs

### Python developer
- Understand callers and dependencies before changing a function.
- Find indirect effects of refactoring a shared helper.
- Discover highly coupled modules and symbols.

### Code reviewer
- Inspect the likely impact of changed functions before approving a patch.
- Find relevant call paths and potentially affected tests.
- Export an impact summary for review discussions.

### New team member
- Understand project structure and module relationships.
- Trace a feature through functions and classes.
- Identify architectural hotspots without manually searching the whole repository.

## 5. Core product concepts

### User account
A FlowLens account identified by the authenticated GitHub account. Store the stable GitHub numeric user ID as the external identity key, along with the login and avatar URL. A GitHub email address is not required for the MVP.

### GitHub App installation
An installation of the FlowLens GitHub App on a personal account or organization. An installation grants the app access only to the repositories selected during installation and only for the permissions configured for FlowLens.

### Connected GitHub repository
A repository selected by the user from an installation that FlowLens can access. Store its GitHub repository ID, canonical owner/name, installation relationship, default branch, visibility, and connection metadata. Do not trust repository names or installation IDs submitted by the browser without server-side verification.

### Project
A user-owned analysis workspace with a source provider (`github` or `upload`), source metadata, immutable source snapshots, analysis runs, and reports.

### Source snapshot
An immutable copy of a repository tree at a particular commit/ref, or an uploaded ZIP revision. Each snapshot records a content hash and source provenance. A GitHub snapshot records repository ID, full name, ref, resolved commit SHA, and import timestamp.

### Analysis run
An immutable record of a particular snapshot analyzed with a FlowLens version and configuration. Store state, timestamps, file/symbol/edge counts, diagnostics, and graph schema version.

### Symbol
A module, class, function, or method with a deterministic identifier within an analysis run. Example formats include `package.module:function_name` and `package.module:ClassName.method_name`; nested scopes and duplicate names must remain collision-safe.

### Dependency edge
A typed, directed relationship such as `CALLS`, `IMPORTS`, `INHERITS`, `REFERENCES`, or `CONTAINS`. Edges retain evidence and a confidence value/category where applicable.

### Impact result
A derived result for one or more target symbols, including upstream/downstream affected symbols, hop distance, representative paths, risk factors, diagnostics, and optional coverage/test context.

## 6. Functional requirements

### FR-1: GitHub authentication

- Provide a **Continue with GitHub** sign-in flow.
- Use a GitHub App configured for user authorization rather than requesting broad OAuth App scopes by default.
- Perform the authorization-code exchange on the backend. The client secret and private key must never reach the browser.
- Validate an unpredictable, one-time OAuth `state` value and callback parameters.
- Create or retrieve a FlowLens account using GitHub's stable numeric user ID.
- Maintain a secure application session using an `HttpOnly`, `Secure` (in production), appropriately `SameSite` cookie.
- Keep GitHub user access tokens and refresh tokens on the backend only; encrypt them at rest.
- Handle access-token expiration, refresh, revocation, and failed reauthorization explicitly.
- Provide `GET current user` and `logout` behavior.
- Do not require repository installation merely to establish the user's identity. Repository access is a separate authorization step.

### FR-2: GitHub App installation and repository connection

- Provide a clear action to install the FlowLens GitHub App on the user's personal account or an organization they administer, subject to GitHub policy.
- Request only the permissions needed for the MVP: repository **Contents: read-only** and **Metadata: read-only**. Do not request write permissions.
- Support listing installations and repositories accessible to the authenticated user through those installations.
- Support repository pagination and show owner, repository name, visibility, default branch, and description when available.
- Allow the user to select a repository and a branch/tag/commit reference.
- Verify the installation, repository ID, user access, and requested ref on the backend before importing.
- Use a short-lived installation access token scoped to the chosen repository when fetching source content. Do not expose the token to the browser.
- Import repository source through GitHub's API/archive endpoints using an allowlisted GitHub host/redirect policy. Do not shell out to `git clone` with user-controlled input.
- Record origin repository ID, full name, ref, resolved commit SHA, and import timestamp in the project/snapshot.
- Allow a connected project to be refreshed into a new immutable snapshot.
- Allow a user to disconnect a repository. Disconnecting must not silently erase already-created analysis snapshots or reports.
- Handle revoked, removed, or restricted installations with actionable error messages.
- MVP support is for `github.com`; GitHub Enterprise Server is out of scope unless separately approved.

### FR-3: Local source upload

- Allow authenticated users to upload a ZIP archive containing source code.
- Validate archive format, compressed size, uncompressed size, file count, and per-file size.
- Reject absolute paths, traversal entries, unsafe names, and extraction paths escaping the managed snapshot directory.
- Ignore standard generated directories by default: `.git`, `.venv`, `venv`, `__pycache__`, `node_modules`, build output, and configured exclusions.
- Preserve relative paths and infer importable module paths conservatively.
- Report discovered Python files, skipped files, and reasons.
- Never import or execute uploaded source.

### FR-4: Static parsing and symbol extraction

- Parse each Python file using the standard-library `ast` module.
- Record syntax errors per file and continue processing other files.
- Extract modules, classes, functions, async functions, methods, nested definitions where feasible, decorators, base classes, imports, and call expressions.
- Preserve source line and column ranges.
- Record parser diagnostics and unsupported constructs.
- Do not assume every `ast.Call` expression can be resolved to a unique symbol.

### FR-5: Name and cross-file resolution

- Resolve straightforward local calls, imported names, aliases, module-qualified calls, relative imports, and common class/method cases where static evidence supports it.
- Use a resolver abstraction so the initial AST resolver can be improved with Jedi.
- Use LibCST only for concrete-syntax/source-range needs; do not present it as a semantic resolver by itself.
- Label ambiguous or unresolved calls rather than fabricating edges.
- Store confidence (`high`, `medium`, `low`, or a documented numeric scale), resolution strategy, and source evidence.
- Explain dynamic dispatch limitations in the UI and reports.

### FR-6: Dependency graph

- Construct typed nodes and edges for a specific source snapshot.
- Support module/file, class, and function/method granularities.
- Preserve edge provenance: source path, line/column, expression, resolver, and confidence.
- Deduplicate equivalent edges without losing multiple evidence locations.
- Calculate in-degree, out-degree, reachable-node count, and other documented graph metrics.
- Produce deterministic results for identical snapshots, tool versions, and configuration.

### FR-7: Interactive graph

- Render a directed, zoomable, pannable graph.
- Support node selection, search, node/edge-type filters, impact highlighting, and neighborhood expansion.
- Provide file/module, class, and function/method views.
- Show selected node metadata and relationship evidence in a details panel.
- Distinguish direct impact, indirect impact, unaffected visible nodes, and unresolved relationships.
- Keep larger graphs usable with limits, filtering, clustering/grouping, and lazy neighborhood requests.
- Provide a list/table alternative to canvas-only navigation.
- Use a legend and text/icon cues; color must not be the only status indicator.

### FR-8: Change impact simulation

For a selected target symbol, calculate and present:

- Direct upstream callers and direct downstream callees/dependencies.
- Transitive upstream and downstream nodes within a configurable depth.
- Minimum hop distance and one or more representative paths.
- Potential entry points or externally visible endpoints where inferable.
- Risk factors, dependency counts, resolution confidence, and coverage status when available.
- The traversal direction and analysis limitations.

Use BFS for shortest-hop exploration and graph traversal with cycle protection. Static reachability is not proof that a path executes at runtime.

### FR-9: Risk scoring

- Provide a transparent, configurable score from 0 to 100.
- Consider normalized upstream reachable dependents, in-degree/centrality, downstream breadth, public/entry-point indicators, and coverage deficiency when coverage is available.
- Expose the individual factor values, normalization method, and scoring version.
- Treat missing coverage as `unknown`, not zero coverage.
- If coverage is unavailable, renormalize the available factors and label the score accordingly.
- Describe the score as a prioritization heuristic, not a predicted failure probability.

### FR-10: Git diff and changed-symbol analysis

- Accept a pasted or uploaded unified diff in the MVP.
- Parse changed file paths and hunk line ranges.
- Map changed lines to containing symbols using snapshot source locations.
- Mark changes as added, modified, deleted, or unmapped.
- Preserve unmapped changes and diagnostics.
- Calculate combined impact for multiple changed symbols and deduplicate impacted nodes while retaining per-target attribution.
- Native pull-request discovery and comment posting are not part of the MVP.

### FR-11: Test and coverage overlay

- Accept a supported Coverage.py JSON artifact.
- Validate its schema and normalize paths against the source snapshot.
- Map covered/executable lines to symbol ranges.
- Display `covered`, `partially_covered`, `uncovered`, or `unknown`.
- Suggest tests only where an explicit or defensible mapping exists.
- Explain that execution coverage does not measure assertion quality or behavioral completeness.
- Never run tests from the connected/uploaded repository.

### FR-12: Reports

Generate downloadable Markdown reports containing:

- Project, user-visible source origin, snapshot, commit/ref, analysis timestamp, and tool version.
- Target/changed symbols and direct/indirect impacted symbols.
- Important paths and relationship evidence.
- Risk score, factor breakdown, and scoring version.
- Test/coverage context when supplied.
- Unresolved references, diagnostics, exclusions, and analysis limitations.
- Suggested review/validation actions.

### FR-13: Analysis lifecycle

- Use states: `queued`, `running`, `completed`, `completed_with_warnings`, and `failed`.
- Provide progress stages and diagnostic summaries.
- Allow retry for failed analyses where the snapshot remains available.
- Tie every analysis result to an immutable source snapshot and configuration.
- Avoid exposing server paths, stack traces, credentials, or raw secret values to the client.

## 7. UX and screen requirements

1. **Authentication:** sign in with GitHub, session loading, expired session, logout, and authorization failure states.
2. **Projects dashboard:** list owned projects, source provider, connected repository/ref, latest commit/snapshot, and latest analysis status.
3. **Create project/source chooser:** upload ZIP or connect a GitHub repository; GitHub flow includes installation/account, repository, and ref selection.
4. **Analysis workspace:** graph canvas, search/filter controls, hierarchy/navigation, selected-node details, and list alternative.
5. **Impact panel:** target, direction, depth, impacted symbols, paths, risk factors, and tests/coverage.
6. **Diff review:** changed files/symbols, combined impact, and unmapped changes.
7. **Reports:** preview and download Markdown report.
8. **Settings/help:** connected installations/repositories, disconnect action, exclusions, graph limits, score explanation, and analysis limitations.

All major controls must have loading, empty, success, and error states. Authentication and repository permission failures must explain the next recovery step.

## 8. Recommended architecture

### Frontend
- React + TypeScript; Next.js App Router is the default unless the existing repository has a sound alternative.
- Tailwind CSS + shadcn/ui.
- Cytoscape.js as the single MVP graph renderer. React Flow is not to be added in parallel.
- Typed API client generated from or kept in sync with `contracts/openapi.yaml`.
- Browser requests use `credentials: include` for the application session; never store GitHub access tokens in browser storage.

### Backend
- FastAPI on Python 3.11+.
- Pydantic request/response schemas.
- SQLAlchemy + Alembic recommended; SQLite acceptable for local development, PostgreSQL preferred for shared deployments.
- Python `ast` for parsing.
- Resolver interface with optional Jedi adapter.
- NetworkX for MVP graph algorithms behind a graph-service abstraction.
- Background analysis mechanism must be bounded. A durable queue is not mandatory until measured load requires one.

### GitHub integration
- GitHub App with user authorization enabled.
- App permissions for MVP: Contents read-only and Metadata read-only.
- OAuth authorization-code exchange and token lifecycle handled server-side.
- Installation access token generated server-side and scoped to the selected repository for source fetches.
- Private key, client secret, access tokens, refresh tokens, and session signing/encryption keys remain server-side.

### Storage
- Persist user, project ownership, GitHub installations/repository links, snapshots, analysis metadata, graph artifacts, and report metadata.
- Store source files and reports outside the public web root.
- Encrypt GitHub tokens at rest using an application-managed encryption key or managed secret/KMS integration.
- Enforce ownership checks on every project, snapshot, analysis, and report request.

## 9. Security and privacy requirements

- Never execute analyzed source or run package installation commands from a repository.
- Treat ZIP entries, source text, Git diffs, GitHub metadata, and report content as untrusted input.
- Reject archive path traversal and enforce decompression/resource limits.
- Enforce OAuth `state`, callback validation, secure sessions, CSRF protections for state-changing cookie-authenticated requests, and strict CORS origins.
- Keep GitHub credentials server-side; encrypt persisted tokens and redact them from logs.
- Request only read-only GitHub repository permissions required for source retrieval.
- Validate repository IDs and installation ownership/access server-side; never trust owner/name/installation IDs from the browser alone.
- Use short-lived, repository-scoped installation tokens where possible.
- Restrict remote requests to documented GitHub API/archive hosts and validate redirects to prevent SSRF.
- Enforce user-level project ownership. A user must not access another user's projects or reports by changing identifiers.
- Provide disconnect/logout behavior and handle GitHub access revocation.

## 10. Non-functional requirements and initial targets

### Reliability
- A malformed source file must not fail the whole analysis.
- Analysis results must be reproducible for the same snapshot and configuration.
- GitHub refresh creates a new snapshot; it must not mutate historical analysis results.

### Performance
- Initial target: a Python project of up to 100 source files should usually analyze within 10 seconds on a typical development machine; measure before promising this as a service-level guarantee.
- Keep approximately 2,000 visible graph nodes responsive through filtering and neighborhood expansion.
- Apply timeouts, upload limits, parser limits, graph-depth limits, and bounded result sizes.

### Maintainability
- Separate authentication, GitHub integration, ingestion, parsing, resolution, graph construction, impact, diff, coverage, reports, and API layers.
- Use stable, versioned schemas and deterministic IDs.
- Add unit, integration, and end-to-end tests.
- Document unsupported Python constructs and GitHub permission assumptions.

## 11. Product success criteria

- A user can sign in with GitHub and see their FlowLens account.
- A user can install/connect FlowLens to a GitHub account and import an accessible public or private repository that the installation is authorized to read.
- A user can upload a ZIP and obtain equivalent analysis capabilities.
- No analyzed source code is executed.
- A user can search/select a symbol and inspect direct callers/callees.
- A user can distinguish direct, indirect, unresolved, and unaffected visible nodes.
- Diff changes map to symbols where source locations allow.
- Markdown reports match the displayed analysis and include provenance and caveats.
- User A cannot access User B's projects, snapshots, connected repository metadata, or reports.
- Tests cover GitHub token/session lifecycle, repository permission failures, ZIP safety, parser/resolver behavior, graph traversal, diff mapping, coverage, and report generation.

## 12. Defaults and product decisions

- Analysis language: Python only.
- Source providers: ZIP upload and GitHub App-connected repository.
- GitHub platform: github.com only for the MVP.
- GitHub permissions: Contents read-only and Metadata read-only; no repository write access.
- GitHub login: GitHub App user authorization flow; identity and repository installation remain distinct concepts.
- GitHub source retrieval: server-side installation token, scoped to the selected repository.
- Graph renderer: Cytoscape.js.
- Backend: FastAPI + AST + NetworkX.
- Report: Markdown.
- Unresolved relationships: diagnostics, not fabricated edges.
- Hosted GitHub PR integration, PDF export, multi-language support, collaboration, and billing: future scope.

## 13. Official GitHub design references

- [Differences between GitHub Apps and OAuth Apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/differences-between-github-apps-and-oauth-apps)
- [Authenticating with a GitHub App on behalf of a user](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user)
- [Generating a user access token for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
- [Authenticating as a GitHub App installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
