"""Project routes: list/detail, ZIP upload, GitHub import, refresh, disconnect.

All routes require an authenticated session and enforce ownership through the
service layer. Responses follow the Project/Snapshot contract schemas.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_projects_bundle
from app.core.errors import ApiError
from app.schemas.serializers import (
    analysis_view,
    pagination_view,
    project_view,
    snapshot_view,
)
from app.services.projects.service import ProjectService

logger = logging.getLogger("flowlens.projects_routes")

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

UPLOAD_TOO_LARGE = ApiError(
    status_code=413,
    code="UPLOAD_TOO_LARGE",
    message="The uploaded archive exceeds the configured size limit.",
)
UPLOAD_INVALID = ApiError(
    status_code=400,
    code="UPLOAD_INVALID",
    message="The uploaded archive is not a valid ZIP file.",
)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CreateFromGithubRequest(BaseModel):
    repository_id: int
    installation_id: int
    ref: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=200)


class RefreshRequest(BaseModel):
    ref: str | None = Field(default=None, max_length=255)


@router.get("")
def list_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    service: ProjectService = bundle.service
    projects, total = service.list_projects(user, page, per_page)
    latest = bundle.analysis_service.latest_for_projects([project.id for project in projects])
    return {
        "items": [
            project_view(
                project,
                latest_snapshot=service.latest_snapshot(project),
                latest_analysis=(
                    analysis_view(latest[project.id], {})
                    if project.id in latest
                    else None
                ),
            )
            for project in projects
        ],
        "pagination": pagination_view(page, per_page, total),
    }


@router.post("/from-upload", status_code=201)
async def create_project_from_upload(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    """Create a project and immutable snapshot from a ZIP upload.

    The archive is size-limited while reading, then validated and extracted with
    traversal/symlink/size protections. Uploaded code is never executed.
    """
    limit = bundle.settings.snapshot_max_archive_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UPLOAD_TOO_LARGE
        chunks.append(chunk)
    archive_bytes = b"".join(chunks)
    if not archive_bytes:
        raise UPLOAD_INVALID
    project = bundle.service.create_from_upload(
        user,
        archive_bytes=archive_bytes,
        filename=file.filename or "upload.zip",
        name=name,
    )
    return project_view(project, latest_snapshot=bundle.service.latest_snapshot(project))


@router.post("", status_code=201)
def create_project(
    payload: CreateProjectRequest,
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    """Create a bare project record (source attached by a later phase/endpoint)."""
    project = bundle.service.create_bare(user, payload.name.strip()[:200])
    return project_view(project)


@router.post("/from-github", status_code=201)
def create_from_github(
    payload: CreateFromGithubRequest,
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    """Import a GitHub repository into a new project + immutable snapshot."""
    project = bundle.service.create_from_github(
        user,
        repository_id=payload.repository_id,
        installation_id=payload.installation_id,
        ref=payload.ref,
        name=payload.name,
    )
    return project_view(
        project, latest_snapshot=bundle.service.latest_snapshot(project)
    )


@router.get("/{project_id}")
def get_project(
    project_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    project = bundle.service.get_project(user, project_id)
    latest_run = bundle.analysis_service.latest_for_project(project.id)
    return project_view(
        project,
        latest_snapshot=bundle.service.latest_snapshot(project),
        latest_analysis=analysis_view(latest_run, {}) if latest_run else None,
    )


@router.post("/{project_id}/refresh", status_code=201)
def refresh_project(
    project_id: str,
    payload: RefreshRequest | None = None,
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    """Create a NEW immutable snapshot from the connected repository."""
    snapshot = bundle.service.refresh(user, project_id, ref=payload.ref if payload else None)
    return snapshot_view(snapshot)


@router.delete("/{project_id}/github-connection", status_code=204)
def disconnect_github_connection(
    project_id: str,
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    """Disconnect future access; existing snapshots/reports are retained."""
    bundle.service.disconnect(user, project_id)
    return None


@router.get("/{project_id}/snapshots")
def list_snapshots(
    project_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user=Depends(get_current_user),
    bundle=Depends(get_projects_bundle),
):
    snapshots, total = bundle.service.list_snapshots(user, project_id, page, per_page)
    return {
        "items": [snapshot_view(snapshot) for snapshot in snapshots],
        "pagination": pagination_view(page, per_page, total),
    }
