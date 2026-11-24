# FlowLens GitHub App Setup

**Status:** outline — completed during Phase 3A on `feature/madvith-backend-core`.

FlowLens uses a GitHub App (not a broad OAuth App) for both user sign-in and
repository access.

## Registration summary

1. Create a GitHub App at `https://github.com/settings/apps/new`.
2. Enable **Request user authorization (OAuth) during installation** (or use the
   separate user authorization flow) — exact setting documented in Phase 3A.
3. Set the callback URL to `{BACKEND_PUBLIC_URL}/api/v1/auth/github/callback`.
4. Permissions (read-only only):
   - **Contents: read-only**
   - **Metadata: read-only**
5. No write permissions; no webhooks required for the MVP.
6. Generate a client secret and an app private key; store them in backend
   environment variables (see `backend/.env.example`), never in the repository.

## Local testing

- Documented manual smoke test with a configured development GitHub App is added
  in Phase 3A.

## Environment variables

See `backend/.env.example`; every required GitHub App variable is listed with a
safe placeholder and an explanation.

## Installation flow

Users install the app on their personal account or an organization they
administer; the backend verifies installation ownership through GitHub APIs
before listing or importing repositories.
