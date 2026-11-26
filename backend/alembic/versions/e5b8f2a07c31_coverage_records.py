"""coverage records (Phase 7A)

Revision ID: e5b8f2a07c31
Revises: c3d9e2ab5c71
Create Date: 2026-11-27 12:00:00.000000

Phase 7A: Coverage.py file mappings (executed/missing/excluded lines, matched
snapshot path) and per-symbol coverage classification. Coverage attachment is
per analysis run and re-attachment replaces the previous mapping; symbols with
no coverage data have no row and are reported as `unknown`, never as zero.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5b8f2a07c31"
down_revision: Union[str, None] = "c3d9e2ab5c71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coverage_files",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("analysis_id", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("matched_path", sa.String(length=1024), nullable=True),
        sa.Column("executed_lines", sa.Text(), nullable=False),
        sa.Column("missing_lines", sa.Text(), nullable=False),
        sa.Column("excluded_lines", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "source_path", name="uq_coverage_files_analysis_source"),
    )
    op.create_index("ix_coverage_files_analysis_id", "coverage_files", ["analysis_id"])
    op.create_table(
        "symbol_coverage",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("analysis_id", sa.String(length=32), nullable=False),
        sa.Column("symbol_id", sa.String(length=40), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("qualified_name", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("executable_line_count", sa.Integer(), nullable=False),
        sa.Column("executed_line_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "symbol_id", name="uq_symbol_coverage_symbol"),
    )
    op.create_index("ix_symbol_coverage_analysis_id", "symbol_coverage", ["analysis_id"])
    op.create_index("ix_symbol_coverage_symbol_id", "symbol_coverage", ["symbol_id"])


def downgrade() -> None:
    op.drop_index("ix_symbol_coverage_symbol_id", table_name="symbol_coverage")
    op.drop_index("ix_symbol_coverage_analysis_id", table_name="symbol_coverage")
    op.drop_table("symbol_coverage")
    op.drop_index("ix_coverage_files_analysis_id", table_name="coverage_files")
    op.drop_table("coverage_files")
