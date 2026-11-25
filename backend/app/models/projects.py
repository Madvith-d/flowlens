"""Project, immutable source snapshot, analysis run, and report records.

Symbol/dependency-edge bulk tables are added in later phases with their
services; these four give the ownership/provenance backbone for Phase 2A.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.user import new_object_id

SOURCE_PROVIDERS = ("github", "upload")
ANALYSIS_STATES = ("queued", "running", "completed", "completed_with_warnings", "failed")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(16), nullable=False)
    # GitHub connection provenance (null for upload projects)
    github_installation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("github_installations.installation_id"), nullable=True
    )
    github_repository_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    github_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceSnapshot(Base, TimestampMixin):
    """Immutable source snapshot; refreshes create new rows, never mutate."""

    __tablename__ = "source_snapshots"
    __table_args__ = {"comment": "Immutable per commit/ref or upload revision"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    file_count: Mapped[int] = mapped_column(nullable=False, default=0)
    # GitHub provenance
    github_repository_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    github_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    snapshot_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("source_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    flowlens_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    graph_schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    python_file_count: Mapped[int] = mapped_column(nullable=False, default=0)
    symbol_count: Mapped[int] = mapped_column(nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_object_id)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="markdown")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
