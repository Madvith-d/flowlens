"""dependency edges and resolver counters (Phase 5A)

Revision ID: c3d9e2ab5c71
Revises: b7f31c8e5a41
Create Date: 2026-11-27 10:15:00.000000

Phase 5A: typed, deduplicated dependency edges (CALLS / IMPORTS / INHERITS /
REFERENCES) with bounded source evidence, plus exact unresolved/ambiguous
reference counters on analysis runs. CONTAINS remains structural and is never
stored as a dependency edge.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d9e2ab5c71"
down_revision: Union[str, None] = "b7f31c8e5a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dependency_edges",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("analysis_id", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("resolver", sa.String(length=64), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id", "source_id", "target_id", "kind",
            name="uq_dependency_edges_edge",
        ),
    )
    op.create_index(
        "ix_dependency_edges_analysis_id", "dependency_edges", ["analysis_id"]
    )
    op.create_index(
        "ix_dependency_edges_analysis_source", "dependency_edges", ["analysis_id", "source_id"]
    )
    op.create_index(
        "ix_dependency_edges_analysis_target", "dependency_edges", ["analysis_id", "target_id"]
    )
    op.add_column(
        "analysis_runs",
        sa.Column("unresolved_reference_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("ambiguous_reference_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "ambiguous_reference_count")
    op.drop_column("analysis_runs", "unresolved_reference_count")
    op.drop_index("ix_dependency_edges_analysis_target", table_name="dependency_edges")
    op.drop_index("ix_dependency_edges_analysis_source", table_name="dependency_edges")
    op.drop_index("ix_dependency_edges_analysis_id", table_name="dependency_edges")
    op.drop_table("dependency_edges")
