"""Unit tests: OAuth state lifecycle (one-time, expiring) and sessions."""

from datetime import datetime, timedelta, timezone

from app.models.auth import OAuthState, UserSession
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


# --------------------------------------------------------- Phase 8 retention
def test_expired_states_purged_on_create(session_factory) -> None:
    """Creating a state purges states that expired beyond the grace window."""
    db = session_factory()
    repo = OAuthStateRepository(db)
    now = datetime.now(timezone.utc)
    db.add(OAuthState(state="expired-old", expires_at=now - timedelta(days=2)))
    db.add(OAuthState(state="expired-recent", expires_at=now - timedelta(hours=1)))
    db.add(OAuthState(state="still-valid", expires_at=now + timedelta(minutes=10)))
    db.commit()

    repo.create(ttl_seconds=600)
    db.commit()

    assert db.get(OAuthState, "expired-old") is None
    assert db.get(OAuthState, "expired-recent") is not None  # inside grace window
    assert db.get(OAuthState, "still-valid") is not None


def test_expired_sessions_purged_on_create(session_factory) -> None:
    """Creating a session purges sessions that expired beyond the grace window."""
    db = session_factory()
    users = UserRepository(db)
    user = users.upsert_from_github(github_id=1, github_login="u", avatar_url=None)
    repo = UserSessionRepository(db)
    now = datetime.now(timezone.utc)

    stale = UserSession(
        id="a" * 32,
        user_id=user.id,
        csrf_token="t1",
        expires_at=now - timedelta(days=2),
    )
    fresh_expired = UserSession(
        id="b" * 32,
        user_id=user.id,
        csrf_token="t2",
        expires_at=now - timedelta(hours=1),
    )
    live = repo.create(user.id, ttl_seconds=600)
    db.add(stale)
    db.add(fresh_expired)
    db.commit()

    repo.create(user.id, ttl_seconds=600)
    db.commit()

    assert db.get(UserSession, "a" * 32) is None
    assert db.get(UserSession, "b" * 32) is not None  # inside grace window
    assert db.get(UserSession, live.id) is not None
