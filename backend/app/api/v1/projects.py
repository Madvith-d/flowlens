"""Project routes: list/detail, GitHub import, refresh, disconnect, snapshots.

All routes require an authenticated session and enforce ownership through the
service layer. Responses follow the Project/Snapshot contract schemas.
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_projects_bundle
from app.schemas.serializers import pagination_view, project_view, snapshot_view
from app.services.projects.service import ProjectService

logger = logging.getLogger("flowlens.projects_routes")

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


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
    return {
        "items": [
            project_view(project, latest_snapshot=service.latest_snapshot(project))
            for project in projects
        ],
        "pagination": pagination_view(page, per_page, total),
    }


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
    return project_view(project, latest_snapshot=bundle.service.latest_snapshot(project))


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
