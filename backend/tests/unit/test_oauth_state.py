"""Unit tests: OAuth state lifecycle (one-time, expiring) and sessions."""

from datetime import datetime, timedelta, timezone

from app.repositories.auth import OAuthStateRepository, UserSessionRepository
from app.repositories.users import UserRepository
from app.models.user import User


def test_state_is_one_time(session_factory) -> None:
    db = session_factory()
    repo = OAuthStateRepository(db)
    state = repo.create(ttl_seconds=600)
    db.commit()

    assert repo.try_consume(state.state) is True
    db.commit()
    # Replay must fail: one-time use.
    assert repo.try_consume(state.state) is False


def test_state_expires(session_factory) -> None:
    db = session_factory()
    repo = OAuthStateRepository(db)
    state = repo.create(ttl_seconds=600)
    # Force expiry directly in the database.
    record = db.get(type(state), state.state)
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert repo.try_consume(state.state) is False


def test_unknown_state_rejected(session_factory) -> None:
    db = session_factory()
    assert OAuthStateRepository(db).try_consume("no-such-state") is False


def test_session_lifecycle(session_factory) -> None:
    db = session_factory()
    user = UserRepository(db).upsert_from_github(1, "u", None)
    sessions = UserSessionRepository(db)
    record = sessions.create(user.id, ttl_seconds=3600)
    db.commit()

    assert sessions.get_valid(record.id) is not None
    assert sessions.revoke(record.id) is True
    assert sessions.get_valid(record.id) is None
    # Revoking twice does not resurrect.
    assert sessions.revoke(record.id) is False


def test_revoke_all_for_user_persists_other_users(session_factory) -> None:
    db = session_factory()
    users = UserRepository(db)
    user_a = users.upsert_from_github(1, "a", None)
    user_b = users.upsert_from_github(2, "b", None)
    sessions = UserSessionRepository(db)
    session_a = sessions.create(user_a.id, 3600)
    session_b = sessions.create(user_b.id, 3600)
    db.commit()

    count = sessions.revoke_all_for_user(user_a.id)
    db.commit()
    assert count == 1
    assert sessions.get_valid(session_a.id) is None
    assert sessions.get_valid(session_b.id) is not None
