"""Coverage.py artifact mapping (Phase 7A).

Parses the documented Coverage.py JSON format (`coverage json`) with strict
schema validation, normalizes reported paths against the snapshot, and maps
executable/covered lines onto stored symbol spans:

* executable lines = executed + missing lines reported by Coverage.py;
* per symbol: `covered` (all executable lines executed), `partially_covered`,
  `uncovered` (executable lines exist for the span but none executed) or
  `unknown` (no executable statement in the span, or no matching coverage
  file at all).

Path matching is conservative: exact snapshot paths, `a/`- `b/`- and `./`
prefixes, and — only when unique — a path suffix match. Anything that cannot
be matched is counted as unmatched and stays `unknown`; missing coverage is
never reported as zero.
"""

import json
import logging

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.coverage import CoverageFile, SymbolCoverage
from app.models.user import User
from app.repositories.analysis import AnalysisRepository, SymbolRepository
from app.repositories.coverage import CoverageFileRepository, SymbolCoverageRepository
from app.repositories.projects import ProjectRepository, SnapshotRepository

logger = logging.getLogger("flowlens.coverage")

COVERAGE_INVALID = ApiError(
    status_code=400,
    code="COVERAGE_INVALID",
    message="The provided Coverage.py JSON artifact is malformed.",
)


def _validated_file_entry(source_path: str, entry: object) -> dict:
    if not isinstance(source_path, str) or not source_path or not isinstance(entry, dict):
        raise COVERAGE_INVALID
    validated: dict = {}
    for key in ("executed_lines", "missing_lines", "excluded_lines"):
        value = entry.get(key, [])
        if not isinstance(value, list) or any(
            not isinstance(item, int) or item < 0 for item in value
        ):
            raise COVERAGE_INVALID
        validated[key] = sorted(set(value))
    summary = entry.get("summary", {})
    if not isinstance(summary, dict):
        raise COVERAGE_INVALID
    return validated


class CoverageService:
    """Attaches Coverage.py JSON to a completed analysis run."""

    def __init__(
        self,
        settings: Settings,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        analysis_repo: AnalysisRepository,
        symbol_repo: SymbolRepository,
        coverage_file_repo: CoverageFileRepository,
        symbol_coverage_repo: SymbolCoverageRepository,
    ) -> None:
        self._settings = settings
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._analyses = analysis_repo
        self._symbols = symbol_repo
        self._coverage_files = coverage_file_repo
        self._symbol_coverage = symbol_coverage_repo

    def attach(self, user: User, analysis_id: str, payload: object) -> dict:
        return self.attach_payload(user, analysis_id, payload)

    def _owned_run(self, user: User, analysis_id: str):
        run = self._analyses.get(analysis_id)
        if run is None:
            raise ApiError(status_code=404, code="ANALYSIS_NOT_FOUND", message="Analysis not found.")
        snapshot = self._snapshots.get(run.snapshot_id)
        if snapshot is None or self._projects.get_owned(snapshot.project_id, user.id) is None:
            raise ApiError(status_code=404, code="ANALYSIS_NOT_FOUND", message="Analysis not found.")
        if run.state not in ("completed", "completed_with_warnings"):
            raise ApiError(
                status_code=409, code="ANALYSIS_NOT_READY", message="Analysis has not completed yet."
            )
        return run

    def attach_payload(self, user: User, analysis_id: str, payload: object) -> dict:
        run = self._owned_run(user, analysis_id)
        parsed = self._parse_payload(payload)

        symbols = self._symbols.list_for_analysis(analysis_id)
        known_paths = sorted({symbol.file_path for symbol in symbols})
        symbols_by_path: dict[str, list] = {}
        for symbol in symbols:
            symbols_by_path.setdefault(symbol.file_path, []).append(symbol)

        warnings: list[str] = []
        file_rows: list[CoverageFile] = []
        coverage_rows: list[SymbolCoverage] = []
        unmatched = 0
        file_records: dict[str, tuple[str, dict]] = {}

        if len(parsed) > self._settings.coverage_max_files:
            raise ApiError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Coverage artifact contains too many files.",
                details={
                    "max_files": self._settings.coverage_max_files,
                    "file_count": len(parsed),
                },
            )

        for source_path in sorted(parsed):
            entry = parsed[source_path]
            matched_path = self._match_path(source_path, known_paths)
            if matched_path is None:
                unmatched += 1
                warnings.append(
                    f"Coverage file '{source_path}' could not be matched to a"
                    " snapshot path; its symbols remain unknown."
                )
            file_records[source_path] = (matched_path, entry)
            file_rows.append(
                CoverageFile(
                    analysis_id=analysis_id,
                    source_path=source_path[:1024],
                    matched_path=matched_path,
                    executed_lines=json.dumps(entry["executed_lines"], separators=(",", ":")),
                    missing_lines=json.dumps(entry["missing_lines"], separators=(",", ":")),
                    excluded_lines=json.dumps(entry.get("excluded_lines", []), separators=(",", ":")),
                )
            )

        for source_path, (matched_path, entry) in file_records.items():
            if matched_path is None:
                continue
            executed = set(entry["executed_lines"])
            missing = set(entry["missing_lines"])
            executable = executed | missing
            for symbol in symbols_by_path.get(matched_path, []):
                span_lines = set(range(symbol.start_line, symbol.end_line + 1))
                ext = executable & span_lines
                if not ext:
                    status = "unknown"
                else:
                    hit = executed & span_lines
                    if hit == ext:
                        status = "covered"
                    elif hit:
                        status = "partially_covered"
                    else:
                        status = "uncovered"
                coverage_rows.append(
                    SymbolCoverage(
                        analysis_id=analysis_id,
                        symbol_id=symbol.id,
                        file_path=symbol.file_path,
                        qualified_name=symbol.qualified_name,
                        status=status,
                        executable_line_count=len(ext),
                        executed_line_count=len(executed & span_lines),
                    )
                )

        self._coverage_files.replace_for_analysis(analysis_id, file_rows)
        self._symbol_coverage.replace_for_analysis(analysis_id, coverage_rows)
        result = {
            "analysis_id": analysis_id,
            "summary": self.summary(analysis_id, symbols=symbols, rows=coverage_rows),
            "unmatched_file_count": unmatched,
            "warnings": warnings,
        }
        logger.info(
            "coverage attached",
            extra={
                "context": {
                    "analysis_id": analysis_id,
                    "files": len(file_rows),
                    "unmatched": unmatched,
                    "symbols": len(coverage_rows),
                }
            },
        )
        return result

    def _parse_payload(self, payload: object) -> dict[str, dict]:
        if not isinstance(payload, dict):
            raise COVERAGE_INVALID
        if "meta" in payload and not isinstance(payload["meta"], dict):
            raise COVERAGE_INVALID
        files = payload.get("files")
        if not isinstance(files, dict) or not files:
            raise COVERAGE_INVALID
        totals = payload.get("totals", {})
        if not isinstance(totals, dict):
            raise COVERAGE_INVALID
        return {
            source_path: _validated_file_entry(source_path, entry)
            for source_path, entry in files.items()
        }

    def _match_path(self, source_path: str, known_paths: list[str]) -> str | None:
        candidates = [source_path]
        if source_path.startswith(("./", "a/", "b/")):
            candidates.append(source_path[source_path.index("/") + 1 :])
        for candidate in candidates:
            if candidate in known_paths:
                return candidate
        for candidate in candidates:
            suffix_matches = [
                known for known in known_paths if known.endswith("/" + candidate)
            ]
            if len(suffix_matches) == 1:
                return suffix_matches[0]
        return None

    def summary(self, analysis_id: str, symbols=None, rows=None) -> dict[str, int]:
        if symbols is None:
            symbols = self._symbols.list_for_analysis(analysis_id)
            symbols = [s for s in symbols]
        if rows is None:
            rows = self._symbol_coverage.list_for_analysis(analysis_id)
        counts = {"covered": 0, "partially_covered": 0, "uncovered": 0, "unknown": 0}
        for row in rows:
            if row.status in counts:
                counts[row.status] += 1
        total = len(symbols) if symbols is not None else self._symbols.count(analysis_id)
        counts["unknown"] = max(
            total - counts["covered"] - counts["partially_covered"] - counts["uncovered"], 0
        )
        return {
            "covered": counts["covered"],
            "partially_covered": counts["partially_covered"],
            "uncovered": counts["uncovered"],
            "unknown": counts["unknown"],
        }
