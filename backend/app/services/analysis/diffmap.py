"""Unified diff parsing and changed-symbol mapping (Phase 7A).

The parser handles standard unified diffs (git-style `diff --git` headers or
plain `---`/`+++` pairs), multiple files and hunks, new/deleted files, and
maps changed lines onto the stored symbol spans of one analysis:

* Added lines are tracked on the *new* side and removed lines on the *old*
  side; both map onto symbol spans (symbols come from the snapshot).
* File classification: `added` (new file), `deleted` (file removed) or
  `modified`; every stored symbol in a deleted file is `deleted`.
* Symbol classification within a changed file:
  - `added`   — every line of the span was added and none were removed;
  - `deleted` — every line of the span was removed and none were added;
  - `modified` — any other overlap between changed lines and the span.
* Changed lines outside every symbol span (e.g. module-level imports) and
  diff paths that do not exist in the snapshot are reported as unmapped
  with an explicit reason — never silently dropped or guessed.

The combined impact is delegated to the impact service with the mapped
symbols as targets; per-target attribution is retained by that service.
"""

import logging
import re

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.user import User
from app.repositories.analysis import AnalysisRepository, SymbolRepository
from app.repositories.projects import ProjectRepository, SnapshotRepository
from app.services.analysis.impact import ImpactService

logger = logging.getLogger("flowlens.diff")

DIFF_INVALID = ApiError(
    status_code=422,
    code="DIFF_INVALID",
    message="The provided unified diff could not be parsed.",
)
INVALID_DIFF_QUERY = ApiError(
    status_code=400,
    code="VALIDATION_ERROR",
    message="Invalid diff request.",
)

_HEADER_LINE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_OLD_PATH = re.compile(r"^--- (?:a/)?(.*)$")
_NEW_PATH = re.compile(r"^\+\+\+ (?:b/)?(.*)$")
_HUNK_HEAD = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


class ParsedFile:
    """One file section of a unified diff."""

    def __init__(self, old_path: str | None, new_path: str | None) -> None:
        self.old_path = old_path
        self.new_path = new_path
        self.change_type = "modified"
        self.added_lines: set[int] = set()
        self.removed_lines: set[int] = set()
        self.added_count = 0
        self.removed_count = 0

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def changed_line_count(self) -> int:
        return self.added_count + self.removed_count


def parse_unified_diff(text: str) -> list[ParsedFile]:
    """Parse unified diff text into per-file changed-line sets.

    Raises DIFF_INVALID for text that contains no recognizable diff.
    """
    if not text or not text.strip():
        raise DIFF_INVALID

    files: list[ParsedFile] = []
    current: ParsedFile | None = None
    old_counter = 0
    new_counter = 0
    in_hunk = False

    for line in text.splitlines():
        header = _HEADER_LINE.match(line)
        if header:
            current = ParsedFile(header.group(1), header.group(2))
            files.append(current)
            in_hunk = False
            continue
        hunk_match = _HUNK_HEAD.match(line)
        if hunk_match:
            if current is None:
                raise DIFF_INVALID
            old_counter = int(hunk_match.group(1))
            new_counter = int(hunk_match.group(3))
            in_hunk = True
            continue
        if not in_hunk:
            if line.startswith("--- "):
                old_match = _OLD_PATH.match(line)
                if old_match and old_match.group(1) != "/dev/null":
                    if current is None or current.path != old_match.group(1):
                        current = ParsedFile(old_match.group(1), None)
                        files.append(current)
                elif old_match:
                    if current is None:
                        current = ParsedFile(None, None)
                        files.append(current)
                    current.old_path = None
                    current.change_type = "added"
                continue
            if line.startswith("+++ "):
                new_match = _NEW_PATH.match(line)
                if new_match and new_match.group(1) != "/dev/null":
                    if current is None or current.path != new_match.group(1):
                        current = ParsedFile(new_match.group(1), new_match.group(1))
                        files.append(current)
                    if current.old_path is None:
                        current.change_type = "added"
                    current.new_path = new_match.group(1)
                elif new_match:
                    if current is None:
                        current = ParsedFile(None, None)
                        files.append(current)
                    current.new_path = None
                    current.change_type = "deleted"
                continue
            if line.startswith(
                ("--- ", "+++ ")
            ) or line.startswith(
                ("new file mode", "deleted file mode", "index ", "similarity index",
                 "dissimilarity", "rename from", "rename to", "old mode", "new mode")
            ):
                if current is not None and line.startswith("deleted file mode"):
                    current.change_type = "deleted"
                if current is not None and line.startswith("new file mode"):
                    current.change_type = "added"
                continue
            raise DIFF_INVALID
        if line.startswith("+"):
            current.added_lines.add(new_counter)
            current.added_count += 1
            new_counter += 1
        elif line.startswith("-"):
            current.removed_lines.add(old_counter)
            current.removed_count += 1
            old_counter += 1
        elif line.startswith("\\"):
            continue
        else:
            old_counter += 1
            new_counter += 1

    if not files or all(file.changed_line_count == 0 for file in files):
        raise DIFF_INVALID
    return files


class DiffService:
    """Maps a unified diff onto the stored symbols of one analysis."""

    def __init__(
        self,
        settings: Settings,
        project_repo: ProjectRepository,
        snapshot_repo: SnapshotRepository,
        analysis_repo: AnalysisRepository,
        symbol_repo: SymbolRepository,
        impact_service: ImpactService,
    ) -> None:
        self._settings = settings
        self._projects = project_repo
        self._snapshots = snapshot_repo
        self._analyses = analysis_repo
        self._symbols = symbol_repo
        self._impact_service = impact_service

    def analyze(self, user: User, analysis_id: str, unified_diff: str) -> dict:
        if not isinstance(unified_diff, str) or not unified_diff.strip():
            raise INVALID_DIFF_QUERY
        if len(unified_diff) > self._settings.diff_max_bytes:
            raise ApiError(
                status_code=413,
                code="UPLOAD_TOO_LARGE",
                message="Unified diff exceeds the configured size limit.",
            )
        self._impact_service._owned_run(user, analysis_id)
        files = parse_unified_diff(unified_diff)
        if len(files) > self._settings.diff_max_files:
            raise ApiError(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Unified diff contains too many files.",
                details={"max_files": self._settings.diff_max_files, "file_count": len(files)},
            )

        symbols = self._symbols.list_for_analysis(analysis_id)
        by_path: dict[str, list] = {}
        for symbol in symbols:
            by_path.setdefault(symbol.file_path, []).append(symbol)
        for path in by_path:
            by_path[path].sort(key=lambda s: (s.start_line, s.qualified_name, s.id))

        warnings: list[str] = []
        file_payloads: list[dict] = []
        mapped_targets: dict[str, dict] = {}

        for parsed in files:
            payload, target_ids, file_warnings = self._map_file(parsed, by_path)
            file_payloads.append(payload)
            warnings.extend(file_warnings)
            for symbol_id in target_ids:
                mapped_targets[symbol_id] = True

        target_ids = sorted(mapped_targets, key=lambda sid: self._target_order(sid, symbols))
        capped = target_ids
        if len(target_ids) > 10:
            kept = target_ids[:10]
            warnings.append(
                f"Mapped changed symbols were capped to the impact target bound of 10;"
                f" {len(target_ids) - 10} mapped symbol(s) were excluded from the"
                " combined impact."
            )
            capped = kept
        capped = sorted(capped)

        if capped:
            combined = self._impact_service.impact(
                user,
                analysis_id,
                target_ids=capped,
                direction="both",
                max_depth=self._settings.diff_impact_max_depth,
            )
        else:
            combined = self._empty_impact(analysis_id, symbols)
            warnings.append(
                "No changed lines mapped to a stored symbol; the combined impact"
                " set is empty."
            )

        return {
            "analysis_id": analysis_id,
            "files": file_payloads,
            "combined_impact": combined,
            "warnings": warnings,
        }

    def _target_order(self, symbol_id: str, symbols) -> tuple:
        for symbol in symbols:
            if symbol.id == symbol_id:
                return (symbol.file_path, symbol.start_line, symbol.id)
        return ("", 0, symbol_id)

    def _match_path(self, path: str, known_paths: set[str]) -> str | None:
        candidates = [path]
        if path.startswith(("./", "a/", "b/")):
            candidates.append(path[path.index("/") + 1 :])
        for candidate in candidates:
            if candidate in known_paths:
                return candidate
        return None

    def _map_file(self, parsed: ParsedFile, by_path: dict) -> tuple[dict, list[str], list[str]]:
        warnings: list[str] = []
        known_paths = set(by_path.keys())
        matched = self._match_path(parsed.path, known_paths) if parsed.path else None
        payload = {
            "path": parsed.path,
            "change_type": parsed.change_type,
            "changed_line_count": parsed.changed_line_count,
            "mapped_symbols": [],
            "unmapped_line_count": parsed.changed_line_count,
            "unmapped_reason": None,
        }
        if parsed.path and matched is None:
            payload["unmapped_reason"] = "path not found in this analysis snapshot"
            warnings.append(
                f"Diff path '{parsed.path}' does not exist in this analysis"
                " snapshot; its changes were not mapped."
            )
            return payload, [], warnings

        # Module symbols span whole files; mapping to them would mark every
        # module-level change as "mapped". Non-module spans are mapped instead
        # so module-level lines stay explicitly unmapped with a reason.
        file_symbols = [symbol for symbol in by_path[matched] if symbol.kind != "module"]
        mapped: list[dict] = []
        unmapped = parsed.changed_line_count
        mapped_lines = 0
        target_ids: list[str] = []
        for symbol in file_symbols:
            span_lines = set(range(symbol.start_line, symbol.end_line + 1))
            added_in_span = len(parsed.added_lines & span_lines)
            removed_in_span = len(parsed.removed_lines & span_lines)
            changed = added_in_span + removed_in_span
            if changed == 0:
                continue
            if parsed.change_type == "deleted":
                change_type = "deleted"
            elif added_in_span == len(span_lines) and removed_in_span == 0:
                change_type = "added"
            elif removed_in_span == len(span_lines) and added_in_span == 0:
                change_type = "deleted"
            else:
                change_type = "modified"
            mapped.append(
                {
                    "symbol_id": symbol.id,
                    "qualified_name": symbol.qualified_name,
                    "change_type": change_type,
                }
            )
            target_ids.append(symbol.id)
            mapped_lines += changed

        payload["mapped_symbols"] = mapped
        payload["unmapped_line_count"] = max(parsed.changed_line_count - mapped_lines, 0)
        if payload["unmapped_line_count"] > 0:
            payload["unmapped_reason"] = (
                "changed lines outside any symbol span (e.g. module-level changes)"
            )
        return payload, target_ids, warnings

    def _empty_impact(self, analysis_id: str, symbols) -> dict:
        consequence = {
            "analysis_id": analysis_id,
            "targets": [],
            "direction": "both",
            "max_depth": self._settings.diff_impact_max_depth,
            "impacted": [],
            "truncated": False,
            "risk": {
                "score": 0,
                "version": self._settings.risk_score_version,
                "coverage_included": False,
                "factors": [],
                "caveats": ["No mapped changed symbols; the risk factor breakdown is empty."],
            },
            "warnings": [],
            "coverage_summary": None,
        }
        del symbols
        return consequence
