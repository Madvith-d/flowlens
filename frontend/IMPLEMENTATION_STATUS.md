# IMPLEMENTATION_STATUS — Frontend (Sameeksha)

**Branch:** `sam`
**Phase:** 2B — Frontend foundation and authentication UX
**Ownership:** `frontend/**` only. No files in `backend/**` or `contracts/openapi.yaml` were modified.

## Completed in this session

- Next.js App Router structure with Tailwind CSS theme (design tokens, focus-visible
  rings, container widths) and a shadcn/ui-style component library:
  Button, Card, Alert, Input/Label, Badge, Skeleton/Spinner, Dialog,
  DropdownMenu, Avatar, EmptyState, ErrorState, plus `sonner` toasts wired in
  the root layout.
- Typed API layer kept in sync with `contracts/openapi.yaml` v0.1.0:
  - `src/types/api.ts` — SessionState/AuthUser/error envelope/pagination types
    mirrored from the contract (no undocumented keys).
  - `src/lib/api-client.ts` — single client: `NEXT_PUBLIC_API_BASE_URL`,
    `credentials: "include"` on every request, JSON/multipart bodies, 20s
    timeout via `AbortController` (works in jsdom too), safe error
    normalization (`ApiError`, `NetworkError`), 401 → session-expired handler
    (`/auth/me` exempted so the signed-out check cannot loop).
- Auth UX (Phase 2B scope):
  - `/login` — Continue with GitHub performs a full-page navigation to
    `GET /api/v1/auth/github/start` (never XHR); states for session-check
    loading, signed-out, session-expired, GitHub callback failure, and
    backend-unavailable with Reload.
  - `SessionProvider` (`useSession`) checks `GET /api/v1/auth/me`;
    `RequireAuth` guard renders loading skeleton / children / redirect to
    `/login?reason=expired` / backend-unavailable error state with retry.
  - `LogoutButton` with confirmation dialog; calls `POST /api/v1/auth/logout`;
    navigates to `/login?reason=signed-out`; failures keep the dialog open
    with an actionable message.
  - Protected app shell: sticky header, user menu from safe `/auth/me` data
    only, responsive container, skip-to-content link, analysis-caveat footer.
  - Pages: `/` → dashboard redirect, `/dashboard`, `/settings` (account +
    session only; GitHub connection UI arrives with Phase 3B).
- Tests (vitest + Testing Library, mocked fetch — no MSW needed):
  - `tests/api-client.test.ts` — credentials include, base URL/env override,
    JSON/FormData bodies, query serialization, error envelope → ApiError
    (code/message/request_id), non-envelope fallback message, mid-session 401
    handler, `/auth/me` 401 exemptions, NetworkError, 204 handling (11 tests).
  - `tests/session.test.tsx` — provider states: loading, authenticated,
    unauthenticated redirect, backend-unavailable error + retry, logout POST,
    refresh-after-401 without redirect loop (7 tests).
  - `tests/login-page.test.tsx` — login states, OAuth navigation target,
    expired/signed-out/callback-failure notices, reload on backend down,
    no provider-token leakage in the DOM (9 tests).
  - `tests/logout-button.test.tsx` — confirm/cancel, endpoint call +
    navigation, backend-failure message remains visible (4 tests).

## Files added or changed (frontend/ only)

```
frontend/
├── eslint.config.mjs            (new, FlatCompat with next/core-web-vitals + next/typescript)
├── package.json                 (scripts: lint=eslint ., test/test:watch; new deps)
├── postcss.config.mjs           (new)
├── tailwind.config.ts            (new)
├── vitest.config.ts              (new)
├── IMPLEMENTATION_STATUS.md      (this file)
├── src/
│   ├── app/
│   │   ├── globals.css           (new theme tokens)
│   │   ├── layout.tsx            (root: SessionProvider + Toaster + skip link)
│   │   ├── page.tsx              (redirect → /dashboard)
│   │   ├── login/page.tsx        (new)
│   │   └── (protected)/
│   │       ├── layout.tsx        (new guarded shell)
│   │       ├── dashboard/page.tsx
│   │       └── settings/page.tsx
│   ├── components/
│   │   ├── ui/ (button, card, alert, input, badge, skeleton, dialog,
│   │   │        dropdown-menu, avatar, states)
│   │   └── layout/ (app-header.tsx, account-card.tsx)
│   ├── features/auth/
│   │   ├── auth-service.ts
│   │   ├── session-provider.tsx
│   │   ├── require-auth.tsx
│   │   └── components/ (github-login-button.tsx, logout-button.tsx)
│   ├── lib/ (api-client.ts, api-error.ts, utils.ts)
│   └── types/api.ts
└── tests/ (setup.ts + 4 test suites)
```

## Commands run and observed results (2025-06-12, Windows, Node 24 / npm 11)

- `npm install` + dev deps install — OK
- `npm test` → `vitest run` — **31 passed, 4 files**
- `npm run typecheck` → `tsc --noEmit` — **pass, no errors**
- `npm run lint` → `eslint .` — **pass, no errors**
- `npm run build` → `next build` — **pass**, 5 routes, all static-prerendered
- `npx next dev -p 3100` live smoke — `/login` HTTP 200 with FlowLens markup,
  `/dashboard` HTTP 200 (client guard runs in browser); server stopped after check

## Mocked vs real API

- All tests use a stubbed global `fetch` (no MSW; no fixtures shipped as data).
- Production code paths call the real backend only. No GitHub client secret,
  private key, access token, refresh token, or installation token appears in
  frontend code or env files; only `NEXT_PUBLIC_API_BASE_URL` is configured.

## Known gaps / next smallest tasks

- Real-backend sign-in redirect is unverified until Phase 2A backend
  (`/auth/github/start`, `/auth/me`, `/auth/logout`) is merged; then verify
  cookie/CORS behavior across origins (browser, not just tests).
- Contract note for Madvith (frontend consumer view): the OpenAPI callback
  describes an "error query parameter" on the frontend redirect; the frontend
  recognizes `reason`/`error` values `oauth`, `oauth_denied`, `auth` and
  `expired`, `signed-out`. Align the exact values at integration time.
- Next phase (3B): project dashboard data, ZIP upload, GitHub installation/
  repository/ref pickers against the real endpoints.

## Next smallest actionable task

Start Phase 3B project dashboard scaffolding: add `Project` types wiring to
`GET /api/v1/projects` in a `projects` feature module with list/empty/error
states tested against mocked contract responses.
