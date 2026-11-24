"""User accounts, keyed on GitHub's stable numeric user ID."""

import uuid

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


def new_object_id() -> str:
    return uuid.uuid4().hex


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("github_id", name="uq_users_github_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    github_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def public_view(self) -> dict:
        """Client-safe representation: never includes credentials."""
        return {
            "id": self.id,
            "github_login": self.github_login,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
