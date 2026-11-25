"""github connection visibility and default branch on projects

Revision ID: a1c74f9d3e02
Revises: 48e88e749069
Create Date: 2026-11-25 10:12:00.000000

Phase 3A: canonical GitHub visibility/default-branch provenance on the
project GitHub connection (metadata only — access is always verified live).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c74f9d3e02'
down_revision: Union[str, None] = '48e88e749069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('github_visibility', sa.String(length=16), nullable=True),
    )
    op.add_column(
        'projects',
        sa.Column('github_default_branch', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('projects', 'github_default_branch')
    op.drop_column('projects', 'github_visibility')
