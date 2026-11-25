"""GitHub App installation data access.

Installation rows are written only after the installation has been verified
through GitHub APIs against the authenticated user's installations.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.github import GitHubInstallation
from app.repositories.base import BaseRepository


class GitHubInstallationRepository(BaseRepository):
    def upsert_verified(
        self,
        installation_id: int,
        account_login: str,
        account_type: str,
        avatar_url: str | None,
    ) -> GitHubInstallation:
        record = self.session.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        )
        if record is None:
            record = GitHubInstallation(installation_id=installation_id)
            record.account_login = account_login
            record.account_type = account_type
            record.avatar_url = avatar_url
            self.session.add(record)
        else:
            record.account_login = account_login
            record.account_type = account_type
            record.avatar_url = avatar_url
        record.verified_at = datetime.now(timezone.utc)
        self.session.flush()
        return record

    def get_by_installation_id(self, installation_id: int) -> GitHubInstallation | None:
        return self.session.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id)
        )
