# Agent Instructions — Madvith

**Role:** Backend lead, GitHub integration, static analysis and graph/impact engine  
**Branch:** `feature/madvith-backend-core`  
**Workload:** Primary / larger engineering workstream

## 1. Mission

Build the complete FlowLens backend and the difficult core services: GitHub App authentication and repository access, secure source ingestion, Python AST extraction, cross-file dependency resolution, graph construction, impact analysis, diff mapping, coverage mapping, and Markdown reports.

Your implementation must follow `product.md`, `scope.md`, and `phases.md`. These documents are the requirements contract. Do not reduce requirements silently to make implementation easier.

## 2. Start-up procedure

1. Confirm you are on `feature/madvith-backend-core` and that it was created from the shared scaffold commit.
2. Read all project documents and inspect the existing backend/package/database structure before editing.
3. Verify the OpenAPI contract in `contracts/openapi.yaml`. Treat it as the shared frontend/backend boundary.
4. Create or update `IMPLEMENTATION_STATUS.md` with branch, current phase, test commands, and known gaps.
5. Implement in the order below. Keep the backend runnable after every phase.

If the scaffold commit has not yet been created, you are responsible for preparing it on `main` as specified in Phase 0 of `phases.md`. Get Sameeksha's review of the folder layout and OpenAPI contract before committing. Once the single scaffold commit is complete, create/work only on `feature/madvith-backend-core`; do not make further feature commits directly to `main`.

## 3. Ownership boundaries

### You own
- `backend/**`
- Backend migrations, ORM models, schemas, repositories, service layer, API routes, and backend tests.
- `docs/github-app-setup.md` and backend sections of `docs/architecture.md`.
- Authoritative updates to `contracts/openapi.yaml`, coordinated with Sameeksha before changing a response/request contract.
- Backend `.env.example` and backend-specific configuration.

### You must not independently modify
- `frontend/**` (owned by Sameeksha).
- Frontend generated types or UI components.
- Shared root configuration such as Docker Compose, root README, or CI workflows without coordinating first.

If you need a frontend or shared-root change, document the requested change and communicate it rather than editing the other workstream's files.

## 4. Required implementation order

### A. Backend foundation and database

- FastAPI application structure with typed configuration.
- Centralized error handling and stable API error envelope.
- Request IDs and structured logging with credential redaction.
- Health/readiness routes.
- SQLAlchemy models and Alembic migrations.
- User ownership model for projects, snapshots, analyses, and reports.
- Storage abstraction for source snapshots and generated reports.
- Database transaction/session handling and appropriate uniqueness/index constraints.

Suggested domain records include `User`, `GitHubCredential`, `GitHubInstallation`, `GitHubRepositoryConnection`, `Project`, `SourceSnapshot`, `AnalysisRun`, `Symbol`, `DependencyEdge`, and `Report`. Adapt the schema to the implementation, but preserve the ownership and provenance requirements.

### B. GitHub App sign-in and sessions

Use a GitHub App with user authorization enabled. Do not use a broad OAuth App `repo` scope as a shortcut.

Implement:

- `GET /api/v1/auth/github/start`
- `GET /api/v1/auth/github/callback`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

Requirements:

- Generate and validate an unpredictable, one-time OAuth `state` value with short expiry.
- Exchange the authorization code on the backend only.
- Fetch the GitHub authenticated user and key the FlowLens account on GitHub's stable numeric user ID.
- Persist only necessary profile information (ID, login, avatar URL); do not require email for MVP.
- Keep GitHub access/refresh tokens server-side and encrypt them at rest.
- Implement token expiry/refresh and revoked/invalid credential behavior.
- Create a secure application session with `HttpOnly`, `Secure` in production, and suitable `SameSite` settings.
- Implement CSRF protection and/or strict Origin checks for state-changing cookie-authenticated requests.
- Never return access/refresh tokens to the frontend or store them in a browser-readable cookie/local storage.
- Keep callback URLs, frontend origin, and allowed CORS origins in configuration.

### C. GitHub App installation and repository access

Implement:

- `GET /api/v1/github/install/start`
- `GET /api/v1/github/install/callback`
- `GET /api/v1/github/installations`
- `GET /api/v1/github/installations/{installation_id}/repositories`

Requirements:

- Document GitHub App registration, callback URL, installation URL, and required app settings.
- For the MVP, request only **Contents: read-only** and **Metadata: read-only**.
- Do not request repository write access.
- Verify installation ownership/access with GitHub APIs. Treat browser-supplied installation IDs as untrusted.
- List only repositories the authenticated user and FlowLens installation are both permitted to access.
- Support API pagination and rate-limit errors.
- Use short-lived installation access tokens for repository operations. Scope a generated token to the selected repository where supported.
- Do not keep long-lived installation tokens in the database; generate/cache them only for their validity period with secure handling.
- Handle organization approval requirements, removed installations, unselected repositories, SAML/permission restrictions, and revocation cleanly.

### D. GitHub source import and ZIP ingestion

Implement:

- `POST /api/v1/projects/from-github`
- `POST /api/v1/projects/{project_id}/refresh`
- `DELETE /api/v1/projects/{project_id}/github-connection`
- `POST /api/v1/projects/from-upload`
- Project and snapshot list/detail endpoints.

GitHub requirements:

- Accept verified repository ID, installation ID, and ref; resolve the submitted repo/ref against GitHub server-side.
- Do not trust owner/name alone. Persist canonical GitHub repository ID and full name.
- Fetch source through official GitHub API/archive endpoints with a strict host/redirect allowlist.
- Do not shell out to `git clone`, run hooks, or accept arbitrary remote URLs.
- Resolve and record the commit SHA before/with source snapshot creation.
- Create a new immutable snapshot on refresh; never overwrite historical analysis sources.
- Disconnect must prevent future refresh/access but preserve existing snapshots and reports.

ZIP requirements:

- Validate archive format, compressed/uncompressed size, file count, and per-file size.
- Reject absolute paths, `..` traversal, duplicate unsafe entries, symlink/path surprises, and extraction escapes.
- Extract only inside a managed snapshot directory after resolving and validating every path.
- Apply documented exclusions and report skipped paths.
- Never execute repository contents or install requirements.

### E. AST parser and symbol catalog

- Parse files through Python `ast` only.
- Extract modules, classes, functions, async functions, methods, nested definitions where feasible, decorators, base classes, imports, and call expressions.
- Capture qualified names, lexical parents, stable deterministic IDs, file paths, and line/column ranges.
- Continue after per-file syntax errors and emit diagnostics.
- Handle duplicate names and nested scopes without ID collisions.
- Expose searchable/paginated symbol APIs.
- Do not equate an AST call expression with a successfully resolved dependency.

### F. Cross-file resolution and graph

- Create a resolver interface independent of extraction.
- Resolve straightforward imports, aliases, relative imports, module-qualified calls, local lexical references, and supported method patterns.
- Jedi may be used as a resolver adapter if tests show meaningful benefits. LibCST should be used for concrete syntax/source mapping, not described as semantic resolution on its own.
- Each edge must include type, endpoints, confidence, source evidence, and resolution method.
- Ambiguous/unresolved/dynamic calls must be recorded explicitly.
- Use NetworkX behind a graph service abstraction.
- Keep structural containment separate from dependency traversal edges.
- Provide graph summary, filtered graph, node detail, neighbors, and shortest-path queries with limits and deterministic sorting.

### G. Impact engine and risk score

- Implement upstream caller and downstream callee/dependency traversals.
- Use BFS for minimum hop distance and representative shortest paths.
- Use visited sets to prevent cycles and support max-depth/result limits.
- Distinguish direct and indirect impact.
- Support multiple target symbols, deduplicate results, and preserve attribution.
- Calculate a versioned, explainable 0–100 score. Expose factors and normalization.
- Treat absent coverage as unknown; renormalize the score when coverage is not available.
- Never describe the score as regression probability.

### H. Diff, coverage and report generation

- Parse unified diff file/hunk data and map changed line ranges to symbol source spans.
- Preserve added/modified/deleted/unmapped status.
- Support multiple targets and combined impact.
- Validate Coverage.py JSON and normalize paths within the snapshot.
- Map coverage line data to symbol spans and return covered/partial/uncovered/unknown.
- Suggest tests only when mapping evidence exists.
- Generate safe, deterministic Markdown reports containing snapshot/provider/commit provenance, targets, impact paths, risk factors, coverage, diagnostics, exclusions, and limitations.
- Add ownership checks for every project/analysis/report route and download.

## 5. API contract responsibilities

`contracts/openapi.yaml` is the shared agreement with Sameeksha.

- Keep routes and response fields aligned with the endpoints described in `scope.md` and `phases.md`.
- Every response used by the frontend must have an explicit schema.
- Every user-owned resource route must enforce ownership before reading or mutating data.
- Use stable enums for analysis states, source providers, node kinds, edge kinds, impact directions, coverage statuses, and error codes.
- If a contract change is required, first communicate the request and reason to Sameeksha, then update the contract and notify them to regenerate TypeScript types.
- Do not expose server paths, secrets, exception strings, GitHub tokens, or private key material.

## 6. Required security rules

- Never execute the analyzed Python code or use `importlib` to inspect it.
- Never run user-controlled shell commands or `git clone` URLs.
- Validate all archive paths and resource limits.
- Never accept GitHub installation/repository IDs as proof of access; verify against GitHub.
- Keep GitHub App private key and client secret in server-only environment/secret storage.
- Encrypt user access/refresh tokens at rest and redact credentials from logs.
- Validate OAuth state and callback. Use secure session cookies and CSRF/Origin controls.
- Restrict GitHub API/archive fetching to allowlisted hosts and safe redirects.
- Enforce project ownership at the service/repository layer, not only in UI.
- Keep source files outside public static directories.

## 7. Testing expectations

Write tests while implementing, not at the end.

### Authentication/GitHub
- OAuth state valid, invalid, expired, and replayed.
- Token exchange failure, refresh success/failure, expiry, revocation.
- Installation not found, wrong owner, removed installation, inaccessible repo, repository not selected, private repo permission denied.
- Repository pagination, invalid ref, rate limit, archive download error, disallowed redirect host.
- Ensure API responses/logs contain no credential values.

### Ingestion/analysis
- ZIP traversal and absolute path, malformed archive, excessive decompression, too many files, excluded folders.
- Syntax error in one file while other files still analyze.
- Imports/aliases/relative imports, nested functions, methods/inheritance, async, cycles, dynamic calls, duplicate names.

### Graph/impact/report
- Duplicate edges, deterministic ordering, cycle handling, upstream/downstream direction, direct/indirect, depth limits, path validity, multiple targets, risk-score reproducibility.
- Diff hunk mapping and unmapped lines.
- Coverage path mismatch and unknown status.
- Markdown escaping and report consistency.

Use mocked GitHub API responses in automated tests. Document one manual smoke test with an actual development GitHub App.

## 8. Environment variables and setup documentation

Document the exact names used by the implementation. Expected categories include:

- GitHub App ID, client ID, client secret, app slug, private key, and callback URLs.
- Session signing secret and token encryption key.
- Database URL and source/report storage root.
- Frontend origin, backend public URL, allowed CORS origins, cookie domain/security settings.

Only variable names and safe placeholders belong in `.env.example`. Never commit real credentials, private keys, tokens, or developer-specific paths.

## 9. Completion requirements

Before requesting merge:

- All applicable backend phases in `phases.md` are complete.
- `contracts/openapi.yaml` matches the implemented API.
- Database migrations work on a clean database.
- Backend unit/integration tests pass.
- Formatting, lint, and type checks pass.
- `docs/github-app-setup.md` enables another developer to configure a test app.
- `IMPLEMENTATION_STATUS.md` contains exact commands and observed results.
- PR description lists implemented scope, known gaps, and manual test steps.

## 10. Merge coordination

Madvith's branch should be merged first so Sameeksha can integrate against the real backend and final contract. Before merge:

1. Notify Sameeksha of any OpenAPI contract changes.
2. Ensure the backend can start and exposes a valid OpenAPI schema.
3. Include migration and environment setup instructions.
4. Avoid changing frontend files or unrelated root configuration.
5. Do not claim GitHub integration works until tested against a configured GitHub App or clearly mark automated tests as mocked-provider tests.

## 11. End-of-session update

Update `IMPLEMENTATION_STATUS.md` with current phase, completed backend work, changed files, commands run, actual pass/fail result, GitHub test assumptions, blockers, and the next task. Be explicit about mocked vs real GitHub verification.
