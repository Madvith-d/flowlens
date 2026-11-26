"""Unit tests for Phase 7A internals: diff parser, coverage validation, report escaping."""

import pytest

from app.core.errors import ApiError
from app.services.analysis.coverage import CoverageService, _validated_file_entry
from app.services.analysis.diffmap import parse_unified_diff
from app.services.analysis.reports import escape_cell, render_markdown_report

# ----------------------------------------------------------------- diff parser


def test_parse_basic_modified_file():
    diff = "\n".join(
        [
            "--- a/app/service.py",
            "+++ b/app/service.py",
            "@@ -1,3 +1,3 @@",
            " def helper(value):",
            "-    return value",
            "+    return value + 1",
            " ",
        ]
    )
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert files[0].path == "app/service.py"
    assert files[0].change_type == "modified"
    assert files[0].added_lines == {2}
    assert files[0].removed_lines == {2}
    assert files[0].changed_line_count == 2


def test_parse_multiple_hunks_tracks_new_and_old_sides():
    diff = "\n".join(
        [
            "diff --git a/big.py b/big.py",
            "index 111..222 100644",
            "--- a/big.py",
            "+++ b/big.py",
            "@@ -2,3 +2,4 @@ def first():",
            " ctx",
            "+    added = 1",
            " ctx2",
            " ctx3",
            "@@ -10,2 +11,2 @@",
            "-removed = 2",
            "+replacement = 3",
        ]
    )
    files = parse_unified_diff(diff)
    assert len(files) == 1
    # Hunk 1: added new-side line 3; hunk 2: removed old-side 10, added new-side 11.
    assert files[0].added_lines == {3, 11}
    assert files[0].removed_lines == {10}
    assert files[0].added_count == 2
    assert files[0].removed_count == 1


def test_parse_multiple_files():
    diff = "\n".join(
        [
            "diff --git a/one.py b/one.py",
            "--- a/one.py",
            "+++ b/one.py",
            "@@ -1,1 +1,2 @@",
            "+x = 1",
            " keep",
            "diff --git a/two.py b/two.py",
            "--- a/two.py",
            "+++ b/two.py",
            "@@ -5,1 +5,1 @@",
            "-old",
            "+new",
        ]
    )
    files = parse_unified_diff(diff)
    assert [f.path for f in files] == ["one.py", "two.py"]
    assert files[0].added_lines == {1}
    assert files[1].removed_lines == {5}


def test_parse_deleted_file():
    diff = "\n".join(
        [
            "diff --git a/gone.py b/gone.py",
            "deleted file mode 100644",
            "index 111..000",
            "--- a/gone.py",
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
            "-def gone():",
            "-    return 1",
        ]
    )
    files = parse_unified_diff(diff)
    assert files[0].path == "gone.py"
    assert files[0].change_type == "deleted"
    assert files[0].removed_lines == {1, 2}
    assert files[0].added_count == 0


def test_parse_added_file():
    diff = "\n".join(
        [
            "diff --git a/fresh.py b/fresh.py",
            "new file mode 100644",
            "--- /dev/null",
            "+++ b/fresh.py",
            "@@ -0,0 +1,2 @@",
            "+def fresh():",
            "+    return 2",
        ]
    )
    files = parse_unified_diff(diff)
    assert files[0].path == "fresh.py"
    assert files[0].change_type == "added"
    assert files[0].added_lines == {1, 2}
    assert files[0].removed_count == 0


@pytest.mark.parametrize(
    "text",
    ["", "   ", "this is not a diff at all", "--- a/x.py\n", "@@ -1 +1 @@\nwith no file header"],
)
def test_parse_rejects_malformed(text):
    with pytest.raises(ApiError) as raised:
        parse_unified_diff(text)
    assert raised.value.code == "DIFF_INVALID"


# ----------------------------------------------------------- coverage validation


def _entry(**overrides):
    base = {"executed_lines": [1], "missing_lines": [2], "excluded_lines": []}
    base.update(overrides)
    return base


def test_validated_file_entry_accepts_documented_shape():
    validated = _validated_file_entry("app/x.py", _entry(executed_lines=[2, 2, 1]))
    assert validated["executed_lines"] == [1, 2]


@pytest.mark.parametrize(
    "entry",
    [
        "not-a-dict",
        {"executed_lines": [1], "missing_lines": "all"},
        {"executed_lines": [1], "missing_lines": [0, "3"]},
        {"executed_lines": [1], "missing_lines": [-2]},
        {"executed_lines": [1], "missing_lines": [2], "summary": "oops"},
    ],
)
def test_validated_file_entry_rejects_malformed(entry):
    with pytest.raises(ApiError) as raised:
        _validated_file_entry("app/x.py", entry)
    assert raised.value.code == "COVERAGE_INVALID"


def test_validated_file_entry_rejects_bad_path():
    with pytest.raises(ApiError):
        _validated_file_entry("", _entry())
    with pytest.raises(ApiError):
        _validated_file_entry("x", None)


def test_coverage_match_path_variants():
    service = CoverageService.__new__(CoverageService)
    known = ["app/service.py", "pkg/other.py", "tests/unit/test_x.py"]
    assert service._match_path("app/service.py", known) == "app/service.py"
    assert service._match_path("a/app/service.py", known) == "app/service.py"
    assert service._match_path("./app/service.py", known) == "app/service.py"
    assert service._match_path("test_x.py", known) == "tests/unit/test_x.py"
    assert service._match_path("service.py", known) == "app/service.py"
    # Absent paths stay unmatched (conservative).
    assert service._match_path("none.py", known) is None


# --------------------------------------------------------------- report escaping


def test_escape_cell_escapes_markdown_hazards():
    assert escape_cell("a|b") == r"a\|b"
    assert escape_cell("back\\slash") == r"back\\slash"
    assert escape_cell("line1\nline2") == "line1 line2"
    assert escape_cell(None) == ""
    assert escape_cell("| `code` |") == r"\| `code` \|"


def test_render_report_is_deterministic_and_contains_sections():
    data = {
        "metadata": {"analysis_id": "a1", "project_name": "P|Q"},
        "targets": [{"node_id": "t1", "qualified_name": "helper"}],
        "impacted": [
            {
                "node_id": "n2",
                "kind": "function",
                "qualified_name": "uses_helper",
                "direct": True,
                "min_hops": 1,
                "paths": [{"edges": ["e1"]}],
                "attributed_to": ["t1"],
            }
        ],
        "truncated": False,
        "risk": {
            "score": 42,
            "version": "1",
            "coverage_included": False,
            "factors": [
                {
                    "key": "public_entry_point",
                    "label": "Public API / entry-point indicator",
                    "weight": 0.15,
                    "raw_value": 1.0,
                    "normalized_value": 1.0,
                    "included": True,
                }
            ],
            "caveats": ["a|b"],
        },
        "coverage": {"attached": False},
        "diagnostics": {"syntax_errors": 0},
        "exclusions": ["unresolved references excluded"],
        "warnings": [],
    }
    first = render_markdown_report(data)
    second = render_markdown_report(data)
    assert first == second
    assert "# FlowLens Impact Report" in first
    assert "## Metadata" in first
    assert r"P\|Q" in first  # project name pipe escaped in a table cell
    assert "## Targets" in first
    assert "## Impacted nodes" in first
    assert "uses_helper" in first
    assert "## Risk score" in first
    assert "42/100" in first
    assert "## Coverage" in first
    assert "_No Coverage.py artifact is attached" in first
    assert r"a\|b" in first
    assert "NOT a" in first


def test_render_report_coverage_attached():
    data = {
        "metadata": {},
        "targets": [],
        "impacted": [],
        "truncated": False,
        "risk": None,
        "coverage": {
            "attached": True,
            "summary": {"covered": 2, "partially_covered": 1, "uncovered": 0, "unknown": 3},
            "symbols": [
                {
                    "qualified_name": "helper",
                    "file_path": "app/service.py",
                    "status": "covered",
                    "executable_line_count": 1,
                    "executed_line_count": 1,
                }
            ],
        },
        "diagnostics": {},
        "exclusions": [],
        "warnings": [],
    }
    rendered = render_markdown_report(data)
    assert "| covered | 2 |" in rendered
    assert "| partially_covered | 1 |" in rendered
    assert "| helper | app/service.py | covered | 1 | 1 |" in rendered
    assert "_No target symbols were selected._" in rendered
