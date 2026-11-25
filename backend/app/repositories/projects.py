"""Project and snapshot data access with strict user-ownership scopes."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.projects import Project, SourceSnapshot
from app.repositories.base import BaseRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRepository(BaseRepository):
    def create(
        self,
        user_id: str,
        name: str,
        source_provider: str,
    ) -> Project:
        project = Project(user_id=user_id, name=name, source_provider=source_provider)
        self.session.add(project)
        self.session.flush()
        return project

    def get_owned(self, project_id: str, user_id: str) -> Project | None:
        """Ownership is enforced at the data-access layer, not only in the UI."""
        project = self.session.get(Project, project_id)
        if project is None or project.user_id != user_id:
            return None
        return project

    def list_owned(self, user_id: str, page: int, per_page: int) -> tuple[list[Project], int]:
        total = self.session.scalar(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        ) or 0
        projects = self.session.scalars(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc(), Project.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return list(projects), int(total)

    def attach_github_connection(
        self,
        project: Project,
        *,
        installation_id: int,
        repository_id: int,
        full_name: str,
        ref: str,
        visibility: str | None,
        default_branch: str | None,
    ) -> Project:
        project.github_installation_id = installation_id
        project.github_repository_id = repository_id
        project.github_full_name = full_name
        project.github_ref = ref
        project.github_visibility = visibility
        project.github_default_branch = default_branch
        project.disconnected_at = None
        self.session.flush()
        return project

    def update_github_ref(self, project: Project, ref: str) -> Project:
        project.github_ref = ref
        self.session.flush()
        return project

    def mark_disconnected(self, project: Project) -> Project:
        project.disconnected_at = utc_now()
        self.session.flush()
        return project

    def latest_snapshot(self, project_id: str) -> SourceSnapshot | None:
        return self.session.scalar(
            select(SourceSnapshot)
            .where(SourceSnapshot.project_id == project_id)
            .order_by(SourceSnapshot.created_at.desc(), SourceSnapshot.id.desc())
            .limit(1)
        )


class SnapshotRepository(BaseRepository):
    def create(
        self,
        project_id: str,
        *,
        provider: str,
        content_hash: str,
        file_count: int,
        github_repository_id: int | None = None,
        github_full_name: str | None = None,
        github_ref: str | None = None,
        github_commit_sha: str | None = None,
    ) -> SourceSnapshot:
        snapshot = SourceSnapshot(
            project_id=project_id,
            provider=provider,
            content_hash=content_hash,
            file_count=file_count,
            github_repository_id=github_repository_id,
            github_full_name=github_full_name,
            github_ref=github_ref,
            github_commit_sha=github_commit_sha,
            imported_at=utc_now(),
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def list_for_project(
        self, project_id: str, page: int, per_page: int
    ) -> tuple[list[SourceSnapshot], int]:
        total = (
            self.session.scalar(
                select(func.count(SourceSnapshot.id)).where(SourceSnapshot.project_id == project_id)
            )
            or 0
        )
        snapshots = self.session.scalars(
            select(SourceSnapshot)
            .where(SourceSnapshot.project_id == project_id)
            .order_by(SourceSnapshot.created_at.desc(), SourceSnapshot.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return list(snapshots), int(total)
