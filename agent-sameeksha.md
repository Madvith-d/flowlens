# Agent Instructions — Sameeksha

**Role:** Frontend lead, application experience, graph visualization and client-side integration  
**Branch:** `feature/sameeksha-frontend-app`  
**Primary ownership:** Frontend application and frontend tests

## 1. Mission

Build the complete FlowLens frontend: GitHub login experience, project dashboard, ZIP upload, GitHub App installation/repository picker, analysis workspace, interactive dependency graph, impact visualization, diff review, coverage overlay, and Markdown report UI.

Your frontend must consume the shared API contract and display real backend results. It must not contain backend business logic, client-side GitHub secrets, fabricated analysis results, or production-only mock data.

## 2. Start-up procedure

1. Confirm you are on `feature/sameeksha-frontend-app` and that it was created from the shared scaffold commit.
2. Read `product.md`, `scope.md`, `phases.md`, and this agent document.
3. Inspect the current frontend structure and package scripts before modifying anything.
4. Read `contracts/openapi.yaml` and generate or align frontend TypeScript types from it.
5. Create/update `IMPLEMENTATION_STATUS.md` with your branch, current phase, test/build commands, and known gaps.
6. Implement in the order below, keeping the app runnable and adding tests as you go.

Before the feature branches are created, review Madvith's proposed scaffold and the OpenAPI contract from the frontend consumer's perspective. Confirm the frontend structure and setup commands are suitable. Do not start feature implementation or commit to `main`. After the single scaffold commit is made, create/work only on `feature/sameeksha-frontend-app`.

## 3. Ownership boundaries

### You own
- `frontend/**`
- Frontend routes, pages, components, styling, state, API client, graph renderer, frontend tests, and frontend tooling.
- Frontend-specific documentation under `docs/` only when it does not conflict with shared architecture documentation.

### You must not independently modify
- `backend/**`, backend tests, database models, migrations, or backend business logic.
- `contracts/openapi.yaml` as an independent change. It is the shared API contract and Madvith is the primary owner.
- Shared root configuration, Docker Compose, CI workflows, or README without coordinating.

If an API payload or endpoint is missing, write down the exact required contract change and coordinate with Madvith. Do not work around missing data by guessing or deriving security-sensitive values in the browser.

## 4. Required frontend stack and principles

- React + TypeScript; use the existing Next.js App Router baseline if scaffolded that way.
- Tailwind CSS + shadcn/ui.
- Cytoscape.js is the selected MVP graph renderer. Do not add React Flow as a second graph implementation.
- Use the shared OpenAPI contract to generate/maintain TypeScript request and response types.
- Centralize API access in a typed client.
- All authenticated API calls must include cookies (`credentials: include`).
- Never place GitHub client secrets, private keys, OAuth access tokens, refresh tokens, or installation tokens in frontend environment variables or browser storage.
- Use frontend mocks only for unit tests, component previews, or clearly isolated development. The normal app workflow must use the real backend.
- Avoid giant components. Group by product feature and keep forms, API hooks, graph state, and presentation separate.

## 5. Required implementation order

### A. App shell and design system

- Set up application layout, navigation, page containers, typography, theme, responsive behavior, and design tokens.
- Configure Tailwind and shadcn/ui consistently.
- Create reusable buttons, inputs, dialogs, cards, badges, tabs, tooltips, tables, alerts, toasts, loading skeletons, empty states, and error states.
- Define a consistent developer-tool aesthetic that is clear and functional rather than overly decorative.
- Provide responsive layouts for desktop and narrower screens.
- Add focus states, keyboard support, and accessible labels.

### B. GitHub login and session UX

- Build a login/landing screen with a **Continue with GitHub** action.
- Clicking the action redirects the browser to backend `GET /api/v1/auth/github/start`.
- After backend callback, read session status through `GET /api/v1/auth/me`; do not parse or store provider tokens in the client.
- Build authenticated route guards or layouts based on app session state.
- Implement logout through `POST /api/v1/auth/logout`.
- Handle unauthenticated, loading, session-expired, authorization-failed, and backend-unavailable states.
- Display the GitHub login/avatar only from the safe current-user response.
- Do not request or store GitHub email unless the product contract is changed.

### C. API client and data handling

- Build one API client with a configured backend base URL, JSON/multipart support, typed responses, credentials, timeout/abort handling, and a shared error parser.
- Support consistent error envelope handling such as `error.code`, `error.message`, and `request_id`.
- Add typed hooks/data services for auth, projects, GitHub repositories, snapshots, analyses, graph, impact, diff, coverage, and reports.
- Ensure upload progress and long-running analysis status are represented accurately.
- Use the API schema as the source of truth; do not hard-code undocumented response keys.
- If generated TypeScript types need refreshing after Madvith changes `openapi.yaml`, coordinate, then regenerate from the shared contract.

### D. Projects dashboard

- Build the authenticated dashboard listing the current user's projects.
- Show project title, provider (GitHub or ZIP), repository or uploaded archive metadata, ref/commit when relevant, latest snapshot, and analysis status.
- Add empty state and create-project action.
- Add search/sort only if it can be implemented cleanly from available response data.
- Build project detail/settings view with source provenance, snapshot history, refresh, and disconnect options for GitHub-backed projects.
- Clearly explain that disconnecting GitHub access does not delete historical snapshots or reports.

### E. Source creation: ZIP and GitHub

#### ZIP upload
- Build ZIP picker/dropzone and project naming form.
- Show client-side file-size/type feedback but rely on backend validation as authoritative.
- Show actual upload progress where supported.
- Display backend ingestion errors and skipped-file diagnostics.
- Prevent duplicate submissions and allow retry when appropriate.

#### GitHub repository selection
- Build an **Install FlowLens GitHub App** action that navigates to the backend installation-start endpoint.
- Build installation/account selector using `GET /api/v1/github/installations`.
- Build searchable/paginated repository picker using the installation repositories endpoint.
- Show repository name, owner, visibility, default branch, and description when available.
- Build branch/tag/commit ref selector. Do not assume a ref exists; validate through the backend contract.
- Submit selected installation ID, repository ID, and ref to `POST /api/v1/projects/from-github`.
- Show permission denied, no installation, no accessible repositories, organization approval required, invalid ref, rate-limit, and import failure states.
- Do not infer actual access from a public/private badge; backend response is authoritative.

### F. Analysis lifecycle and symbol browsing

- Build project workspace with project info, active snapshot/ref/commit, analysis status, progress stage, counts, and diagnostics.
- Provide start/retry analysis action using the appropriate API endpoint.
- Refresh status with bounded polling or the agreed backend mechanism; stop polling after terminal states or navigation away.
- Build searchable symbol list with filters and pagination.
- Show qualified name, symbol type, source location, and analysis warnings.
- Support empty projects, no Python files, syntax errors, partial analysis, failed analysis, and stale snapshot states.

### G. Interactive graph workspace

Use Cytoscape.js only.

- Render real graph nodes/edges from backend graph APIs.
- Provide file/module, class, and function/method views through graph filters/grouping.
- Add zoom, pan, fit-to-view, reset, selection, edge selection, search, node/edge filters, depth controls, and neighbor expansion.
- Add selected-node details panel with qualified name, kind, file/line span, graph metrics, incoming/outgoing dependencies, evidence, and confidence.
- Use concise graph labels with full qualified names in the details panel/tooltips.
- Provide legend for node/edge kinds, direct/indirect impact, unresolved/low-confidence links, and selected target.
- Add a keyboard-accessible list/table alternative for nodes and relationships.
- Avoid loading the entire graph if it is too large. Use bounded filtered/subgraph/neighbor endpoints.
- Handle graph layout/loading failures and large result warnings without freezing the page.

### H. Impact analysis UX

- Build target selection from graph nodes and symbol search.
- Add direction selection: upstream callers, downstream dependencies, or both.
- Add traversal-depth control within backend limits.
- Submit impact request and render direct vs indirect impacted nodes.
- Show hop distance, representative paths, risk score, score factors, and warnings.
- Allow selecting an impacted node/path to inspect the relevant graph route and edge evidence.
- Show explicit caveat that static paths do not prove runtime execution.
- Handle no impact, low-confidence resolution, incomplete analysis, and request errors.
- Do not calculate an alternative client-side risk score; display the backend score and factors.

### I. Diff, coverage and reports

- Build paste/upload unified-diff interface.
- Show changed files, mapped symbols, added/modified/deleted status, and unmapped hunks.
- Present combined impact results from the backend.
- Show coverage states `covered`, `partially_covered`, `uncovered`, and `unknown` with a legend.
- Never render unknown coverage as uncovered.
- Build report generation action, Markdown preview, metadata, and download.
- Show diagnostics/limitations in report preview.
- Handle empty diff, unsupported diff, malformed coverage, mismatched paths, no tests mapped, report failure, and download failure.

## 6. Screen inventory and completion expectations

| Screen | Required behavior |
|---|---|
| Login | GitHub sign-in redirect, loading and failure states |
| Dashboard | List projects, create project, empty state |
| Create project | ZIP upload and GitHub source flows |
| GitHub picker | Installation, repository, and ref selection |
| Project workspace | Source metadata, snapshots, analysis status, diagnostics |
| Graph workspace | Search, filters, graph, details, list alternative |
| Impact panel | Direction/depth, affected nodes, paths, risk factors |
| Diff review | Changed symbol mapping and combined impact |
| Coverage | Coverage overlay and unknown handling |
| Reports | Generate, preview and download Markdown |
| Settings | Refresh/disconnect GitHub connection and project metadata |

## 7. API coordination with Madvith

The shared contract is in `contracts/openapi.yaml`.

- Generate frontend types from this file and use those types in API hooks/components.
- Do not guess response fields or create parallel undocumented endpoint shapes.
- Keep a small `API_INTEGRATION.md` or status section listing endpoint dependencies and integration gaps.
- If an endpoint is missing, tell Madvith the required route, input, output, loading behavior, and error cases.
- If the contract changes, regenerate types and update the relevant frontend tests.
- Do not modify backend source to make the UI work.

Expected areas include:

- Auth: start, callback redirect, current user, logout.
- GitHub: installation start/callback, list installations, list repositories.
- Projects: list/detail, upload, GitHub import, refresh, disconnect, snapshots.
- Analysis: start/status, symbols, graph, node details, neighbors, impact.
- Review: diff, coverage, reports, Markdown download.

## 8. UX quality and accessibility requirements

- Every page has clear loading, empty, success, and failure states where applicable.
- All primary controls work; no decorative placeholder buttons.
- Keyboard users can reach and operate forms, dialogs, menus, and list-based graph alternatives.
- Provide visible focus states and accessible names.
- Status must not depend on color alone.
- Preserve project/snapshot context during navigation.
- Use confirmation for disconnect actions and clarify their effect on existing snapshots.
- Keep error messages actionable and avoid displaying raw backend stack traces.
- Do not show fake percentages or progress unless the backend provides meaningful progress.

## 9. Testing expectations

### Component/unit tests
- Login/loading/error states and authenticated route behavior.
- API client credentials, error mapping, and unauthorized handling.
- Project dashboard empty/list states.
- ZIP upload validation/progress/failure states.
- GitHub installation/repository/ref selection and permission failures.
- Analysis status transitions and diagnostics.
- Graph filters, node selection, details, list alternative, and large graph handling.
- Impact direction/depth and direct/indirect rendering.
- Diff mapping, coverage unknown state, report preview/download.

### Integration/E2E tests
- Logged-out user is redirected to login.
- GitHub sign-in callback creates a session and dashboard loads.
- User connects an installation and selects a repository.
- ZIP source can be uploaded and analyzed.
- User can search/select a symbol and run impact.
- Diff and coverage responses render correctly.
- Markdown report download works.
- Session expiry/logout returns user to the correct unauthenticated state.

Use mocked API responses for frontend tests. The integrated application must use the real backend; do not ship mock fixtures as default project data.

## 10. Completion requirements

Before requesting merge:

- All applicable frontend tasks in `phases.md` are complete.
- TypeScript types match the shared OpenAPI contract.
- API client sends cookies and never stores provider tokens.
- Frontend unit/component tests pass.
- Lint, type check, and production build pass.
- Graph uses Cytoscape.js, with a list/table alternative.
- No production mock data, fake progress, or inert controls remain.
- Responsive and accessibility checks are complete.
- `IMPLEMENTATION_STATUS.md` lists exact commands and observed results.
- PR description lists implemented screens, API integrations, known gaps, and test results.

## 11. Merge coordination

Madvith's backend branch is expected to merge first. When it is merged:

1. Fetch latest `main` and rebase/merge it into `feature/sameeksha-frontend-app`.
2. Regenerate TypeScript API types if the OpenAPI contract changed.
3. Run frontend tests, lint, type check, and production build.
4. Validate actual auth cookie/CORS behavior against the merged backend.
5. Open the frontend PR and list any endpoint/contract mismatches explicitly.

Do not force-push or modify Madvith's branch. Do not merge the frontend based only on mocked API tests; run the integrated app against the real backend before final release.

## 12. End-of-session update

Update `IMPLEMENTATION_STATUS.md` with branch, phase, completed frontend work, changed files, exact test/build commands and actual outcomes, mocked-vs-real API status, current integration gaps, and the next smallest task.
