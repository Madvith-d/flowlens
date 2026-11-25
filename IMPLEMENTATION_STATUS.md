# FlowLens — Implementation Status

**Contributor:** Madvith (backend, GitHub integration, analysis engine)
**Current branch:** `madvith` (backend workstream)
**Phase:** 4A complete (secure ZIP ingestion and AST analysis)

## Completed work

### Phase 0 — Scaffold commit (on `main`, commit `9256538`) — done

Structure-only scaffold + shared `contracts/openapi.yaml`, verified: health
endpoints live, backend tests passed, frontend build/typecheck passed.

### Phase 2A — Backend foundation and account/session layer (merged to `main`) — done

FastAPI app factory with typed settings, JSON logging with credential redaction,
request IDs, stable error envelope, SQLAlchemy 2 models + Alembic, Fernet token
encryption, signed `HttpOnly` session cookies, Origin/CSRF validation, GitHub App
OAuth sign-in with one-time state, mocked-provider tests. Commit `fbc4ec3`.

### Phase 3A — GitHub App installation and repository connection (merged to `main`) — done

RS256 app JWT (hand-rolled with `cryptography`), short-lived repository-scoped
installation tokens, paginated installations/repositories, ref→SHA resolution,
allowlisted `codeload` archive download with bounded validated redirects (SSRF
guard), projects import/refresh/disconnect with server-side installation and
repository verification, ownership enforcement, `GITHUB_API_ERROR` /
`GITHUB_APP_NOT_CONFIGURED` contract codes, migration `a1c74f9d3e02`.
Commit `439e6e6` (merged in `66ec9bc`, verified 61 passed).

### Phase 4A — Secure ZIP ingestion and AST analysis (branch `madvith`)

**ZIP ingestion** (`app/services/ingestion/zip_archive.py`)
- Real-ZIP validation (magic bytes + readable central directory), then per-entry
  validation: absolute paths, `..` traversal, backslashes, NUL bytes, over-long
  names, duplicate normalized names, symlink entries, encrypted entries.
- Limits: file count, per-file size, total uncompressed size, and
  compression-ratio (zip-bomb) checks above a 1 MiB threshold so legitimately
  compressible source is not rejected; all limits come from settings.
- Documented exclusions (`.git`, `__pycache__`, virtualenvs, caches,
  `node_modules`) are skipped and reported; every write is confined to the
  snapshot directory; content is never imported, executed, or installed.
- `POST /api/v1/projects/from-upload` streams the multipart upload with a hard
  size cap (413 `UPLOAD_TOO_LARGE`), validates the archive (400
  `UPLOAD_INVALID`), and creates a project + immutable upload snapshot.

**AST extraction** (`app/services/analysis/parser.py`)
- Standard-library `ast` only; PEP 263 encoding declarations honored; per-file
  syntax errors, decode failures, and oversized files become diagnostics while
  the rest of the snapshot continues to parse.
- Extracts modules, classes (bases), functions, async functions, methods, nested
  classes/functions, decorators, imports, and call expressions with
  snapshot-relative file paths and line/column spans.
- Qualified names follow the contract: `module:Class.method`,
  `module:function`, `module:function.nested`.
- Deterministic symbol IDs: SHA-256 of
  `analysis|file|kind|qualified_name|start_line|end_line` (40 hex chars), so IDs
  are collision-safe and stable within a run; repeated parses of the same
  snapshot produce identical IDs.
- Call expressions are attributed to the nearest enclosing symbol only (nested
  definitions own their own calls) and stored as expressions — no dependency is
  invented before the resolver phase.

**Analysis run + catalogue** (`app/services/analysis/service.py`,
`app/repositories/analysis.py`, `app/api/v1/analyses.py`)
- `POST /snapshots/{id}/analyses` creates a run (`queued` → `running` →
  `completed` / `completed_with_warnings` / `failed`), parses every `*.py` file,
  and persists `source_files` metadata, `symbols`, `symbol_calls`, and
  `analysis_diagnostics` scoped to the run (cascading FKs).
- `GET /analyses/{id}` returns state, counters (`python_file_count`,
  `symbol_count`, `edge_count=0` until Phase 5A), timestamps, versions, and a
  diagnostics summary (`syntax_errors`, `skipped_files`; resolver counters are
  omitted rather than reported as fabricated zeros).
- `GET /analyses/{id}/symbols` supports `q` (short/qualified name),
  `kind` filter, and bounded pagination with deterministic ordering
  `(file_path, start_line, start_column, qualified_name)`.
- `GET /projects/{id}` and `GET /projects` now expose `latest_analysis` (real
  run state) alongside `latest_snapshot`.
- Both providers feed the same pipeline: GitHub imports and ZIP uploads produce
  identical snapshot storage + identical symbol catalogues (tested).

## Files/modules added or changed (Phase 4A)

- Added: `app/models/analysis.py`, `app/repositories/analysis.py`,
  `app/services/analysis/{parser.py,service.py}`,
  `app/services/ingestion/zip_archive.py`, `app/api/v1/analyses.py`,
  `alembic/versions/b7f31c8e5a41_analysis_records.py`,
  `tests/unit/{test_zip_extraction.py,test_parser.py}`,
  `tests/integration/test_upload_and_analysis.py`.
- Changed: `app/core/config.py` (limits, versions), `app/models/__init__.py`,
  `app/repositories/projects.py` (`SnapshotRepository.get`),
  `app/services/projects/service.py` (`create_from_upload`),
  `app/services/ingestion/archive.py` (shared `validate_entry_name` /
  `is_excluded` helpers), `app/api/deps.py` (analysis bundle),
  `app/api/v1/projects.py` (upload route, `latest_analysis`),
  `app/schemas/serializers.py` (`analysis_view`, `symbol_view`),
  `app/main.py` (router), `backend/pyproject.toml` (`python-multipart`),
  `backend/.env.example`, `docs/architecture.md`, `IMPLEMENTATION_STATUS.md`,
  `tests/conftest.py` (ZIP fixtures, sample project).
- No frontend files touched; no root config touched.

## Exact commands executed and actual results

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **107 passed** (61 pre-existing + 46 new: 12 ZIP-safety unit, 16 parser unit, 18 upload/analysis integration; 1 starlette deprecation warning) |
| `DATABASE_URL=sqlite:////tmp/flowlens_mig4a.db .venv/bin/python -m alembic upgrade head` (clean DB) | All three migrations applied (`48e88e749069` → `a1c74f9d3e02` → `b7f31c8e5a41`); 14 tables present incl. `source_files`, `symbols`, `symbol_calls`, `analysis_diagnostics` |
| `DATABASE_URL=… .venv/bin/python -m alembic check` | "No new upgrade operations detected" — no model/migration drift |
| `uv pip install --python .venv/bin/python python-multipart` | Installed `python-multipart==0.0.34` (required for upload form parsing) |

## Known issues, blockers, assumptions

- **Analysis runs execute inline** (synchronous) for the MVP; the API still
  models the full lifecycle so a worker/queue can replace the inline call
  without a contract change. A crash mid-run marks the run `failed` with
  `error_code=INTERNAL_ERROR` rather than raising.
- **No dependency edges yet**: `edge_count` is 0 and resolver counters are
  omitted from the diagnostics summary until Phase 5A.
- Re-running analysis on the same snapshot creates a **new** run with its own
  symbol IDs (IDs are deterministic *within* a run, per the contract's
  "stable ID within analysis" wording).
- Very large repositories are bounded by `ANALYSIS_MAX_SYMBOLS`; hitting the
  budget adds a `SYMBOL_LIMIT_REACHED` warning instead of silently truncating.
- `POST /projects` (bare project) still creates an upload-provider project
  without a snapshot; only `/from-upload` and `/from-github` create snapshots.
- Orphaned snapshot directories from failed imports/extractions remain until
  storage GC lands (Phase 8); DB rows roll back so no API exposes them.
- Frontend ZIP upload (Phase 3B) now has a real backend endpoint; analysis UI
  is Phase 4B.

## API/schema/database changes

- New endpoints: `POST /api/v1/projects/from-upload` (multipart `file`, optional
  `name`), `POST /api/v1/snapshots/{snapshot_id}/analyses` (202),
  `GET /api/v1/analyses/{analysis_id}`,
  `GET /api/v1/analyses/{analysis_id}/symbols` (`page`, `per_page`, `q`, `kind`).
- `Project.latest_analysis` is now populated (previously always `null`).
- New tables: `source_files`, `symbols`, `symbol_calls`,
  `analysis_diagnostics`; migration `b7f31c8e5a41` (down revision
  `a1c74f9d3e02`). Symbol/call/import metadata not in the public `Symbol`
  schema (decorators, bases, imports, calls) stays internal for Phase 5A.
- No contract changes required for this phase; contract routes/schemas already
  covered these endpoints.

## Next smallest actionable task

Phase 5A start: resolver interface + lexical/import resolution over the stored
`symbols`/`symbol_calls`/`imports`, persisting `dependency_edges` with type,
endpoints, resolver name, confidence, and source evidence — explicit
unresolved/ambiguous diagnostics, no guessed edges.
