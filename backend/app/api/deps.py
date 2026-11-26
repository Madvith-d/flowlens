"""API dependencies: DB session, auth service, and session resolution."""

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models.auth import UserSession
from app.models.user import User
from app.repositories.auth import OAuthStateRepository, UserSessionRepository
from app.repositories.analysis import (
    AnalysisRepository,
    DependencyEdgeRepository,
    DiagnosticRepository,
    SourceFileRepository,
    SymbolCallRepository,
    SymbolRepository,
)
from app.repositories.github import GitHubCredentialRepository
from app.repositories.installations import GitHubInstallationRepository
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.repositories.users import UserRepository
from app.services.analysis.service import AnalysisService
from app.services.analysis.graph import AnalysisGraphService
from app.services.auth.service import AUTH_REQUIRED, AuthService
from app.services.github.service import GitHubInstallationService
from app.services.ingestion.storage import SnapshotStorage
from app.services.projects.service import ProjectService


def get_settings(request: Request):
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class AuthBundle:
    """Request-scoped service/socket for auth endpoints and dependencies."""

    def __init__(self, request: Request, db: Session):
        self.request = request
        self.db = db
        settings = request.app.state.settings
        self.settings = settings
        self.service = AuthService(
            settings=settings,
            provider=request.app.state.github_provider,
            user_repo=UserRepository(db),
            state_repo=OAuthStateRepository(db),
            session_repo=UserSessionRepository(db),
            credential_repo=GitHubCredentialRepository(db),
        )

    def cookie_value(self) -> str | None:
        return self.request.cookies.get(self.settings.session_cookie_name)

    def resolve_session(self) -> tuple[UserSession, User] | None:
        value = self.cookie_value()
        if not value:
            return None
        return self.service.resolve_session(value)


def get_auth_bundle(request: Request, db: Session = Depends(get_db)) -> AuthBundle:
    return AuthBundle(request, db)


def get_current_user(bundle: AuthBundle = Depends(get_auth_bundle)) -> User:
    """Dependency for authenticated endpoints; raises the AUTH_REQUIRED envelope."""
    resolved = bundle.resolve_session()
    if resolved is None:
        raise AUTH_REQUIRED
    _session, user = resolved
    return user


class GitHubBundle:
    """Request-scoped wiring for installation/repository endpoints."""

    def __init__(self, request: Request, db: Session, user: User):
        self.request = request
        self.db = db
        self.settings = request.app.state.settings
        self.user = user
        self.installation_service = GitHubInstallationService(
            settings=self.settings,
            app_client=request.app.state.github_app_client,
            state_repo=OAuthStateRepository(db),
            credential_repo=GitHubCredentialRepository(db),
            installation_repo=GitHubInstallationRepository(db),
        )


def get_github_bundle(
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
) -> GitHubBundle:
    return GitHubBundle(request, db, user)


class ProjectsBundle:
    """Request-scoped wiring for project endpoints."""

    def __init__(self, request: Request, db: Session, user: User):
        self.request = request
        self.db = db
        self.settings = request.app.state.settings
        self.user = user
        self.service = ProjectService(
            settings=self.settings,
            app_client=request.app.state.github_app_client,
            project_repo=ProjectRepository(db),
            snapshot_repo=SnapshotRepository(db),
            credential_repo=GitHubCredentialRepository(db),
            storage=SnapshotStorage(self.settings),
        )
        self.analysis_service = AnalysisService(
            settings=self.settings,
            project_repo=ProjectRepository(db),
            snapshot_repo=SnapshotRepository(db),
            analysis_repo=AnalysisRepository(db),
            source_file_repo=SourceFileRepository(db),
            symbol_repo=SymbolRepository(db),
            call_repo=SymbolCallRepository(db),
            edge_repo=DependencyEdgeRepository(db),
            diagnostic_repo=DiagnosticRepository(db),
            storage=SnapshotStorage(self.settings),
        )


def get_projects_bundle(
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
) -> ProjectsBundle:
    return ProjectsBundle(request, db, user)


class AnalysisBundle:
    """Request-scoped wiring for analysis endpoints."""

    def __init__(self, request: Request, db: Session, user: User):
        self.request = request
        self.db = db
        self.settings = request.app.state.settings
        self.user = user
        self.service = AnalysisService(
            settings=self.settings,
            project_repo=ProjectRepository(db),
            snapshot_repo=SnapshotRepository(db),
            analysis_repo=AnalysisRepository(db),
            source_file_repo=SourceFileRepository(db),
            symbol_repo=SymbolRepository(db),
            call_repo=SymbolCallRepository(db),
            edge_repo=DependencyEdgeRepository(db),
            diagnostic_repo=DiagnosticRepository(db),
            storage=SnapshotStorage(self.settings),
        )


def get_analysis_bundle(
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
) -> AnalysisBundle:
    return AnalysisBundle(request, db, user)


class GraphBundle:
    """Request-scoped wiring for graph query endpoints."""

    def __init__(self, request: Request, db: Session, user: User):
        self.request = request
        self.db = db
        self.settings = request.app.state.settings
        self.user = user
        self.service = AnalysisGraphService(
            settings=self.settings,
            project_repo=ProjectRepository(db),
            snapshot_repo=SnapshotRepository(db),
            analysis_repo=AnalysisRepository(db),
            symbol_repo=SymbolRepository(db),
            edge_repo=DependencyEdgeRepository(db),
        )


def get_graph_bundle(
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
) -> GraphBundle:
    return GraphBundle(request, db, user)
