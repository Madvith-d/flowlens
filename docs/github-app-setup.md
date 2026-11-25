# FlowLens GitHub App Setup

**Status:** complete for Phase 3A (installation + repository connection).

FlowLens uses a GitHub App (not a broad OAuth App) for both user sign-in and
repository access. github.com only; GitHub Enterprise Server is not supported.

## Registration summary

1. Create a GitHub App at `https://github.com/settings/apps/new` (or your
   organization's App registration page).
2. Enable **Request user authorization (OAuth) during installation**.
3. Callback URLs:
   - **Callback URL**: `{BACKEND_PUBLIC_URL}/api/v1/auth/github/callback`
     (user authorization / sign-in).
   - **Setup URL**: `{BACKEND_PUBLIC_URL}/api/v1/github/install/callback`
     (installation flow redirect after install/update).
   - Example `Authorization callback URL` must match theOAuth callback exactly.
4. Permissions (read-only only):
   - **Contents: read-only**
   - **Metadata: read-only** (mandatory, automatically granted)
5. No repository write permissions; no webhooks required for the MVP.
6. Generate a **client secret** and an App **private key**; store them in
   backend environment variables (see `backend/.env.example`). Never commit
   them, never log them, never return them from an API response.
7. Set **Where can this GitHub App be installed?** per your preference;
   the backend verifies installation access through GitHub APIs regardless.

## Permissions model

- User sign-in: user access token (encrypted at rest, server-side only).
- Repository access: short-lived **installation access tokens** created
  server-side per request, scoped to the selected repository where supported,
  with `Contents: read` and `Metadata: read` only. Tokens are never persisted
  or exposed to the frontend.

## Environment variables

See `backend/.env.example`; every required GitHub App variable is listed with
a safe placeholder and an explanation:

- `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_CLIENT_ID`,
  `GITHUB_APP_CLIENT_SECRET`, `GITHUB_APP_PRIVATE_KEY` (PEM content),
  `GITHUB_OAUTH_CALLBACK_URL` (falls back to
  `{BACKEND_PUBLIC_URL}/api/v1/auth/github/callback`).

## Installation flow (what the backend does)

1. `GET /api/v1/github/install/start` — authenticated users are redirected to
   `https://github.com/apps/{slug}/installations/new` with a one-time `state`.
2. After installing, GitHub redirects to the Setup URL
   (`/api/v1/github/install/callback`) with `installation_id` and `setup_action`.
3. The backend validates the one-time `state`, then verifies the
   `installation_id` against the authenticated user's installation list
   (GitHub API `GET /user/installations`). Unverifiable installations are
   rejected with `REPOSITORY_ACCESS_DENIED`.
4. Verified installations are recorded and redirected to the frontend.

## Manual smoke test (development app)

Automated tests use a mocked GitHub API. To verify against a real GitHub App:

1. Register a development GitHub App as above (callback URLs on localhost).
2. Fill `backend/.env` and run migrations (`alembic upgrade head`).
3. Start the backend; sign in through the frontend login page
   (`/auth/github/start` → GitHub → back to the frontend signed in).
4. Call `GET /api/v1/github/install/start`, complete the installation page on
   github.com, and confirm the redirect lands on the frontend with the
   installation recorded.
5. `GET /api/v1/github/installations` should list the installation;
   `GET /api/v1/github/installations/{id}/repositories` should list the
   repositories selected during installation.
6. Import a repository via `POST /api/v1/projects/from-github` with a real
   repository id, installation id, and ref; confirm the project shows an
   immutable snapshot with the resolved commit SHA.

## Error handling notes

- Removed/revoked installations and installations not accessible to the user:
  `INSTALLATION_NOT_FOUND` / `REPOSITORY_ACCESS_DENIED`.
- Repository not selected during installation or otherwise inaccessible:
  `REPOSITORY_ACCESS_DENIED` (GitHub returns HTTP 404 for those, which the
  backend maps to an explicit denial).
- Invalid branch/tag/commit ref: `NOT_FOUND` with a ref-specific message.
- Rate limits: `RATE_LIMITED` (HTTP 429).
