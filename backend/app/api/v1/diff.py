"""Diff routes (Phase 7A): unified diff mapping onto stored symbols."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_diff_bundle

logger = logging.getLogger("flowlens.diff_routes")

router = APIRouter(prefix="/api/v1", tags=["diff"])


class DiffRequest(BaseModel):
    unified_diff: str = Field(min_length=1, max_length=524_288)


@router.post("/analyses/{analysis_id}/diff")
def analyze_diff(
    analysis_id: str,
    request: DiffRequest,
    user=Depends(get_current_user),
    bundle=Depends(get_diff_bundle),
):
    """Map a unified diff to changed symbols and a combined impact result."""
    return bundle.service.analyze(user, analysis_id, request.unified_diff)
