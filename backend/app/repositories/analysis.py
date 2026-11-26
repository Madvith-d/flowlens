"""Analysis-run, source-file, symbol, call, and diagnostic data access."""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.models.projects import AnalysisRun, SourceSnapshot
from app.models.analysis import AnalysisDiagnostic, DependencyEdge, SourceFile, Symbol, SymbolCall
from app.repositories.base import BaseRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRepository(BaseRepository):
    def create(self, snapshot_id: str, flowlens_version: str, graph_schema_version: str) -> AnalysisRun:
        run = AnalysisRun(
            snapshot_id=snapshot_id,
            state="queued",
            flowlens_version=flowlens_version,
            graph_schema_version=graph_schema_version,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, analysis_id: str) -> AnalysisRun | None:
        return self.session.get(AnalysisRun, analysis_id)

    def mark_running(self, run: AnalysisRun) -> AnalysisRun:
        run.state = "running"
        run.started_at = utc_now()
        self.session.flush()
        return run

    def finish(
        self,
        run: AnalysisRun,
        *,
        state: str,
        python_file_count: int,
        symbol_count: int,
        edge_count: int = 0,
        unresolved_reference_count: int = 0,
        ambiguous_reference_count: int = 0,
        error_code: str | None = None,
    ) -> AnalysisRun:
        run.state = state
        run.python_file_count = python_file_count
        run.symbol_count = symbol_count
        run.edge_count = edge_count
        run.unresolved_reference_count = unresolved_reference_count
        run.ambiguous_reference_count = ambiguous_reference_count
        run.error_code = error_code
        run.finished_at = utc_now()
        self.session.flush()
        return run

    def latest_for_project(self, project_id: str) -> AnalysisRun | None:
        return self.session.scalar(
            select(AnalysisRun)
            .join(SourceSnapshot, SourceSnapshot.id == AnalysisRun.snapshot_id)
            .where(SourceSnapshot.project_id == project_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
            .limit(1)
        )

    def latest_for_projects(self, project_ids: list[str]) -> dict[str, AnalysisRun]:
        """Batched latest-analysis lookup (one query per project list page)."""
        if not project_ids:
            return {}
        rows = self.session.execute(
            select(SourceSnapshot.project_id, AnalysisRun)
            .join(SourceSnapshot, SourceSnapshot.id == AnalysisRun.snapshot_id)
            .where(SourceSnapshot.project_id.in_(project_ids))
            .order_by(AnalysisRun.created_at.asc(), AnalysisRun.id.asc())
        ).all()
        latest: dict[str, AnalysisRun] = {}
        for project_id, run in rows:
            latest[project_id] = run  # ascending order → last wins
        return latest


class SourceFileRepository(BaseRepository):
    def add_many(self, files: list[SourceFile]) -> None:
        if files:
            self.session.add_all(files)
            self.session.flush()

    def list_for_analysis(self, analysis_id: str) -> list[SourceFile]:
        return list(
            self.session.scalars(
                select(SourceFile)
                .where(SourceFile.analysis_id == analysis_id)
                .order_by(SourceFile.path.asc())
            ).all()
        )


class SymbolRepository(BaseRepository):
    def add_many(self, symbols: list[Symbol]) -> None:
        if symbols:
            self.session.add_all(symbols)
            self.session.flush()

    def get(self, analysis_id: str, symbol_id: str) -> Symbol | None:
        symbol = self.session.get(Symbol, symbol_id)
        if symbol is None or symbol.analysis_id != analysis_id:
            return None
        return symbol

    def search(
        self,
        analysis_id: str,
        *,
        query: str | None,
        kind: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[Symbol], int]:
        """Deterministically ordered, bounded, case-insensitive symbol search."""
        conditions = [Symbol.analysis_id == analysis_id]
        if kind:
            conditions.append(Symbol.kind == kind)
        if query:
            needle = f"%{query.strip()}%"
            conditions.append(or_(Symbol.name.ilike(needle), Symbol.qualified_name.ilike(needle)))
        total = self.session.scalar(select(func.count(Symbol.id)).where(*conditions)) or 0
        items = self.session.scalars(
            select(Symbol)
            .where(*conditions)
            .order_by(
                Symbol.file_path.asc(),
                Symbol.start_line.asc(),
                Symbol.start_column.asc(),
                Symbol.qualified_name.asc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return list(items), int(total)

    def count(self, analysis_id: str) -> int:
        return int(
            self.session.scalar(select(func.count(Symbol.id)).where(Symbol.analysis_id == analysis_id))
            or 0
        )

    def list_for_analysis(self, analysis_id: str) -> list[Symbol]:
        """All symbols of one analysis in deterministic source order."""
        return list(
            self.session.scalars(
                select(Symbol)
                .where(Symbol.analysis_id == analysis_id)
                .order_by(
                    Symbol.file_path.asc(),
                    Symbol.start_line.asc(),
                    Symbol.start_column.asc(),
                    Symbol.qualified_name.asc(),
                )
            ).all()
        )


class SymbolCallRepository(BaseRepository):
    def add_many(self, calls: list[SymbolCall]) -> None:
        if calls:
            self.session.add_all(calls)
            self.session.flush()

    def list_for_analysis(self, analysis_id: str) -> list[SymbolCall]:
        return list(
            self.session.scalars(
                select(SymbolCall)
                .where(SymbolCall.analysis_id == analysis_id)
                .order_by(
                    SymbolCall.caller_symbol_id.asc(),
                    SymbolCall.line.asc(),
                    SymbolCall.column.asc(),
                    SymbolCall.callee_expression.asc(),
                )
            ).all()
        )


class DependencyEdgeRepository(BaseRepository):
    def add_many(self, edges: list[DependencyEdge]) -> None:
        if edges:
            self.session.add_all(edges)
            self.session.flush()

    def list_for_analysis(self, analysis_id: str) -> list[DependencyEdge]:
        """All dependency edges of one analysis, deterministic by edge ID."""
        return list(
            self.session.scalars(
                select(DependencyEdge)
                .where(DependencyEdge.analysis_id == analysis_id)
                .order_by(DependencyEdge.id.asc())
            ).all()
        )

    def count(self, analysis_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(DependencyEdge.id)).where(DependencyEdge.analysis_id == analysis_id)
            )
            or 0
        )


class DiagnosticRepository(BaseRepository):
    def add_many(self, diagnostics: list[AnalysisDiagnostic]) -> None:
        if diagnostics:
            self.session.add_all(diagnostics)
            self.session.flush()

    def list_for_analysis(self, analysis_id: str) -> list[AnalysisDiagnostic]:
        return list(
            self.session.scalars(
                select(AnalysisDiagnostic)
                .where(AnalysisDiagnostic.analysis_id == analysis_id)
                .order_by(
                    AnalysisDiagnostic.file_path.asc(),
                    AnalysisDiagnostic.line.asc(),
                    AnalysisDiagnostic.code.asc(),
                )
            ).all()
        )

    def summary(self, analysis_id: str) -> dict[str, int]:
        """Counts only; unresolved/ambiguous counters arrive with the resolver phase."""
        rows = self.session.execute(
            select(AnalysisDiagnostic.code, func.count(AnalysisDiagnostic.id))
            .where(AnalysisDiagnostic.analysis_id == analysis_id)
            .group_by(AnalysisDiagnostic.code)
        ).all()
        counts = {code: int(count) for code, count in rows}
        return {
            "syntax_errors": counts.get("SYNTAX_ERROR", 0),
            "skipped_files": counts.get("FILE_TOO_LARGE", 0)
            + counts.get("FILE_SKIPPED", 0)
            + counts.get("SOURCE_ENCODING_ERROR", 0),
        }
