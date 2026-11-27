"""Authentication service: GitHub App user authorization, sessions, logout.

All GitHub credential material stays server-side and encrypted at rest.
The callback never touches the client with tokens; only the signed,
HttpOnly application session cookie is issued.
"""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    sign_value,
    verify_signed,
)
from app.db.base import ensure_aware
from app.models.auth import UserSession
from app.models.user import User
from app.repositories.auth import OAuthStateRepository, UserSessionRepository
from app.repositories.github import GitHubCredentialRepository
from app.repositories.users import UserRepository
from app.services.github.client import GitHubOAuthProvider

logger = logging.getLogger("flowlens.auth")

INVALID_STATE = ApiError(
    status_code=401,
    code="OAUTH_STATE_INVALID",
    message="The sign-in request could not be validated. Please start again.",
)

AUTH_CALLBACK_FAILED = ApiError(
    status_code=401,
    code="GITHUB_TOKEN_ERROR",
    message="GitHub sign-in failed. Please try again.",
)

AUTH_REQUIRED = ApiError(
    status_code=401,
    code="AUTH_REQUIRED",
    message="Authentication required.",
)


def active_access_token(
    user: User,
    settings: Settings,
    provider: GitHubOAuthProvider,
    credential_repo: GitHubCredentialRepository,
) -> str:
    """Return a usable GitHub access token, refreshing an expired one.

    Expired access tokens are refreshed with the stored (encrypted) refresh
    token and the rotated pair is persisted. If no credential exists or the
    refresh fails, the stable GITHUB_TOKEN_ERROR (401) envelope is raised so
    the client prompts a fresh sign-in. Refresh tokens themselves are never
    returned or logged.
    """
    from app.services.github.app_client import USER_TOKEN_UNAVAILABLE

    credential = credential_repo.get_active(user.id)
    if credential is None:
        raise USER_TOKEN_UNAVAILABLE
    access_token = decrypt_secret(credential.encrypted_access_token, settings)
    if credential.expires_at is None or ensure_aware(credential.expires_at) > datetime.now(
        timezone.utc
    ):
        return access_token
    if not credential.encrypted_refresh_token:
        logger.info("github access token expired without refresh token")
        raise USER_TOKEN_UNAVAILABLE
    try:
        tokens = provider.refresh_token(
            decrypt_secret(credential.encrypted_refresh_token, settings)
        )
    except ApiError:
        logger.warning("github token refresh failed; user must sign in again")
        raise USER_TOKEN_UNAVAILABLE from None
    expires_at = None
    if tokens.expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)
    credential_repo.upsert(
        user_id=user.id,
        encrypted_access_token=encrypt_secret(tokens.access_token, settings),
        encrypted_refresh_token=(
            encrypt_secret(tokens.refresh_token, settings) if tokens.refresh_token else None
        ),
        expires_at=expires_at,
        scopes=tokens.scopes,
    )
    logger.info("github access token refreshed", extra={"context": {"github_id": user.github_id}})
    return tokens.access_token


class AuthService:
    def __init__(
        self,
        settings: Settings,
        provider: GitHubOAuthProvider,
        user_repo: UserRepository,
        state_repo: OAuthStateRepository,
        session_repo: UserSessionRepository,
        credential_repo: GitHubCredentialRepository,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._users = user_repo
        self._states = state_repo
        self._sessions = session_repo
        self._credentials = credential_repo

    # ------------------------------------------------------------ OAuth flow
    def start(self) -> str:
        """Create a one-time state and return the GitHub authorize URL."""
        record = self._states.create(self._settings.oauth_state_ttl_seconds)
        params = {
            "client_id": self._settings.github_app_client_id,
            "redirect_uri": self._settings.github_oauth_callback_url,
            "state": record.state,
            "response_type": "code",
        }
        return f"{self._settings.github_oauth_base_url}/login/oauth/authorize?{urlencode(params)}"

    def complete_callback(self, state: str, code: str) -> User:
        """Validate state (one-time), exchange the code, upsert the user.

        Raises ApiError(OAUTH_STATE_INVALID | GITHUB_TOKEN_ERROR) on failure;
        no session is created on any failure path.
        """
        if not self._states.try_consume(state):
            logger.info("oauth state rejected (missing, expired, or replayed)")
            raise INVALID_STATE
        tokens = self._provider.exchange_code(code)
        user_info = self._provider.get_user(tokens.access_token)
        user = self._users.upsert_from_github(
            github_id=user_info.github_id,
            github_login=user_info.login,
            avatar_url=user_info.avatar_url,
        )
        expires_at = None
        if tokens.expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)
        self._credentials.upsert(
            user_id=user.id,
            encrypted_access_token=encrypt_secret(tokens.access_token, self._settings),
            encrypted_refresh_token=(
                encrypt_secret(tokens.refresh_token, self._settings)
                if tokens.refresh_token
                else None
            ),
            expires_at=expires_at,
            scopes=tokens.scopes,
        )
        logger.info("user signed in", extra={"context": {"github_id": user_info.github_id}})
        return user

    # ----------------------------------------------------------- sessions
    def create_session(self, user: User) -> UserSession:
        return self._sessions.create(user.id, self._settings.session_ttl_seconds)

    def resolve_session(self, cookie_value: str) -> tuple[UserSession, User] | None:
        """Verify cookie signature and load a valid session + user."""
        session_id = verify_signed(cookie_value, self._settings)
        if session_id is None:
            return None
        record = self._sessions.get_valid(session_id)
        if record is None:
            return None
        user = self._users.get(record.user_id)
        if user is None:
            return None
        return record, user

    def logout(self, session_id: str) -> None:
        self._sessions.revoke(session_id)
        logger.info("user logged out", extra={"context": {}})

    # ------------------------------------------------------------ cookies
    def session_cookie_value(self, session: UserSession) -> str:
        """Signed cookie payload: only the session ID, never credentials."""
        return sign_value(session.id, self._settings)
