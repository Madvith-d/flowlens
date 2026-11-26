"""Impact routes (Phase 6A): impact queries with explainable risk score."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_impact_bundle

logger = logging.getLogger("flowlens.impact_routes")

router = APIRouter(prefix="/api/v1", tags=["impact"])


class ImpactRequest(BaseModel):
    target_ids: list[str] = Field(min_length=1, max_length=10)
    direction: str = Field(pattern="^(upstream|downstream|both)$", default="both")
    max_depth: int = Field(ge=1, le=10, default=3)


@router.post("/analyses/{analysis_id}/impact")
def compute_impact(
    analysis_id: str,
    request: ImpactRequest,
    user=Depends(get_current_user),
    bundle=Depends(get_impact_bundle),
):
    """Upstream/downstream impact for one or more targets with risk breakdown.

    Paths are representative shortest paths (ordered real edge IDs) and the
    risk score is a versioned prioritization heuristic — never a failure
    probability.
    """
    return bundle.service.impact(
        user,
        analysis_id,
        target_ids=request.target_ids,
        direction=request.direction,
        max_depth=request.max_depth,
    )
