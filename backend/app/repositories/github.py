"""GitHub credential data access. Tokens are always stored encrypted."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.github import GitHubCredential
from app.repositories.base import BaseRepository


class GitHubCredentialRepository(BaseRepository):
    def upsert(
        self,
        user_id: str,
        encrypted_access_token: str,
        encrypted_refresh_token: str | None,
        expires_at: datetime | None,
        scopes: str,
    ) -> GitHubCredential:
        credential = self.session.scalar(
            select(GitHubCredential).where(GitHubCredential.user_id == user_id)
        )
        if credential is None:
            credential = GitHubCredential(user_id=user_id)
            self.session.add(credential)
        credential.encrypted_access_token = encrypted_access_token
        credential.encrypted_refresh_token = encrypted_refresh_token
        credential.expires_at = expires_at
        credential.scopes = scopes
        credential.revoked_at = None
        self.session.flush()
        return credential

    def get_active(self, user_id: str) -> GitHubCredential | None:
        credential = self.session.scalar(
            select(GitHubCredential).where(GitHubCredential.user_id == user_id)
        )
        if credential is None or credential.revoked_at is not None:
            return None
        return credential

    def revoke(self, user_id: str) -> None:
        """Mark stored credentials revoked (e.g. upstream authorization revoked)."""
        credential = self.get_active(user_id)
        if credential is not None:
            credential.revoked_at = datetime.now(timezone.utc)
            self.session.flush()
