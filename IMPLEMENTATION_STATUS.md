# FlowLens — Implementation Status

**Contributor:** Madvith (backend, GitHub integration, analysis engine)
**Current branch:** `madvith` (backend workstream)
**Phase:** 3A complete (GitHub App installation and repository connection)

## Completed work

### Phase 0 — Scaffold commit (on `main`, commit `9256538`) — done

Structure-only scaffold + shared `contracts/openapi.yaml` (28 paths, 44 schemas), verified:
health endpoints live, backend tests 2 passed, frontend build/typecheck passed.

### Phase 2A — Backend foundation and account/session layer (merged to `main`) — done

FastAPI app factory with typed settings, JSON logging with credential redaction,
request IDs, stable error envelope, SQLAlchemy 2 models + Alembic, Fernet
token encryption, signed `HttpOnly` session cookies, Origin/CSRF validation,
GitHub App OAuth sign-in with one-time state, mocked-provider tests. See
`git log` of `fbc4ec3` for details. Verified via `.venv/bin/python -m pytest -q`
(27 passed at the time).

### Phase 3A — GitHub App installation and repository connection (branch `madvith`)

- **Settings** (`app/core/config.py`): GitHub App ID/slug/private key,
  archive base URL (github.com only), snapshot resource limits (file count,
  uncompressed bytes, compressed archive bytes, download timeout), exact-host
  allowlist properties.
- **GitHub App client** (`app/services/github/app_client.py`): injectable
  interface + production `HttpxGitHubAppClient`.
  - RS256 app JWT signing for installation tokens, implemented directly with
    `cryptography` (no new dependency; format per GitHub App docs, ≤10 min exp).
  - Short-lived installation access tokens, repository-scoped
    (`repository_ids=[…]`) where supported, `Contents: read`,
    `Metadata: read` only; tokens exist only in server memory, are never
    logged, stored, or returned to clients.
  - Paginated `GET /user/installations` (user-verified installations) and
    `GET /installation/repositories` (top-level pagination via page/per_page
    plus the total_count pass-through).
  - `GET /repositories/{id}` with an installation token: GitHub's 404 for
    unselected/inaccessible repos maps to explicit `REPOSITORY_ACCESS_DENIED`
    (browser-supplied repository IDs are never trusted as proof of access).
  - Ref resolution (`/commits/{ref}` → `sha`) and archive download from the
    `codeload.github.com` host with a validated-host allowlist and bounded
    manual redirects (SSRF guard), size-limited streaming, no `git clone`,
    no shells, no arbitrary URLs.
  - Rate-limit (429 / `x-ratelimit-remaining: 0`) and transport errors mapped
    to stable envelopes (`RATE_LIMITED` 429, `GITHUB_API_ERROR` 502) — newly
    documented contract codes.
- **Installation service** (`app/services/github/service.py`): installation
  flow reuses the one-time `OAuthState` store (install callbacks cannot be
  replayed or forged); installs verify the installation against the
  authenticated user's installations list before recording anything;
  repositories listed only after installation-level verification.
- **Ingestion** (`app/services/ingestion/`):
  - `archive.py`: traversal/absolute-path/link rejection, per-entry
    normalization, file-count and total-uncompressed-size limits, `.git`/
    `__pycache__`/… default exclusions with skipped-entry reporting, and a
    stable SHA-256 content hash of the raw archive.
  - `storage.py`: snapshot-per-directory storage under
    `STORAGE_ROOT/snapshots/{snapshot_id}/` with path-escape validation,
    outside any served directory.
- **Projects service** (`app/services/projects/service.py`): GitHub import
  verifying user → installation → repository → ref (SHA) before any source is
  fetched; immutable snapshots (refresh always inserts a new one and can move
  the ref forward); disconnect removes future access while retaining all
  snapshots; strict per-user ownership enforced at the repository layer.
- **Repositories** (`app/repositories/installations.py`, `projects.py`):
  verified-installation upsert (verified_at) and project/snapshot data access
  scoped by `user_id`/`project_id`.
- **API routes** (`app/api/v1/github.py`, `app/api/v1/projects.py`): install
  start/callback (browser redirects with stable error codes),
  installations/repositories listing, `GET/POST /projects`,
  `POST /projects/from-github`, `GET /projects/{id}`,
  `POST /projects/{id}/refresh`, `DELETE /projects/{id}/github-connection`,
  `GET /projects/{id}/snapshots`; responses serialized through
  `app/schemas/serializers.py` to stay aligned with the frozen contract.
- **Contract** (`contracts/openapi.yaml`): added `GITHUB_API_ERROR` and
  `GITHUB_APP_NOT_CONFIGURED` to the `ErrorCode` enum (extensible by design)
  — Sameeksha should regenerate or extend frontend error-code handling.
- **Migration** `a1c74f9d3e02`: `projects.github_visibility` +
  `projects.github_default_branch` (connection provenance); `GitHubInstallation.id`
  now defaults to a generated object id.

## Files/modules added or changed (Phase 3A)

- Changed: `app/core/config.py`, `app/main.py` (routers + app client wiring),
  `app/api/deps.py` (auth dependency + service bundles), `app/models/github.py`,
  `app/models/projects.py`, `app/services/github/client.py` (unchanged),
  `tests/conftest.py`, `contracts/openapi.yaml`, `backend/.env.example`,
  `docs/github-app-setup.md`, `IMPLEMENTATION_STATUS.md`.
- Added: `app/services/github/app_client.py`, `app/services/github/service.py`,
  `app/services/ingestion/archive.py`, `app/services/ingestion/storage.py`,
  `app/services/projects/service.py`, `app/repositories/installations.py`,
  `app/repositories/projects.py`, `app/api/v1/github.py`,
  `app/api/v1/projects.py`, `app/schemas/serializers.py`,
  `backend/alembic/versions/a1c74f9d3e02_add_github_connection_visibility.py`,
  `tests/unit/test_archive_extraction.py`,
  `tests/integration/test_github_install.py`,
  `tests/integration/test_projects_github.py`.
- No frontend files touched; no root config touched.

## Exact commands executed and actual results

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **61 passed** (Phase 2A suite intact + 9 archive-safety unit tests, 12 installation-flow tests, 13 project import/refresh/disconnect/ownership tests; 1 starlette deprecation warning) |
| `DATABASE_URL=sqlite:////tmp/flowlens_mig_test.db .venv/bin/python -m alembic upgrade head` (clean DB) | Both migrations applied (`48e88e749069` → `a1c74f9d3e02`); `github_visibility`/`github_default_branch` columns verified with `PRAGMA table_info(projects)` |

## Known issues, blockers, assumptions

- **GitHub verification is mocked-provider only** in automated tests (per the
  project rules): the scripted `MockGitHubAppClient` simulates installations,
  repo pagination, access denial, expired installation tokens, invalid refs,
  and archive failures. The real-GitHub smoke test procedure is documented in
  `docs/github-app-setup.md` and remains a manual step.
- Token refresh for user access tokens is still Phase-8 hardening work;
  expired/revoked user tokens surface as `GITHUB_TOKEN_ERROR` (401) today.
- Re-created-tarball determinism: `content_hash` digests the exact archive
  bytes; GitHub tarballs are not byte-stable across requests for the same SHA
  in all cases (embedded timestamps), so the hash identifies the snapshot, not
  a "same content" guarantee — noted here to avoid over-claiming.
- If import/refresh fails after archive extraction started, extracted files
  for the not-yet-committed snapshot remain on disk until storage GC is added
  (planned Phase 8); DB rows are rolled back so no API ever exposes them.
- ZIP ingestion (`/projects/from-upload`) is Phase 4A; `POST /projects` (bare
  project) returns an upload-provider project without a snapshot for now.
- `GET /auth/me` still returns 200 with `authenticated:false` instead of 401
  (per contract); all new Phase 3A routes require a real session (401
  `AUTH_REQUIRED`).

## API/schema/database changes

- Implemented endpoints match the frozen contract for the installed group:
  `/github/install/start|callback`, `/github/installations`,
  `/github/installations/{id}/repositories`, `/projects` (GET/POST),
  `/projects/from-github`, `/projects/{id}` (GET),
  `/projects/{id}/refresh` (POST), `/projects/{id}/github-connection`
  (DELETE), `/projects/{id}/snapshots` (GET).
- `ErrorCode` enum additions: `GITHUB_API_ERROR`, `GITHUB_APP_NOT_CONFIGURED`.
  Sameeksha: please notify/integrate when regenerating types.
- Database migration `a1c74f9d3e02` (down revision `48e88e749069`).

## Next smallest actionable task

Phase 4A start: secure ZIP ingestion reusing
`app/services/ingestion/archive.py` (ZIP-specific validation tests:
malformed archives, traversal entries, decompression bombs, per-file limits,
excluded folders) plus the picker metadata APIs shared with GitHub import.
