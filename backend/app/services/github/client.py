"""GitHub API/OAuth client behind an injectable interface.

The production implementation talks to github.com only (configurable base
URLs exist for tests so no real network access is needed in automated tests).
No method ever logs tokens; responses are returned as plain dataclasses.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger("flowlens.github")

TOKEN_EXCHANGE_FAILED = ApiError(
    status_code=502,
    code="GITHUB_TOKEN_ERROR",
    message="GitHub authorization code exchange failed.",
)
USER_FETCH_FAILED = ApiError(
    status_code=502,
    code="GITHUB_TOKEN_ERROR",
    message="Could not fetch the GitHub user profile.",
)


@dataclass(frozen=True)
class TokenExchangeResult:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    scopes: str


@dataclass(frozen=True)
class GitHubUserInfo:
    github_id: int
    login: str
    avatar_url: str | None


class GitHubOAuthProvider:
    """Interface used by the auth service (mocked in tests)."""

    def exchange_code(self, code: str) -> TokenExchangeResult:
        raise NotImplementedError

    def refresh_token(self, refresh_token: str) -> TokenExchangeResult:
        """Rotate an expired user access token (Phase 8)."""
        raise NotImplementedError

    def get_user(self, access_token: str) -> GitHubUserInfo:
        raise NotImplementedError


class HttpxGitHubOAuthProvider(GitHubOAuthProvider):
    """Real GitHub App user-authorization client (github.com only)."""

    def __init__(self, settings: Settings, timeout: float = 10.0) -> None:
        self._settings = settings
        self._timeout = timeout

    def exchange_code(self, code: str) -> TokenExchangeResult:
        url = f"{self._settings.github_oauth_base_url}/login/oauth/access_token"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    data={
                        "client_id": self._settings.github_app_client_id,
                        "client_secret": self._settings.github_app_client_secret,
                        "code": code,
                    },
                    headers={"Accept": "application/json"},
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("token exchange transport error", extra={"context": {"error": type(exc).__name__}})
            raise TOKEN_EXCHANGE_FAILED from exc
        if response.status_code != 200 or "error" in payload or not payload.get("access_token"):
            # Never log the payload: it may echo credential material.
            logger.warning("token exchange rejected by github")
            raise TOKEN_EXCHANGE_FAILED
        return TokenExchangeResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scopes=payload.get("scope", ""),
        )

    def refresh_token(self, refresh_token: str) -> TokenExchangeResult:
        """Exchange a refresh token for a rotated access token.

        GitHub rotates refresh tokens on use; the response carries the new
        pair. Failures raise TOKEN_EXCHANGE_FAILED without logging payload
        material.
        """
        url = f"{self._settings.github_oauth_base_url}/login/oauth/access_token"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    data={
                        "client_id": self._settings.github_app_client_id,
                        "client_secret": self._settings.github_app_client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    headers={"Accept": "application/json"},
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "token refresh transport error",
                extra={"context": {"error": type(exc).__name__}},
            )
            raise TOKEN_EXCHANGE_FAILED from exc
        if response.status_code != 200 or "error" in payload or not payload.get("access_token"):
            logger.warning("token refresh rejected by github")
            raise TOKEN_EXCHANGE_FAILED
        return TokenExchangeResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scopes=payload.get("scope", ""),
        )

    def get_user(self, access_token: str) -> GitHubUserInfo:
        url = f"{self._settings.github_api_base_url}/user"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("user fetch transport error", extra={"context": {"error": type(exc).__name__}})
            raise USER_FETCH_FAILED from exc
        if response.status_code != 200 or "id" not in payload or "login" not in payload:
            logger.warning("user fetch rejected by github")
            raise USER_FETCH_FAILED
        return GitHubUserInfo(
            github_id=int(payload["id"]),
            login=payload["login"],
            avatar_url=payload.get("avatar_url"),
        )
