# FlowLens

Code dependency & change impact visualizer for Python projects. Sign in with
GitHub, import a repository (via the FlowLens GitHub App) or upload a ZIP,
analyze it statically, explore the dependency graph, simulate the impact of a
change, and export a Markdown report.

FlowLens never executes analyzed source code.

## Repository layout

- `backend/` — FastAPI backend (owner: Madvith)
- `frontend/` — Next.js frontend (owner: Sameeksha)
- `contracts/openapi.yaml` — shared API contract (authoritative copy; changes coordinated)
- `docs/` — architecture and GitHub App setup documentation
- `sample-project/` — synthetic Python fixture project

## Development setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in values
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/api/v1/health`

Run tests:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend runs at `http://localhost:3000`.

### Docker Compose (optional baseline)

```bash
docker compose up
```

## Documentation

- `product.md` — product requirements and behavior
- `scope.md` — MVP boundary and acceptance criteria
- `phases.md` — implementation phases and branch workflow
- `agent-madvith.md` / `agent-sameeksha.md` — contributor instructions
- `docs/architecture.md` — architecture overview
- `docs/github-app-setup.md` — GitHub App configuration guide

## Branching

- `main` — shared scaffold commit only; no direct feature development
- `feature/madvith-backend-core` — backend workstream
- `feature/sameeksha-frontend-app` — frontend workstream
