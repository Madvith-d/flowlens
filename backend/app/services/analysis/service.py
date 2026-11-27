"""Static analysis service: create runs, parse snapshots, resolve dependencies.

Runs execute inline (single-process) and persist per-analysis records; the API
still models the run lifecycle (`queued` → `running` → `completed` /
`completed_with_warnings` / `failed`) so a worker-based runner can replace the
inline call without changing the contract. Parsing (Phase 4A) is followed by
dependency resolution (Phase 5A): stored symbols and call expressions become
typed, deduplicated edges with source evidence, and unresolved or ambiguous
references become explicit diagnostics — never guessed edges.

The analyzed source is only ever read and parsed — never imported, executed,
or installed.
"""

import json
import logging
import time
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.analysis import AnalysisDiagnostic, DependencyEdge, SourceFile, Symbol, SymbolCall
from app.models.projects import AnalysisRun, SourceSnapshot
from app.models.user import User
from app.repositories.analysis import (
    AnalysisRepository,
    DependencyEdgeRepository,
    DiagnosticRepository,
    SourceFileRepository,
    SymbolCallRepository,
    SymbolRepository,
)
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.analysis.parser import (
    collect_python_files,
    parse_python_file,
    symbol_imports_to_json,
    symbol_json_list,
)
from app.services.analysis.resolver import (
    CallRecord,
    Evidence,
    ResolutionResult,
    StaticResolver,
    SymbolRecord,
    edge_id,
    import_records_from_json,
)
from app.services.ingestion.archive import DEFAULT_EXCLUDED_PARTS
from app.services.ingestion.storage import SnapshotStorage, UnsafeSnapshotPathError

logger = logging.getLogger("flowlens.analysis")

SNAPSHOT_NOT_FOUND = ApiError(
    status_code=404,
    code="SNAPSHOT_NOT_FOUND",
    message="Snapshot not found.",
)
ANALYSIS_NOT_FOUND = ApiError(
    status_code=404,
    code="ANALYSIS_NOT_FOUND",
    message="Analysis not found.",
)
ANALYSIS_INVALID_KIND = ApiError(
    status_code=400,
    code="VALIDATION_ERROR",
    message="Unknown symbol kind filter.",
)


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        analysis_repo: AnalysisRepository,
        source_file_repo: SourceFileRepository,
        symbol_repo: SymbolRepository,
        call_repo: SymbolCallRepository,
        edge_repo: DependencyEdgeRepository,
        diagnostic_repo: DiagnosticRepository,
        storage: SnapshotStorage,
    ) -> None:
        self._settings = settings
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._analyses = analysis_repo
        self._files = source_file_repo
        self._symbols = symbol_repo
        self._calls = call_repo
        self._edges = edge_repo
        self._diagnostics = diagnostic_repo
        self._storage = storage

    # ------------------------------------------------------------- ownership
    def _owned_snapshot(self, user: User, snapshot_id: str) -> tuple[SourceSnapshot, str]:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise SNAPSHOT_NOT_FOUND
        project = self._projects.get_owned(snapshot.project_id, user.id)
        if project is None:
            # Same envelope for "not yours" and "does not exist".
            raise SNAPSHOT_NOT_FOUND
        return snapshot, project.id

    def get(self, user: User, analysis_id: str) -> AnalysisRun:
        run = self._analyses.get(analysis_id)
        if run is None:
            raise ANALYSIS_NOT_FOUND
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise ANALYSIS_NOT_FOUND
        return run

    # ------------------------------------------------------------ run creation
    def create_run(self, user: User, snapshot_id: str) -> AnalysisRun:
        snapshot, _project_id = self._owned_snapshot(user, snapshot_id)
        run = self._analyses.create(
            snapshot.id,
            flowlens_version=self._settings.flowlens_version,
            graph_schema_version=self._settings.graph_schema_version,
        )
        self._execute(run, snapshot)
        return run

    def _execute(self, run: AnalysisRun, snapshot: SourceSnapshot) -> AnalysisRun:
        """Run the analysis, containing unexpected failures as `failed` runs.

        An unexpected error must never leave a run stuck in `running` and must
        never surface an internal error string to the client: the run is marked
        `failed` with the stable `INTERNAL_ERROR` code, and the failure is
        logged with the full stack trace server-side only.
        """
        self._analyses.mark_running(run)
        try:
            return self._execute_inner(run, snapshot)
        except Exception:
            logger.exception(
                "analysis failed unexpectedly",
                extra={"context": {"analysis_id": run.id}},
            )
            try:
                self._diagnostics.add_many(
                    [
                        AnalysisDiagnostic(
                            analysis_id=run.id,
                            file_path=None,
                            severity="error",
                            code="INTERNAL_ERROR",
                            message="Analysis stopped unexpectedly. Please retry.",
                        )
                    ]
                )
            except Exception:
                logger.exception(
                    "could not record analysis failure diagnostic",
                    extra={"context": {"analysis_id": run.id}},
                )
            return self._analyses.finish(
                run,
                state="failed",
                python_file_count=0,
                symbol_count=0,
                error_code="INTERNAL_ERROR",
            )

    def _execute_inner(self, run: AnalysisRun, snapshot: SourceSnapshot) -> AnalysisRun:
        """Parse every Python file in the snapshot; never raises for bad input."""
        try:
            snapshot_dir = Path(self._storage.snapshot_dir(snapshot.id))
        except (UnsafeSnapshotPathError, OSError):
            logger.warning("snapshot storage unavailable", extra={"context": {"analysis_id": run.id}})
            return self._analyses.finish(
                run,
                state="failed",
                python_file_count=0,
                symbol_count=0,
                error_code="INTERNAL_ERROR",
            )

        rel_paths = collect_python_files(snapshot_dir, set(DEFAULT_EXCLUDED_PARTS))
        if not rel_paths:
            self._diagnostics.add_many(
                [
                    AnalysisDiagnostic(
                        analysis_id=run.id,
                        file_path=None,
                        severity="warning",
                        code="NO_PYTHON_FILES",
                        message="No Python files were found in this snapshot.",
                    )
                ]
            )
            return self._analyses.finish(
                run,
                state="completed_with_warnings",
                python_file_count=0,
                symbol_count=0,
            )

        source_files: list[SourceFile] = []
        symbols: list[Symbol] = []
        calls: list[SymbolCall] = []
        diagnostics: list[AnalysisDiagnostic] = []
        symbol_budget = self._settings.analysis_max_symbols
        limit_diagnostic_added = False
        deadline = time.monotonic() + self._settings.analysis_max_wall_seconds

        for rel_path in rel_paths:
            if time.monotonic() > deadline:
                diagnostics.append(
                    AnalysisDiagnostic(
                        analysis_id=run.id,
                        file_path=None,
                        severity="warning",
                        code="ANALYSIS_TIME_BUDGET_EXCEEDED",
                        message=(
                            "Analysis time budget reached; remaining files were not "
                            "catalogued. Results cover the files processed so far."
                        ),
                    )
                )
                break
            parsed = parse_python_file(
                snapshot_dir / rel_path,
                rel_path,
                analysis_id=run.id,
                max_file_bytes=self._settings.snapshot_max_file_bytes,
                max_calls_per_symbol=self._settings.analysis_max_calls_per_symbol,
            )
            source_files.append(
                SourceFile(
                    analysis_id=run.id,
                    snapshot_id=snapshot.id,
                    path=parsed.path,
                    size_bytes=parsed.size_bytes,
                    sha256=parsed.sha256,
                    is_python=True,
                    has_syntax_error=parsed.has_syntax_error,
                )
            )
            for diagnostic in parsed.diagnostics:
                diagnostics.append(
                    AnalysisDiagnostic(
                        analysis_id=run.id,
                        file_path=diagnostic.file_path,
                        severity=diagnostic.severity,
                        code=diagnostic.code,
                        message=diagnostic.message,
                        line=diagnostic.line,
                        column=diagnostic.column,
                    )
                )
            for parsed_symbol in parsed.symbols:
                if len(symbols) >= symbol_budget:
                    if not limit_diagnostic_added:
                        diagnostics.append(
                            AnalysisDiagnostic(
                                analysis_id=run.id,
                                file_path=None,
                                severity="warning",
                                code="SYMBOL_LIMIT_REACHED",
                                message=(
                                    "Analysis symbol budget reached; remaining definitions "
                                    "were not catalogued."
                                ),
                            )
                        )
                        limit_diagnostic_added = True
                    break
                symbols.append(
                    Symbol(
                        id=parsed_symbol.id,
                        analysis_id=run.id,
                        snapshot_id=snapshot.id,
                        parent_id=parsed_symbol.parent_id,
                        kind=parsed_symbol.kind,
                        name=parsed_symbol.name,
                        qualified_name=parsed_symbol.qualified_name,
                        file_path=parsed_symbol.file_path,
                        start_line=parsed_symbol.start_line,
                        end_line=parsed_symbol.end_line,
                        start_column=parsed_symbol.start_column,
                        end_column=parsed_symbol.end_column,
                        is_async=parsed_symbol.is_async,
                        decorators=symbol_json_list(parsed_symbol.decorators),
                        bases=symbol_json_list(parsed_symbol.bases),
                        imports=symbol_imports_to_json(parsed_symbol.imports),
                    )
                )
                for call in parsed_symbol.calls:
                    calls.append(
                        SymbolCall(
                            analysis_id=run.id,
                            caller_symbol_id=parsed_symbol.id,
                            callee_expression=call.callee_expression,
                            line=call.line,
                            column=call.column,
                        )
                    )

        self._files.add_many(source_files)
        self._symbols.add_many(symbols)
        self._calls.add_many(calls)

        self._diagnostics.add_many(diagnostics)
        resolution = self._resolve_dependencies(run, snapshot)
        unresolved = resolution.unresolved_count
        ambiguous = resolution.ambiguous_count

        warnings = (
            any(item.severity in ("error", "warning") for item in diagnostics)
            or resolution.diagnostics
            or unresolved
            or ambiguous
        )
        state = "completed_with_warnings" if warnings else "completed"
        logger.info(
            "analysis finished",
            extra={
                "context": {
                    "analysis_id": run.id,
                    "files": len(source_files),
                    "symbols": len(symbols),
                    "calls": len(calls),
                    "edges": len(resolution.edges),
                    "unresolved": unresolved,
                    "ambiguous": ambiguous,
                    "state": state,
                }
            },
        )
        return self._analyses.finish(
            run,
            state=state,
            python_file_count=len(source_files),
            symbol_count=len(symbols),
            edge_count=len(resolution.edges),
            unresolved_reference_count=unresolved,
            ambiguous_reference_count=ambiguous,
        )

    # ------------------------------------------------------------- resolution
    def _resolve_dependencies(
        self, run: AnalysisRun, snapshot: SourceSnapshot
    ) -> ResolutionResult:
        """Resolve stored symbols/calls into typed dependency edges (Phase 5A).

        Unresolvable or ambiguous references become explicit diagnostics; the
        run's counters stay exact even when diagnostic rows are capped.
        """
        resolver = StaticResolver(run.id)
        symbol_rows = self._symbols.list_for_analysis(run.id)
        call_rows = self._calls.list_for_analysis(run.id)
        records = [_symbol_record(row) for row in symbol_rows]
        calls = [
            CallRecord(
                caller_id=row.caller_symbol_id,
                expression=row.callee_expression,
                line=row.line,
                column=row.column,
            )
            for row in call_rows
        ]
        result = resolver.resolve(
            records,
            calls,
            max_evidence_per_edge=self._settings.analysis_max_evidence_per_edge,
            max_reference_diagnostics=self._settings.analysis_max_reference_diagnostics,
        )
        edges: list[DependencyEdge] = []
        for record in result.edges[: self._settings.analysis_max_edges]:
            edges.append(
                DependencyEdge(
                    id=edge_id(run.id, record.source_id, record.target_id, record.kind),
                    analysis_id=run.id,
                    source_id=record.source_id,
                    target_id=record.target_id,
                    kind=record.kind,
                    confidence=record.confidence,
                    resolver=record.resolver,
                    evidence=evidence_to_json(record.evidence),
                )
            )
        self._edges.add_many(edges)
        self._diagnostics.add_many(
            [
                AnalysisDiagnostic(
                    analysis_id=run.id,
                    file_path=item.file_path,
                    severity=item.severity,
                    code=item.code,
                    message=item.message,
                    line=item.line,
                    column=item.column,
                )
                for item in result.diagnostics
            ]
        )
        if len(result.edges) > self._settings.analysis_max_edges:
            self._diagnostics.add_many(
                [
                    AnalysisDiagnostic(
                        analysis_id=run.id,
                        file_path=None,
                        severity="warning",
                        code="UNRESOLVED_LIMIT_REACHED",
                        message=(
                            "Dependency edge budget reached; remaining references were"
                            " resolved but not stored as graph edges."
                        ),
                    )
                ]
            )
        return result

    # ------------------------------------------------------------------ reads
    def diagnostics_summary(self, analysis_id: str) -> dict[str, int]:
        run = self._analyses.get(analysis_id)
        summary = self._diagnostics.summary(analysis_id)
        if run is not None:
            # Exact occurrence counters from the resolver (rows may be capped).
            summary["unresolved_references"] = run.unresolved_reference_count
            summary["ambiguous_references"] = run.ambiguous_reference_count
        return summary

    def list_symbols(
        self,
        user: User,
        analysis_id: str,
        *,
        query: str | None,
        kind: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[Symbol], int]:
        self.get(user, analysis_id)  # ownership + existence
        if kind is not None and kind not in {"module", "class", "function", "method"}:
            raise ANALYSIS_INVALID_KIND
        return self._symbols.search(
            analysis_id, query=query, kind=kind, page=page, per_page=per_page
        )

    def latest_for_project(self, project_id: str) -> AnalysisRun | None:
        return self._analyses.latest_for_project(project_id)

    def latest_for_projects(self, project_ids: list[str]) -> dict[str, AnalysisRun]:
        return self._analyses.latest_for_projects(project_ids)


# ---------------------------------------------------------------- record helpers
def _symbol_record(symbol: Symbol) -> SymbolRecord:
    """ORM symbol row → resolver record (base/import JSON → tuples)."""
    bases = json.loads(symbol.bases or "[]")
    return SymbolRecord(
        id=symbol.id,
        kind=symbol.kind,
        name=symbol.name,
        qualified_name=symbol.qualified_name,
        file_path=symbol.file_path,
        parent_id=symbol.parent_id,
        start_line=symbol.start_line,
        bases=tuple(str(base) for base in bases),
        imports=import_records_from_json(symbol.imports),
    )


def evidence_to_json(evidence: tuple[Evidence, ...]) -> str:
    return json.dumps(
        [
            {
                "file_path": item.file_path,
                "line": item.line,
                "column": item.column,
                "expression": item.expression,
            }
            for item in evidence
        ],
        separators=(",", ":"),
    )
