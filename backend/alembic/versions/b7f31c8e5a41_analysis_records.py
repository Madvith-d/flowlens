"""analysis snapshot records: source files, symbols, calls, diagnostics

Revision ID: b7f31c8e5a41
Revises: a1c74f9d3e02
Create Date: 2026-11-25 16:40:00.000000

Phase 4A: per-analysis source file metadata, AST symbols with spans,
call expressions, and diagnostics. All rows cascade with the analysis run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f31c8e5a41'
down_revision: Union[str, None] = 'a1c74f9d3e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'source_files',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('analysis_id', sa.String(length=32), nullable=False),
        sa.Column('snapshot_id', sa.String(length=32), nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('is_python', sa.Boolean(), nullable=False),
        sa.Column('has_syntax_error', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['source_snapshots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analysis_id', 'path', name='uq_source_files_analysis_path'),
    )
    op.create_index('ix_source_files_analysis_id', 'source_files', ['analysis_id'])
    op.create_index('ix_source_files_snapshot_id', 'source_files', ['snapshot_id'])

    op.create_table(
        'symbols',
        sa.Column('id', sa.String(length=40), nullable=False),
        sa.Column('analysis_id', sa.String(length=32), nullable=False),
        sa.Column('snapshot_id', sa.String(length=32), nullable=False),
        sa.Column('parent_id', sa.String(length=40), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=False),
        sa.Column('qualified_name', sa.String(length=1024), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('start_line', sa.Integer(), nullable=False),
        sa.Column('end_line', sa.Integer(), nullable=False),
        sa.Column('start_column', sa.Integer(), nullable=False),
        sa.Column('end_column', sa.Integer(), nullable=False),
        sa.Column('is_async', sa.Boolean(), nullable=False),
        sa.Column('decorators', sa.Text(), nullable=False),
        sa.Column('bases', sa.Text(), nullable=False),
        sa.Column('imports', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_symbols_analysis_id', 'symbols', ['analysis_id'])
    op.create_index('ix_symbols_analysis_qualified', 'symbols', ['analysis_id', 'qualified_name'])
    op.create_index(
        'ix_symbols_analysis_file_order', 'symbols', ['analysis_id', 'file_path', 'start_line']
    )
    op.create_index('ix_symbols_parent_id', 'symbols', ['parent_id'])
    op.create_index('ix_symbols_snapshot_id', 'symbols', ['snapshot_id'])

    op.create_table(
        'symbol_calls',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('analysis_id', sa.String(length=32), nullable=False),
        sa.Column('caller_symbol_id', sa.String(length=40), nullable=False),
        sa.Column('callee_expression', sa.String(length=512), nullable=False),
        sa.Column('line', sa.Integer(), nullable=False),
        sa.Column('column', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_symbol_calls_analysis_id', 'symbol_calls', ['analysis_id'])
    op.create_index(
        'ix_symbol_calls_analysis_caller', 'symbol_calls', ['analysis_id', 'caller_symbol_id']
    )

    op.create_table(
        'analysis_diagnostics',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('analysis_id', sa.String(length=32), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=True),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('message', sa.String(length=1024), nullable=False),
        sa.Column('line', sa.Integer(), nullable=True),
        sa.Column('column', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_analysis_diagnostics_analysis', 'analysis_diagnostics', ['analysis_id'])


def downgrade() -> None:
    op.drop_index('ix_analysis_diagnostics_analysis', table_name='analysis_diagnostics')
    op.drop_table('analysis_diagnostics')
    op.drop_index('ix_symbol_calls_analysis_caller', table_name='symbol_calls')
    op.drop_index('ix_symbol_calls_analysis_id', table_name='symbol_calls')
    op.drop_table('symbol_calls')
    op.drop_index('ix_symbols_snapshot_id', table_name='symbols')
    op.drop_index('ix_symbols_parent_id', table_name='symbols')
    op.drop_index('ix_symbols_analysis_file_order', table_name='symbols')
    op.drop_index('ix_symbols_analysis_qualified', table_name='symbols')
    op.drop_index('ix_symbols_analysis_id', table_name='symbols')
    op.drop_table('symbols')
    op.drop_index('ix_source_files_snapshot_id', table_name='source_files')
    op.drop_index('ix_source_files_analysis_id', table_name='source_files')
    op.drop_table('source_files')
