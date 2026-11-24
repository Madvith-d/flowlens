"""User data access: upsert keyed on GitHub's stable numeric user ID."""

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_by_github_id(self, github_id: int) -> User | None:
        return self.session.scalar(select(User).where(User.github_id == github_id))

    def upsert_from_github(self, github_id: int, github_login: str, avatar_url: str | None) -> User:
        """Create or update the FlowLens account for a GitHub identity."""
        user = self.get_by_github_id(github_id)
        if user is None:
            user = User(github_id=github_id, github_login=github_login, avatar_url=avatar_url)
            self.session.add(user)
        else:
            user.github_login = github_login
            user.avatar_url = avatar_url
        self.session.flush()
        return user
