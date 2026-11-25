"""Project service: GitHub import, refresh, disconnect, and listing (Phase 3A).

Every GitHub-sourced operation verifies, server-side:
1. the installation is accessible to the authenticated user,
2. the repository is accessible through that installation,
3. the ref resolves to a real commit SHA,

before any source is fetched or persisted. Snapshots are immutable: refresh
always creates a new snapshot; nothing historical is ever mutated.
"""

import logging

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_secret
from app.models.projects import Project, SourceSnapshot
from app.models.user import User
from app.repositories.github import GitHubCredentialRepository
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.github.app_client import (
    INSTALLATION_ACCESS_DENIED,
    GitHubAppClient,
    RepositoryInfo,
    ResolvedRef,
)
from app.services.ingestion.archive import (
    UnsafeArchiveError,
    archive_content_hash,
    extract_tar_gz,
)
from app.services.ingestion.storage import SnapshotStorage
from app.services.ingestion.zip_archive import extract_zip, looks_like_zip

logger = logging.getLogger("flowlens.projects")

PROJECT_NOT_FOUND = ApiError(
    status_code=404,
    code="PROJECT_NOT_FOUND",
    message="Project not found.",
)
GITHUB_NOT_CONNECTED = ApiError(
    status_code=409,
    code="CONFLICT",
    message="This project has no connected GitHub repository.",
)
UPLOAD_INVALID = ApiError(
    status_code=400,
    code="UPLOAD_INVALID",
    message="The repository archive could not be imported.",
)


class ProjectService:
    def __init__(
        self,
        settings: Settings,
        app_client: GitHubAppClient,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        credential_repo: GitHubCredentialRepository,
        storage: SnapshotStorage,
    ) -> None:
        self._settings = settings
        self._app_client = app_client
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._credentials = credential_repo
        self._storage = storage

    # ------------------------------------------------------------- verification
    def _user_access_token(self, user: User) -> str:
        credential = self._credentials.get_active(user.id)
        if credential is None:
            from app.services.github.app_client import USER_TOKEN_UNAVAILABLE

            raise USER_TOKEN_UNAVAILABLE
        return decrypt_secret(credential.encrypted_access_token, self._settings)

    def _verify_installation(self, user: User, installation_id: int):
        """The installation must appear in the user's own installations."""
        installations = self._app_client.list_user_installations(self._user_access_token(user))
        matched = next(
            (info for info in installations if info.installation_id == installation_id), None
        )
        if matched is None:
            logger.info(
                "installation not accessible to user",
                extra={"context": {"installation_id": int(installation_id)}},
            )
            raise INSTALLATION_ACCESS_DENIED
        return matched

    # ------------------------------------------------------------- source import
    def _create_github_snapshot(
        self,
        project: Project,
        *,
        repository: RepositoryInfo,
        resolved: ResolvedRef,
        installation_id: int,
    ) -> SourceSnapshot:
        """Fetch the archive, store it immutably, and persist provenance."""
        token = self._app_client.build_installation_token(
            installation_id, repository_ids=[repository.repository_id]
        )
        archive_bytes = self._app_client.download_archive(
            token.token, repository.full_name, resolved.commit_sha
        )
        content_hash = archive_content_hash(archive_bytes)
        # Provenance is recorded with the snapshot before extraction; if
        # extraction fails the snapshot keeps `file_count` 0 and no analysis
        # can claim it.
        snapshot = self._snapshots.create(
            project_id=project.id,
            provider="github",
            content_hash=content_hash,
            file_count=0,
            github_repository_id=repository.repository_id,
            github_full_name=repository.full_name,
            github_ref=resolved.ref,
            github_commit_sha=resolved.commit_sha,
        )
        try:
            snapshot_dir = self._storage.snapshot_dir(snapshot.id)
            result = extract_tar_gz(
                archive_bytes,
                snapshot_dir,
                max_file_count=self._settings.snapshot_max_file_count,
                max_total_bytes=self._settings.snapshot_max_uncompressed_bytes,
            )
        except (UnsafeArchiveError, OSError) as exc:
            logger.warning(
                "github archive rejected during extraction",
                extra={"context": {"error": type(exc).__name__}},
            )
            raise UPLOAD_INVALID from exc
        snapshot.file_count = len(result.stored_paths)
        self._snapshots.flush()
        logger.info(
            "github snapshot stored",
            extra={
                "context": {
                    "snapshot_id": snapshot.id,
                    "files": len(result.stored_paths),
                    "skipped": len(result.skipped_paths),
                }
            },
        )
        return snapshot

    def create_from_github(
        self,
        user: User,
        *,
        repository_id: int,
        installation_id: int,
        ref: str,
        name: str | None,
    ) -> Project:
        """Import a repository the user and installation are both allowed to access."""
        self._verify_installation(user, installation_id)
        token = self._app_client.build_installation_token(installation_id)
        # get_repository maps GitHub 404 → REPOSITORY_ACCESS_DENIED:
        # browser-supplied repository IDs are never trusted as proof of access.
        repository = self._app_client.get_repository(token.token, repository_id)
        resolved = self._app_client.resolve_ref(token.token, repository.full_name, ref)
        project = self._projects.create(
            user_id=user.id,
            name=(name or repository.full_name)[:200],
            source_provider="github",
        )
        self._projects.attach_github_connection(
            project,
            installation_id=installation_id,
            repository_id=repository.repository_id,
            full_name=repository.full_name,
            ref=resolved.ref,
            visibility=repository.visibility,
            default_branch=repository.default_branch,
        )
        self._create_github_snapshot(
            project, repository=repository, resolved=resolved, installation_id=installation_id
        )
        return project

    # ---------------------------------------------------------------- refresh
    def refresh(self, user: User, project_id: str, ref: str | None = None) -> SourceSnapshot:
        """Refresh a connected GitHub project into a NEW immutable snapshot."""
        project = self._require_github_project(user, project_id, require_connected=True)
        target_ref = ref or project.github_ref or project.github_default_branch
        if not target_ref:
            raise GITHUB_NOT_CONNECTED
        self._verify_installation(user, project.github_installation_id)
        token = self._app_client.build_installation_token(
            project.github_installation_id, repository_ids=[project.github_repository_id]
        )
        repository = self._app_client.get_repository(
            token.token, project.github_repository_id
        )
        resolved = self._app_client.resolve_ref(token.token, repository.full_name, target_ref)
        snapshot = self._create_github_snapshot(
            project,
            repository=repository,
            resolved=resolved,
            installation_id=project.github_installation_id,
        )
        if ref and ref != project.github_ref:
            self._projects.update_github_ref(project, resolved.ref)
        return snapshot

    # -------------------------------------------------------------- disconnect
    def disconnect(self, user: User, project_id: str) -> None:
        """Remove future access; existing snapshots and reports are retained."""
        project = self._require_github_project(user, project_id, require_connected=True)
        self._projects.mark_disconnected(project)
        logger.info(
            "github connection disconnected",
            extra={"context": {"project_id": project.id}},
        )

    # --------------------------------------------------------------- uploads
    def create_from_upload(
        self, user: User, *, archive_bytes: bytes, filename: str, name: str | None
    ) -> Project:
        """Create a project + immutable snapshot from an uploaded ZIP archive.

        The archive is inspected and extracted with strict limits; its content
        is never executed or imported.
        """
        if not looks_like_zip(archive_bytes):
            raise UPLOAD_INVALID
        project = self._projects.create(
            user_id=user.id,
            name=(name or filename.rsplit("/", 1)[-1].rsplit(".zip", 1)[0] or "Uploaded project")[:200],
            source_provider="upload",
        )
        snapshot = self._snapshots.create(
            project_id=project.id,
            provider="upload",
            content_hash=archive_content_hash(archive_bytes),
            file_count=0,
        )
        try:
            snapshot_dir = self._storage.snapshot_dir(snapshot.id)
            result = extract_zip(
                archive_bytes,
                snapshot_dir,
                max_file_count=self._settings.snapshot_max_file_count,
                max_total_bytes=self._settings.snapshot_max_uncompressed_bytes,
                max_file_bytes=self._settings.snapshot_max_file_bytes,
                max_compression_ratio=self._settings.snapshot_max_compression_ratio,
            )
        except (UnsafeArchiveError, OSError) as exc:
            logger.info(
                "upload rejected",
                extra={"context": {"error": type(exc).__name__}},
            )
            raise UPLOAD_INVALID from exc
        snapshot.file_count = len(result.stored_paths)
        self._snapshots.flush()
        logger.info(
            "upload snapshot stored",
            extra={
                "context": {
                    "snapshot_id": snapshot.id,
                    "files": len(result.stored_paths),
                    "skipped": len(result.skipped_paths),
                }
            },
        )
        return project

    # ------------------------------------------------------------------ queries
    def create_bare(self, user: User, name: str) -> Project:
        """Create a project record without a snapshot (upload phase attaches it)."""
        return self._projects.create(user_id=user.id, name=name, source_provider="upload")

    def get_project(self, user: User, project_id: str) -> Project:
        project = self._projects.get_owned(project_id, user.id)
        if project is None:
            raise PROJECT_NOT_FOUND
        return project

    def list_projects(self, user: User, page: int, per_page: int) -> tuple[list[Project], int]:
        return self._projects.list_owned(user.id, page, per_page)

    def list_snapshots(
        self, user: User, project_id: str, page: int, per_page: int
    ) -> tuple[list[SourceSnapshot], int]:
        project = self.get_project(user, project_id)
        return self._snapshots.list_for_project(project.id, page, per_page)

    def latest_snapshot(self, project: Project) -> SourceSnapshot | None:
        return self._projects.latest_snapshot(project.id)

    # --------------------------------------------------------------- internals
    def _require_github_project(
        self, user: User, project_id: str, *, require_connected: bool
    ) -> Project:
        project = self._projects.get_owned(project_id, user.id)
        if project is None:
            raise PROJECT_NOT_FOUND
        if project.source_provider != "github":
            raise GITHUB_NOT_CONNECTED
        if require_connected and project.disconnected_at is not None:
            raise GITHUB_NOT_CONNECTED
        return project
