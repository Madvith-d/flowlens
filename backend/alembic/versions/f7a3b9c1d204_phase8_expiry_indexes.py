"""phase 8: expiry indexes for oauth_states and user_sessions

Revision ID: f7a3b9c1d204
Revises: e5b8f2a07c31
Create Date: 2026-11-26 10:00:00.000000

Phase 8 hardening: retention purges delete expired OAuth states and
application sessions opportunistically; both tables get an index on
`expires_at` so the purge (and expiry checks) stay indexed as tables grow.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a3b9c1d204'
down_revision: Union[str, None] = 'e5b8f2a07c31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_oauth_states_expires_at', 'oauth_states', ['expires_at'])
    op.create_index('ix_user_sessions_expires_at', 'user_sessions', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_user_sessions_expires_at', table_name='user_sessions')
    op.drop_index('ix_oauth_states_expires_at', table_name='oauth_states')
