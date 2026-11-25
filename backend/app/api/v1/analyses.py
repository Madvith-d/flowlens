"""Analysis routes: start a run, read status, and search the symbol catalog.

Static analysis only — snapshot source is parsed, never executed.
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analysis_bundle, get_current_user
from app.schemas.serializers import analysis_view, pagination_view, symbol_view

logger = logging.getLogger("flowlens.analysis_routes")

router = APIRouter(prefix="/api/v1", tags=["analyses"])


@router.post("/snapshots/{snapshot_id}/analyses", status_code=202)
def start_analysis(
    snapshot_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_analysis_bundle),
):
    """Run static analysis for an owned snapshot.

    The run executes inline for the MVP; the returned state is the observed
    result (`completed`, `completed_with_warnings`, or `failed`), never a
    fabricated `running`/`queued` state.
    """
    service = bundle.service
    run = service.create_run(user, snapshot_id)
    return analysis_view(run, service.diagnostics_summary(run.id))


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_analysis_bundle),
):
    service = bundle.service
    run = service.get(user, analysis_id)
    return analysis_view(run, service.diagnostics_summary(run.id))


@router.get("/analyses/{analysis_id}/symbols")
def list_symbols(
    analysis_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    kind: str | None = Query(default=None),
    user=Depends(get_current_user),
    bundle=Depends(get_analysis_bundle),
):
    """Searchable, deterministic, paginated symbol catalog."""
    symbols, total = bundle.service.list_symbols(
        user, analysis_id, query=q, kind=kind, page=page, per_page=per_page
    )
    return {
        "items": [symbol_view(symbol) for symbol in symbols],
        "pagination": pagination_view(page, per_page, total),
    }
