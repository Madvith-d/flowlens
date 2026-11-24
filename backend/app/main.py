"""FlowLens backend application shell.

Scaffold entry point only: application wiring, routes and services are
implemented in later phases on `feature/madvith-backend-core`.
"""

from fastapi import FastAPI

app = FastAPI(
    title="FlowLens API",
    version="0.1.0",
    description="Code dependency and change impact visualizer — backend API.",
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready() -> dict[str, str]:
    """Readiness probe. Extended with dependency checks in later phases."""
    return {"status": "ready"}
