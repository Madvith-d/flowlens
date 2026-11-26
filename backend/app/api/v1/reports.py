"""Report routes (Phase 7A): Markdown report generation and download."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_report_bundle
from app.schemas.serializers import report_view

logger = logging.getLogger("flowlens.report_routes")

router = APIRouter(prefix="/api/v1", tags=["reports"])


class ReportRequest(BaseModel):
    target_ids: list[str] | None = Field(default=None, max_length=10)
    direction: str = Field(pattern="^(upstream|downstream|both)$", default="both")
    max_depth: int = Field(ge=1, le=10, default=3)


@router.post("/analyses/{analysis_id}/reports", status_code=201)
def generate_report(
    analysis_id: str,
    request: ReportRequest | None = None,
    user=Depends(get_current_user),
    bundle=Depends(get_report_bundle),
):
    """Generate a deterministic Markdown report from stored analysis data."""
    body = request or ReportRequest()
    report = bundle.service.generate(
        user,
        analysis_id,
        target_ids=body.target_ids,
        direction=body.direction,
        max_depth=body.max_depth,
    )
    return report_view(report)


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_report_bundle),
):
    """Download the stored Markdown file for a generated report."""
    return bundle.download(report_id)
