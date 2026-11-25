"""GitHub credentials (encrypted at rest) and app installation records."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.user import new_object_id


class GitHubCredential(Base, TimestampMixin):
    """GitHub user access token for a user, encrypted at rest.

    Only the vault-style encrypted blobs are stored. Never log or return these
    values; decryption happens only inside server-side GitHub service calls.
    """

    __tablename__ = "github_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encrypted_access_token: Mapped[str] = mapped_column(String(1024), nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GitHubInstallation(Base, TimestampMixin):
    """A FlowLens GitHub App installation verified through GitHub APIs."""

    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_github_installations_installation_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)  # user | organization
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
