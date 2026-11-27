"""GitHub App installation flows and repository access (Phase 3A).

Security properties:
- The `state` used for the installation flow is one-time and server-issued
  (same store as the OAuth flow), so installation callbacks cannot be replayed
  or forged cross-site.
- Browser-supplied installation IDs are untrusted: every use re-verifies the
  installation against the authenticated user's installations via the GitHub
  API before anything is recorded or accessed.
- Installation access tokens are short-lived, repository-scoped where
  supported, generated server-side, and never stored or returned to clients.
"""

import logging
from urllib.parse import urlencode

from app.core.config import Settings
from app.models.user import User
from app.repositories.auth import OAuthStateRepository
from app.repositories.github import GitHubCredentialRepository
from app.repositories.installations import GitHubInstallationRepository
from app.services.github.app_client import (
    INSTALLATION_ACCESS_DENIED,
    GitHubAppClient,
    InstallationInfo,
    RepositoriesPage,
)

logger = logging.getLogger("flowlens.github_service")


class GitHubInstallationService:
    def __init__(
        self,
        settings: Settings,
        app_client: GitHubAppClient,
        provider,
        state_repo: OAuthStateRepository,
        credential_repo: GitHubCredentialRepository,
        installation_repo: GitHubInstallationRepository,
    ) -> None:
        self._settings = settings
        self._app_client = app_client
        self._provider = provider
        self._states = state_repo
        self._credentials = credential_repo
        self._installations = installation_repo

    # ------------------------------------------------------------ install flow
    def install_start(self, user: User) -> str:
        """One-time state + GitHub App installation page URL."""
        record = self._states.create(self._settings.oauth_state_ttl_seconds)
        base = f"{self._settings.github_app_slug}/installations/new"
        params = {"state": record.state}
        return f"{self._settings.github_oauth_base_url}/apps/{base}?{urlencode(params)}"

    def complete_install_callback(self, user: User, state: str, installation_id: int) -> InstallationInfo:
        """Validate state, then verify the installation against GitHub.

        The installation must appear in the user's own installation list
        before it is recorded. Anything else is denied.
        """
        if not self._states.try_consume(state):
            logger.info("install callback state rejected")
            raise ValueError("state")
        installations = self.list_user_installations(user)
        matched = next(
            (info for info in installations if info.installation_id == installation_id), None
        )
        if matched is None:
            logger.info(
                "install callback: installation not accessible to user",
                extra={"context": {"installation_id": installation_id}},
            )
            raise PermissionError("installation")
        self._installations.upsert_verified(
            installation_id=matched.installation_id,
            account_login=matched.account_login,
            account_type=matched.account_type,
            avatar_url=matched.avatar_url,
        )
        return matched

    # ------------------------------------------------------------- installations
    def _user_access_token(self, user: User) -> str:
        from app.services.auth.service import active_access_token

        return active_access_token(
            user, self._settings, self._provider, self._credentials
        )

    def list_user_installations(self, user: User) -> list[InstallationInfo]:
        """Live, verified installations for the authenticated user."""
        return self._app_client.list_user_installations(self._user_access_token(user))

    def list_repositories(
        self, user: User, installation_id: int, page: int, per_page: int
    ) -> tuple[RepositoriesPage, InstallationInfo]:
        """Repositories the user and installation are both permitted to access.

        `installation_id` is verified against the user's installations first;
        then the repository list is fetched with an installation token.
        """
        installations = self.list_user_installations(user)
        matched = next(
            (info for info in installations if info.installation_id == installation_id), None
        )
        if matched is None:
            raise INSTALLATION_ACCESS_DENIED
        # Listing only reads repository metadata; request only that
        # permission so tokens stay least-privilege and work even when the
        # installation has not (yet) granted Contents access.
        token = self._app_client.build_installation_token(
            installation_id, permissions={"metadata": "read"}
        )
        repositories = self._app_client.list_installation_repositories(
            token.token, page=page, per_page=per_page
        )
        return repositories, matched
