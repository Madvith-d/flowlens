"""OAuth state and application session data access.

State consumption is a single conditional UPDATE so a replayed state cannot be
consumed twice even under racing requests.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.models.auth import OAuthState, UserSession
from app.repositories.base import BaseRepository


class OAuthStateRepository(BaseRepository):
    def create(self, ttl_seconds: int, entropy_bytes: int = 32) -> OAuthState:
        state = secrets.token_urlsafe(entropy_bytes)
        record = OAuthState(
            state=state,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def try_consume(self, state: str) -> bool:
        """Atomically mark the state consumed. True only for valid one-time use."""
        result = self.session.execute(
            update(OAuthState)
            .where(
                OAuthState.state == state,
                OAuthState.consumed_at.is_(None),
                OAuthState.expires_at > datetime.now(timezone.utc),
            )
            .values(consumed_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1


class UserSessionRepository(BaseRepository):
    def create(self, user_id: str, ttl_seconds: int) -> UserSession:
        session_record = UserSession(
            id=uuid.uuid4().hex,
            user_id=user_id,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self.session.add(session_record)
        self.session.flush()
        return session_record

    def get_valid(self, session_id: str) -> UserSession | None:
        record = self.session.get(UserSession, session_id)
        if record is None or not record.is_valid:
            return None
        return record

    def revoke(self, session_id: str) -> bool:
        record = self.session.get(UserSession, session_id)
        if record is None or not record.is_valid:
            return False
        record.revoked_at = datetime.now(timezone.utc)
        self.session.flush()
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        records = self.session.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        ).all()
        now = datetime.now(timezone.utc)
        for record in records:
            record.revoked_at = now
        self.session.flush()
        return len(records)
