# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam` (based on `main` after Phase 2A backend merge; Phase 2B already merged)
**Phase:** 3B complete — Project dashboard and source creation UX
**Ownership:** `frontend/**` only. No files in `backend/**` or `contracts/openapi.yaml` were modified in this phase.

## Completed in this session (Phase 3B)

All UI is built against the frozen `contracts/openapi.yaml` v0.1.0. Production paths call
the real backend only; stubbed fetch/XHR responses exist exclusively inside `tests/`.

### Shared foundation (added)

- `src/types/api.ts` — contract types added: `SourceProvider`, `AnalysisState`, `NodeKind`,
  `GitHubInstallation`, `RepositorySummary`, `PaginatedRepositories`, `GitHubConnection`,
  `DiagnosticsSummary`, `AnalysisRun`, `GitHubProvenance`, `Snapshot`, `Project`,
  `PaginatedProjects`, `PaginatedSnapshots` (mirrored from the contract, no undocumented keys).
- `src/lib/use-async.ts` — `useAsync` data-loading hook (loading / error-message mapping /
  reload) and a shared `errorMessage` helper; unmounted results discarded.
- `src/lib/format.ts` — locale-explicit date/time + short-hash display helpers
  (unknown values render as "—", never fabricated).
- `src/components/ui/progress.tsx` — accessible progress bar; determinate mode takes only
  measured values, omitting the value yields an honest indeterminate state.
  Keyframes added to `src/app/globals.css`.

### Features/projects

- `src/features/projects/projects-service.ts` — typed wrappers: `listProjects`,
  `getProject`, `listSnapshots`, `createProject`, `createProjectFromGithub`,
  `refreshProject`, `disconnectGithubConnection`, and `createProjectFromUpload`
  (XMLHttpRequest-based so real upload progress is available; `withCredentials=true`,
  120s timeout, abort support, error envelope normalized through the shared
  `toApiError` parser — same envelope as the fetch client).
- Components: `ProviderBadge` (icon + text), `AnalysisStateBadge` (explicit
  "No analysis yet" absence state), `ProjectCard`, `ProjectsDashboard`
  (loading skeletons / error + retry / empty / paginated grid), `ZipUploadForm`
  (client checks only the file type honestly; backend `UPLOAD_INVALID` /
  `UPLOAD_TOO_LARGE` messages shown verbatim; real upload progress; duplicate-submission
  guard; retry keeps the selection; cancel during body upload), `DisconnectDialog`
  (explicitly states snapshots/reports are retained; stays open on failure).
- `src/features/github/github-service.ts` — `listInstallations`,
  `listInstallationRepositories` (paginated), `githubInstallUrl`
  (`GET /api/v1/github/install/start` as full-page navigation, never XHR).
- `src/features/github/components/github-source-form.tsx` — install/update FlowLens App
  card, installation/account selector, repository picker (radio list with search filter of
  the visible page + pagination + per-page empty/back-end failures),
  ref entry pre-filled from the repository's `default_branch`, project-name (optional),
  import submit; permission failures (`REPOSITORY_ACCESS_DENIED`) and rate/invalid-ref
  errors surface the backend message; visibility badges shown as informational only with
  an explicit disclaimer (access is never inferred from them).

### Pages

- `/dashboard` — real project list (was a placeholder empty shell in Phase 2B).
- `/projects/new` — source chooser with "Upload ZIP" / "Connect GitHub" tabs.
- `/projects/[project_id]` — project detail/settings: created-notice (once, via
  `?created=1` + sessionStorage guard), source origin (repository, ref, visibility badge +
  "informational" note, connected date, latest snapshot hash/file count, resolved commit),
  immutable snapshot history, refresh (optional different ref; new snapshot appended;
  403 messaging for lost access), disconnect with confirmation; 404/not-owned handling.
- Note for Phase 4B: start-analysis actions are intentionally NOT present yet — the
  analysis lifecycle UI is Phase 4B scope; no placeholder buttons were added.

## Files added or changed (frontend/ only)

```
frontend/
├── IMPLEMENTATION_STATUS.md                  (this file)
├── src/
│   ├── app/globals.css                       (progress keyframes appended)
│   ├── app/(protected)/dashboard/page.tsx    (now renders ProjectsDashboard)
│   ├── app/(protected)/projects/new/page.tsx          (new: source chooser)
│   ├── app/(protected)/projects/[project_id]/page.tsx (new: detail/settings)
│   ├── components/ui/progress.tsx            (new)
│   ├── features/projects/projects-service.ts (new)
│   ├── features/github/github-service.ts     (new)
│   ├── features/github/components/github-source-form.tsx (new)
│   ├── features/projects/components/{provider-badge,analysis-state-badge,
│   │        project-card,projects-dashboard,zip-upload-form,disconnect-dialog}.tsx (new)
│   ├── lib/{use-async.ts,format.ts}          (new)
│   └── types/api.ts                          (contract types added)
└── tests/
    ├── dashboard-projects.test.tsx  (new: 5 tests)
    ├── zip-upload.test.tsx          (new: 5 tests, XHR stubbed)
    ├── github-source.test.tsx       (new: 8 tests)
    └── project-detail.test.tsx      (new: 5 tests)
```

## Commands run and observed results (2026-11-25, Windows, Node 24 / npm 11)

- `npm run typecheck` (`tsc --noEmit`) — **pass, no errors**
- `npm test` (`vitest run`) — **54 passed, 0 failed, 8 files** (31 pre-existing Phase 2B
  tests still green; 23 new Phase 3B tests)
- `npm run lint` (`eslint .`) — **pass, no errors**
- `npm run build` (`next build`) — **pass**; routes: `/`, `/dashboard`, `/login`,
  `/projects/new`, `/projects/[project_id]` (dynamic server-rendered),
  `/settings`, `/_not-found`

## Mocked vs real API

- Tests only: global `fetch` stubs + XHR stub for the upload suite; no MSW, no fixtures
  shipped as data, no mock results in product flow.
- Production code paths call the real backend exclusively
  (`NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`; no provider tokens of any kind
  in frontend code/env/storage).

## Known gaps / integration notes for Madvith

1. **Contract gap (frontend consumer view):** there is no endpoint to list a repository's
   branches/tags. The ref field is therefore free-text pre-filled with the repository's
   `default_branch`; a wrong ref currently surfaces the backend's validation error after
   submit. If a `GET .../branches` route (or ref suggestions embedded in
   `RepositorySummary`) is desired, coordinate the contract change and I will regenerate
   types + adapt the picker.
2. Repository search/filter is client-side within the loaded page (the contract's
   repositories endpoint only paginates; no `q` parameter). If server-side search is
   wanted, that is another candidate for coordination.
3. GitHub/project endpoints (`/github/installations…`, `/projects…`, specific refresh/
   disconnect) are Phase 3A backend scope; the UI is contract-complete but browser
   behavior against the live backend (cookie/CORS, real install callbacks) must be
   verified after that merge. Error-envelope polygon (e.g. `REPOSITORY_ACCESS_DENIED`,
   `INSTALLATION_NOT_FOUND`, `UPLOAD_INVALID`, `UPLOAD_TOO_LARGE`) is mapped from the
   backend messages, including the extended code list (codes are treated as extensible
   strings, so new backend codes do not break the UI).
4. Subscription of `error_code` extras: `INSTALLATION_NOT_FOUND` and `RATE_LIMITED` are
   displayed through the generic message path; dedicated copy can be added once the
   backend sends them in practice.
5. ZIP content/diagnostics feedback: `Project.latest_snapshot.file_count` is shown; any
   richer skipped-file diagnostics need a future contract addition if desired in the UI.

## Next smallest actionable task

Phase 4B: project workspace shell — connect analysis start/status/symbol listing UI to
`POST /api/v1/snapshots/{snapshot_id}/analyses`, `GET /api/v1/analyses/{analysis_id}` and
`/symbols` once the Phase 4A backend lands; until then keep the detail page honest
(no analysis controls).
