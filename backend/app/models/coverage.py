"""Change-review records (Phase 7A): Coverage.py file mappings and per-symbol status.

Coverage attachments are scoped to an analysis run so a re-attach replaces the
run's mapping atomically. Missing coverage is represented by absence of rows
(and in summaries as `unknown`) — never as zero coverage.
"""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.user import new_object_id

COVERAGE_STATUSES = ("covered", "partially_covered", "uncovered", "unknown")


class CoverageFile(Base, TimestampMixin):
    """One file entry from the attached Coverage.py JSON artifact.

    `source_path` is the path exactly as reported by Coverage.py; `matched_path`
    is the snapshot path it normalized to (null when no snapshot path matched).
    Line arrays are stored as JSON text.
    """

    __tablename__ = "coverage_files"
    __table_args__ = (
        UniqueConstraint("analysis_id", "source_path", name="uq_coverage_files_analysis_source"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    matched_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    executed_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    excluded_lines: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class SymbolCoverage(Base, TimestampMixin):
    """Per-symbol coverage classification for symbols in matched coverage files.

    Symbols in unmatched coverage files (and symbols from files with no coverage
    data at all) deliberately have no row — their status is `unknown`, which is
    reported as unknown, never as zero.
    """

    __tablename__ = "symbol_coverage"
    __table_args__ = (
        UniqueConstraint("analysis_id", "symbol_id", name="uq_symbol_coverage_symbol"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    executable_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executed_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
