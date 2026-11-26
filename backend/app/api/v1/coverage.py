"""Coverage routes (Phase 7A): attach a Coverage.py JSON artifact."""

import logging

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user, get_coverage_bundle

logger = logging.getLogger("flowlens.coverage_routes")

router = APIRouter(prefix="/api/v1", tags=["coverage"])


@router.post("/analyses/{analysis_id}/coverage")
async def attach_coverage(
    analysis_id: str,
    request: Request,
    user=Depends(get_current_user),
    bundle=Depends(get_coverage_bundle),
):
    """Validate and attach Coverage.py JSON; missing coverage stays unknown."""
    try:
        payload = await request.json()
    except Exception:
        payload = None
    return bundle.service.attach(user, analysis_id, payload)
