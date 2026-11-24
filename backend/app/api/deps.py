"""API dependencies: DB session, auth service, and session resolution."""

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models.auth import UserSession
from app.models.user import User
from app.repositories.auth import OAuthStateRepository, UserSessionRepository
from app.repositories.github import GitHubCredentialRepository
from app.repositories.users import UserRepository
from app.services.auth.service import AuthService


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
