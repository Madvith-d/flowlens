"""Static analysis records: source files, symbols, call expressions, diagnostics.

Every row is scoped to an analysis run (`analysis_id`) so results of two runs
over the same immutable snapshot never overwrite each other. Symbol IDs are
deterministic within an analysis (see `app/services/analysis/ids.py`).
"""

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.user import new_object_id

SYMBOL_KINDS = ("module", "class", "function", "method")
DIAGNOSTIC_SEVERITIES = ("error", "warning", "info")
DIAGNOSTIC_CODES = (
    "SYNTAX_ERROR",
    "SOURCE_ENCODING_ERROR",
    "SOURCE_READ_ERROR",
    "FILE_TOO_LARGE",
    "FILE_SKIPPED",
    "SYMBOL_LIMIT_REACHED",
    "NO_PYTHON_FILES",
    "UNRESOLVED_REFERENCE",
    "AMBIGUOUS_REFERENCE",
    "UNRESOLVED_LIMIT_REACHED",
)
EDGE_KINDS = ("CALLS", "IMPORTS", "INHERITS", "REFERENCES")
DEPENDENCY_EDGE_KINDS = ("CALLS", "IMPORTS", "INHERITS", "REFERENCES")
CONFIDENCE_LEVELS = ("high", "medium", "low")


class SourceFile(Base, TimestampMixin):
    """Metadata for one file considered by an analysis run."""

    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("analysis_id", "path", name="uq_source_files_analysis_path"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_python: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_syntax_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Symbol(Base, TimestampMixin):
    """A parsed module/class/function/method with source spans.

    `id` is deterministic for the analysis (derived from the structural key:
    analysis + file + kind + qualified name + span) so graph IDs stay stable
    within a run; `parent_id` links nested definitions lexically.
    """

    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_analysis_qualified", "analysis_id", "qualified_name"),
        Index("ix_symbols_analysis_file_order", "analysis_id", "file_path", "start_line"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_column: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_async: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSON arrays (internal; not part of the public Symbol payload yet)
    decorators: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    imports: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class SymbolCall(Base, TimestampMixin):
    """A call expression attributed to its nearest enclosing symbol.

    Call expressions are *not* dependencies: resolution happens in a later
    phase, and anything unresolvable must stay unresolved rather than guessed.
    """

    __tablename__ = "symbol_calls"
    __table_args__ = (Index("ix_symbol_calls_analysis_caller", "analysis_id", "caller_symbol_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    caller_symbol_id: Mapped[str] = mapped_column(String(40), nullable=False)
    callee_expression: Mapped[str] = mapped_column(String(512), nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    column: Mapped[int] = mapped_column(Integer, nullable=False)


class DependencyEdge(Base, TimestampMixin):
    """One typed, deduplicated dependency edge between two symbols of an analysis.

    `CONTAINS` is structural and never stored here — it is derived from
    `Symbol.parent_id` at graph-build time and stays separate from dependency
    edges in traversals. Aggregated edges keep a bounded evidence list and the
    weakest (most conservative) confidence of the resolutions that produced
    them; the `resolver` names the best-priority strategy that contributed.
    """

    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint("analysis_id", "source_id", "target_id", "kind", name="uq_dependency_edges_edge"),
        Index("ix_dependency_edges_analysis_source", "analysis_id", "source_id"),
        Index("ix_dependency_edges_analysis_target", "analysis_id", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    resolver: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class AnalysisDiagnostic(Base, TimestampMixin):
    """Per-file / per-analysis diagnostics (syntax errors, skipped files, …)."""

    __tablename__ = "analysis_diagnostics"
    __table_args__ = (Index("ix_analysis_diagnostics_analysis", "analysis_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column: Mapped[int | None] = mapped_column(Integer, nullable=True)
