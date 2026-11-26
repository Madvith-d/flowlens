"""Markdown report generation (Phase 7A).

Renders a deterministic Markdown document from *structured* result data only
— the stored analysis run, its snapshot/project provenance, the impact result
(recomputed through the impact service), attached coverage data, diagnostics
summary, and the standard exclusions/caveats. Every string that enters a
table cell is escaped (pipes, backslashes, newlines) so report content can
never break table layout or inject Markdown structure; every list is emitted
in a deterministic order (typically sorted by qualified name / path / ID).

The report always matches the stored data because it is generated from it in
the same request; nothing in a report is invented, estimated, or guessed.
"""

import logging

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.projects import Report
from app.models.user import User, new_object_id
from app.repositories.analysis import (
    AnalysisRepository,
    DiagnosticRepository,
    SymbolRepository,
)
from app.repositories.analysis import SourceFileRepository
from app.repositories.coverage import CoverageFileRepository, SymbolCoverageRepository
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.analysis.impact import ImpactService
from app.services.ingestion.storage import ReportStorage, UnsafeSnapshotPathError

logger = logging.getLogger("flowlens.report")

ANALYSIS_NOT_FOUND = ApiError(
    status_code=404,
    code="ANALYSIS_NOT_FOUND",
    message="Analysis not found.",
)
REPORT_NOT_FOUND = ApiError(
    status_code=404,
    code="NOT_FOUND",
    message="Report not found.",
)


def escape_cell(value: object) -> str:
    """Make an arbitrary value safe for a Markdown table cell."""
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\r", " ").replace("\n", " ")
    return text


def render_markdown_report(data: dict) -> str:
    """Deterministic Markdown report from a structured result payload."""
    lines: list[str] = []
    lines.append("# FlowLens Impact Report")
    lines.append("")

    meta = data.get("metadata", {})
    lines.append("## Metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    for key in sorted(meta):
        lines.append(f"| {escape_cell(key)} | {escape_cell(meta[key])} |")
    lines.append("")

    targets = data.get("targets", [])
    lines.append("## Targets")
    lines.append("")
    if targets:
        lines.append("| Target | Qualified name |")
        lines.append("| --- | --- |")
        for target in sorted(targets, key=lambda item: (item["qualified_name"], item["node_id"])):
            lines.append(
                f"| {escape_cell(target['node_id'])} | {escape_cell(target['qualified_name'])} |"
            )
    else:
        lines.append("_No target symbols were selected._")
    lines.append("")

    impacted = data.get("impacted", [])
    lines.append("## Impacted nodes")
    lines.append("")
    lines.append(f"Total: **{len(impacted)}**"
                 + (" (truncated)" if data.get("truncated") else "")
                 + ".")
    lines.append("")
    if impacted:
        lines.append("| Qualified name | Kind | Direct | Min hops | Attributed to |")
        lines.append("| --- | --- | --- | --- | --- |")
        ordered = sorted(impacted, key=lambda item: (item["min_hops"], item["qualified_name"], item["node_id"]))
        for node in ordered:
            lines.append(
                f"| {escape_cell(node['qualified_name'])}"
                f" | {escape_cell(node['kind'])}"
                f" | {escape_cell('yes' if node['direct'] else 'no')}"
                f" | {escape_cell(node['min_hops'])}"
                f" | {escape_cell(', '.join(node['attributed_to']))} |"
            )
    else:
        lines.append("_No impacted nodes within the requested depth._")
    lines.append("")

    risk = data.get("risk")
    if risk:
        lines.append("## Risk score")
        lines.append("")
        lines.append(
            f"Score: **{risk['score']}/100** (version {risk['version']};"
            f" coverage included: {'yes' if risk.get('coverage_included') else 'no'})."
        )
        lines.append("")
        lines.append("| Factor | Weight (applied) | Raw | Normalized | Included |")
        lines.append("| --- | --- | --- | --- | --- |")
        for factor in risk.get("factors", []):
            lines.append(
                f"| {escape_cell(factor.get('label', factor['key']))}"
                f" | {escape_cell(factor.get('weight'))}"
                f" | {escape_cell(factor.get('raw_value'))}"
                f" | {escape_cell(factor.get('normalized_value'))}"
                f" | {escape_cell('yes' if factor.get('included') else 'no')} |"
            )
        caveats = risk.get("caveats", [])
        if caveats:
            lines.append("")
            lines.append("Caveats:")
            lines.append("")
            for caveat in caveats:
                lines.append(f"- {escape_cell(caveat)}")
        lines.append("")

    coverage = data.get("coverage")
    if coverage is not None and coverage.get("attached"):
        summary = coverage["summary"]
        lines.append("## Coverage")
        lines.append("")
        lines.append("| Status | Symbols |")
        lines.append("| --- | --- |")
        for key in ("covered", "partially_covered", "uncovered", "unknown"):
            lines.append(f"| {escape_cell(key)} | {escape_cell(summary[key])} |")
        lines.append("")
        symbols = coverage.get("symbols", [])
        if symbols:
            lines.append("| Qualified name | File | Status | Executable | Executed |")
            lines.append("| --- | --- | --- | --- | --- |")
            ordered = sorted(
                symbols, key=lambda item: (item["qualified_name"], item["file_path"])
            )
            for symbol in ordered:
                lines.append(
                    f"| {escape_cell(symbol['qualified_name'])}"
                    f" | {escape_cell(symbol['file_path'])}"
                    f" | {escape_cell(symbol['status'])}"
                    f" | {escape_cell(symbol['executable_line_count'])}"
                    f" | {escape_cell(symbol['executed_line_count'])} |"
                )
            lines.append("")
        lines.append(
            "Coverage marks symbols without executed statements as `unknown`;"
            " missing coverage is never reported as zero."
        )
        lines.append("")
    else:
        lines.append("## Coverage")
        lines.append("")
        lines.append("_No Coverage.py artifact is attached; all coverage is unknown._")
        lines.append("")

    diagnostics = data.get("diagnostics", {})
    if diagnostics:
        lines.append("## Diagnostics summary")
        lines.append("")
        lines.append("| Code | Count |")
        lines.append("| --- | --- |")
        for code in sorted(diagnostics):
            lines.append(f"| {escape_cell(code)} | {escape_cell(diagnostics[code])} |")
        lines.append("")

    exclusions = data.get("exclusions", [])
    if exclusions:
        lines.append("## Exclusions and limitations")
        lines.append("")
        for item in exclusions:
            lines.append(f"- {escape_cell(item)}")
        lines.append("")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {escape_cell(warning)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Risk is a change-impact prioritization heuristic and is NOT a"
        " probability of failure."
    )
    lines.append("")
    return "\n".join(lines)


class ReportService:
    """Generates and serves deterministic Markdown reports."""

    def __init__(
        self,
        settings: Settings,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        analysis_repo: AnalysisRepository,
        symbol_repo: SymbolRepository,
        source_file_repo: SourceFileRepository,
        diagnostics_repo: DiagnosticRepository,
        coverage_file_repo: CoverageFileRepository,
        symbol_coverage_repo: SymbolCoverageRepository,
        impact_service: ImpactService,
        report_storage: ReportStorage,
    ) -> None:
        self._settings = settings
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._analyses = analysis_repo
        self._symbols = symbol_repo
        self._source_files = source_file_repo
        self._diagnostics = diagnostics_repo
        self._coverage_files = coverage_file_repo
        self._symbol_coverage = symbol_coverage_repo
        self._impact_service = impact_service
        self._storage = report_storage

    def _owned_run(self, user: User, analysis_id: str):
        run = self._analyses.get(analysis_id)
        if run is None:
            raise ANALYSIS_NOT_FOUND
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise ANALYSIS_NOT_FOUND
        if run.state not in ("completed", "completed_with_warnings"):
            raise ApiError(
                status_code=409,
                code="ANALYSIS_NOT_READY",
                message="Analysis has not completed yet.",
            )
        return run, snapshot, self._projects.get_owned(snapshot.project_id, user.id)

    def generate(
        self,
        user: User,
        analysis_id: str,
        *,
        target_ids: list[str] | None,
        direction: str = "both",
        max_depth: int = 3,
    ) -> Report:
        run, snapshot, project = self._owned_run(user, analysis_id)
        symbols = self._symbols.list_for_analysis(analysis_id)
        by_id = {symbol.id: symbol for symbol in symbols}

        warnings: list[str] = []
        if not target_ids:
            ordered = sorted(
                symbols,
                key=lambda symbol: (
                    symbol.kind == "module",
                    symbol.file_path,
                    symbol.start_line,
                    symbol.id,
                ),
            )
            target_ids = [symbol.id for symbol in ordered[:10]]
            if len(symbols) > 10:
                warnings.append(
                    "No targets were requested; the first 10 module-level"
                    " symbols (deterministic order) were used."
                )
        target_ids = sorted(set(target_ids))

        impact = self._impact_service.impact(
            user,
            analysis_id,
            target_ids=target_ids,
            direction=direction,
            max_depth=max_depth,
        )

        coverage_attached = (
            self._coverage_files.has_any(analysis_id)
            and self._symbol_coverage.has_any(analysis_id)
        )
        coverage_payload: dict | None = None
        if coverage_attached:
            rows = self._symbol_coverage.list_for_analysis(analysis_id)
            summary = dict(impact.get("coverage_summary") or {})
            coverage_payload = {
                "attached": True,
                "summary": summary,
                "symbols": [
                    {
                        "qualified_name": row.qualified_name,
                        "file_path": row.file_path,
                        "status": row.status,
                        "executable_line_count": row.executable_line_count,
                        "executed_line_count": row.executed_line_count,
                    }
                    for row in rows
                ],
            }
        else:
            coverage_payload = {"attached": False}

        diagnostics_summary: dict = self._diagnostics.summary(analysis_id)
        diagnostics_summary["unresolved_references"] = run.unresolved_reference_count
        diagnostics_summary["ambiguous_references"] = run.ambiguous_reference_count

        exclusions = [
            "Unresolved and ambiguous references are excluded from the"
            " dependency graph and therefore from this report.",
            "The dependency graph is built by static analysis only; sources are"
            " never imported, executed, or installed.",
            "Representative paths are shortest hop paths; other paths may exist.",
            "Impacted nodes are capped by the configured impact bound; hop"
            " counters for omitted nodes are not reported.",
        ]

        data = {
            "metadata": self._metadata(project, snapshot, run, direction, max_depth),
            "targets": [
                {"node_id": symbol_id, "qualified_name": by_id[symbol_id].qualified_name}
                for symbol_id in target_ids
                if symbol_id in by_id
            ],
            "impacted": impact.get("impacted", []),
            "truncated": impact.get("truncated", False),
            "risk": impact.get("risk"),
            "coverage": coverage_payload,
            "diagnostics": diagnostics_summary,
            "exclusions": exclusions,
            "warnings": warnings + impact.get("warnings", []),
        }
        report = Report(
            id=new_object_id(),
            analysis_id=analysis_id,
            format="markdown",
            filename=f"flowlens-report-{analysis_id}.md",
            stored_path="",
        )
        try:
            report.stored_path = self._storage.save(
                report.id, report.filename, render_markdown_report(data)
            )
        except (UnsafeSnapshotPathError, OSError):
            logger.exception("report storage failed")
            raise ApiError(
                status_code=500,
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
            )
        self._analyses.add_report(report)
        logger.info(
            "report generated",
            extra={"context": {"analysis_id": analysis_id, "report_id": report.id}},
        )
        return report

    def _metadata(self, project, snapshot, run, direction: str, max_depth: int) -> dict:
        metadata = {
            "report_id": "",
            "analysis_id": run.id,
            "flowlens_version": run.flowlens_version,
            "graph_schema_version": run.graph_schema_version,
            "risk_score_version": self._settings.risk_score_version,
            "project_name": project.name,
            "source_provider": snapshot.provider,
            "snapshot_id": snapshot.id,
            "snapshot_commit_sha": snapshot.github_commit_sha or "n/a",
            "snapshot_ref": snapshot.github_ref or "n/a",
            "direction": direction,
            "max_depth": max_depth,
        }
        return metadata

    def download(self, user: User, report_id: str) -> tuple[str, str, str]:
        report = self._analyses.get_report(report_id)
        if report is None:
            raise REPORT_NOT_FOUND
        run = self._analyses.get(report.analysis_id)
        if run is None:
            raise REPORT_NOT_FOUND
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise REPORT_NOT_FOUND
        try:
            content = self._storage.read(report.stored_path)
        except (UnsafeSnapshotPathError, OSError):
            raise REPORT_NOT_FOUND
        return content, report.filename, report.format
