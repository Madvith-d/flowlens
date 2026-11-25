"""Unit tests: AST extraction (symbols, spans, qualified names, diagnostics)."""

from pathlib import Path

from app.services.analysis.parser import (
    collect_python_files,
    module_name_from_path,
    parse_python_file,
    symbol_id,
)

ANALYSIS_ID = "analysis-test"

SOURCE = '''\
import os
from typing import Any


@decorator
class Widget(SomeBase, "MixinLike"):
    """Class docstring."""

    @staticmethod
    def build(value):
        return Widget()

    async def fetch(self, url):
        return await helper(url)


class Sub(Widget):
    def ping(self):
        return 1


def top_level(a, b=2):
    inner = lambda x: x

    def nested():
        return os.getcwd()

    return nested() and inner(a)


async def async_top():
    return await top_level(1)
'''


def write_file(tmp_path: Path, rel: str, content: str | bytes) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    return path


def parse(tmp_path, rel, content=None, *, source=SOURCE):
    body = content if content is not None else source
    path = write_file(tmp_path, rel, body)
    return parse_python_file(
        path,
        rel,
        analysis_id=ANALYSIS_ID,
        max_file_bytes=1024 * 1024,
        max_calls_per_symbol=50,
    )


def test_module_name_from_path():
    assert module_name_from_path("app/main.py") == "app.main"
    assert module_name_from_path("app/__init__.py") == "app"
    assert module_name_from_path("main.py") == "main"
    assert module_name_from_path("__init__.py") == "__init__"
    assert module_name_from_path("a/b/c/mod.py") == "a.b.c.mod"


def test_extracts_symbols_and_kinds(tmp_path):
    parsed = parse(tmp_path, "app/service.py")
    by_name = {symbol.qualified_name: symbol for symbol in parsed.symbols}

    module = by_name["app.service"]
    assert module.kind == "module"
    assert module.start_line == 1
    assert module.parent_id is None

    widget = by_name["app.service:Widget"]
    assert widget.kind == "class"
    assert widget.bases == ["SomeBase", "'MixinLike'"]
    assert widget.decorators == ["decorator"]
    assert widget.start_line > 1
    assert widget.end_line >= widget.start_line

    build = by_name["app.service:Widget.build"]
    assert build.kind == "method"
    assert build.parent_id == widget.id
    assert build.start_column >= 0

    fetch = by_name["app.service:Widget.fetch"]
    assert fetch.kind == "method"
    assert fetch.is_async is True

    sub = by_name["app.service:Sub"]
    assert sub.bases == ["Widget"]

    top = by_name["app.service:top_level"]
    assert top.kind == "function"
    assert top.parent_id == module.id
    assert top.is_async is False

    nested = by_name["app.service:top_level.nested"]
    assert nested.kind == "function"
    assert nested.parent_id == top.id

    async_top = by_name["app.service:async_top"]
    assert async_top.is_async is True


def test_spans_cover_source_lines(tmp_path):
    parsed = parse(tmp_path, "app/service.py")
    lines = SOURCE.splitlines()
    for symbol in parsed.symbols:
        if symbol.kind == "module":
            continue
        assert 1 <= symbol.start_line <= len(lines)
        assert symbol.start_line <= symbol.end_line <= len(lines)


def test_calls_attributed_to_nearest_symbol(tmp_path):
    parsed = parse(tmp_path, "app/service.py")
    by_name = {symbol.qualified_name: symbol for symbol in parsed.symbols}

    nested_calls = [call.callee_expression for call in by_name["app.service:top_level.nested"].calls]
    assert "os.getcwd" in nested_calls

    top_calls = [call.callee_expression for call in by_name["app.service:top_level"].calls]
    # Nested definitions own their own calls (no double counting from the parent).
    assert "os.getcwd" not in top_calls
    assert "inner" in top_calls

    method_calls = [call.callee_expression for call in by_name["app.service:Widget.build"].calls]
    assert "Widget" in method_calls


def test_imports_recorded_on_enclosing_symbol(tmp_path):
    parsed = parse(tmp_path, "app/service.py")
    module = next(s for s in parsed.symbols if s.kind == "module")
    records = {(item.module, item.names) for item in module.imports}
    assert (None, ("os",)) in records
    assert ("typing", ("Any",)) in records


def test_syntax_error_produces_diagnostic_and_no_symbols(tmp_path):
    parsed = parse(tmp_path, "app/broken.py", "def nope(:\n    pass\n")
    assert parsed.has_syntax_error is True
    assert parsed.symbols == []
    diagnostic = parsed.diagnostics[0]
    assert diagnostic.code == "SYNTAX_ERROR"
    assert diagnostic.file_path == "app/broken.py"
    assert diagnostic.line is not None


def test_syntax_error_in_one_file_does_not_stop_others(tmp_path):
    good = parse(tmp_path, "app/good.py", "def works():\n    return 1\n")
    bad = parse(tmp_path, "app/bad.py", "def broken(:\n")
    assert bad.has_syntax_error is True
    assert [s.name for s in good.symbols] == ["good", "works"]


def test_file_too_large_skipped(tmp_path):
    path = write_file(tmp_path, "app/big.py", "x = 1\n" * 200)
    parsed = parse_python_file(
        path,
        "app/big.py",
        analysis_id=ANALYSIS_ID,
        max_file_bytes=64,
        max_calls_per_symbol=10,
    )
    assert parsed.symbols == []
    assert parsed.diagnostics[0].code == "FILE_TOO_LARGE"


def test_encoding_error_diagnostic(tmp_path):
    parsed = parse(tmp_path, "app/latin.py", b"# -*- coding: utf-8 -*-\nx = '\xff\xfe'\n")
    assert parsed.symbols == []
    assert parsed.diagnostics[0].code == "SOURCE_ENCODING_ERROR"


def test_pep263_encoding_declaration_honored(tmp_path):
    body = "# -*- coding: latin-1 -*-\n\ndef caf\xe9():\n    return 1\n".encode("latin-1")
    parsed = parse(tmp_path, "app/legacy.py", body)
    assert [s.name for s in parsed.symbols] == ["legacy", "café"]


def test_duplicate_symbol_names_across_files_stay_distinct(tmp_path):
    first = parse(tmp_path, "pkg/a.py", "def thing():\n    return 1\n")
    second = parse(tmp_path, "pkg/b.py", "def thing():\n    return 1\n")
    first_thing = next(s for s in first.symbols if s.name == "thing")
    second_thing = next(s for s in second.symbols if s.name == "thing")
    assert first_thing.qualified_name == "pkg.a:thing"
    assert second_thing.qualified_name == "pkg.b:thing"
    assert first_thing.id != second_thing.id


def test_symbol_ids_deterministic(tmp_path):
    parsed_one = parse(tmp_path, "app/service.py")
    parsed_two = parse(tmp_path, "app/service.py")
    assert [s.id for s in parsed_one.symbols] == [s.id for s in parsed_two.symbols]
    assert symbol_id(ANALYSIS_ID, "app/service.py", "class", "app.service:Widget", 6, 17) == symbol_id(
        ANALYSIS_ID, "app/service.py", "class", "app.service:Widget", 6, 17
    )


def test_lambda_and_comprehensions_do_not_create_symbols(tmp_path):
    parsed = parse(tmp_path, "app/mod.py", "f = lambda x: x\nvals = [i for i in range(3)]\n")
    assert [s.name for s in parsed.symbols] == ["mod"]


def test_nested_classes_and_methods(tmp_path):
    source = (
        "class Outer:\n"
        "    class Inner:\n"
        "        def deep(self):\n"
        "            return 1\n"
        "\n"
        "    def shallow(self):\n"
        "        return 2\n"
    )
    parsed = parse(tmp_path, "app/nested.py", source)
    names = [s.qualified_name for s in parsed.symbols]
    assert names == [
        "app.nested",
        "app.nested:Outer",
        "app.nested:Outer.Inner",
        "app.nested:Outer.Inner.deep",
        "app.nested:Outer.shallow",
    ]
    outer = next(s for s in parsed.symbols if s.qualified_name == "app.nested:Outer")
    inner = next(s for s in parsed.symbols if s.qualified_name == "app.nested:Outer.Inner")
    assert inner.parent_id == outer.id
    kinds = {s.qualified_name: s.kind for s in parsed.symbols}
    assert kinds["app.nested:Outer.Inner"] == "class"
    assert kinds["app.nested:Outer.Inner.deep"] == "method"


def test_source_is_never_executed(tmp_path):
    marker = tmp_path / "executed.marker"
    source = f"open({str(marker)!r}, 'w').write('executed')\n"
    parse(tmp_path, "app/malicious.py", source)
    assert not marker.exists()


def test_collect_python_files_respects_exclusions(tmp_path):
    for rel in ["app/main.py", ".git/hook.py", "__pycache__/x.py", "venv/lib/y.py", "README.md"]:
        write_file(tmp_path, rel, "x = 1\n")
    files = collect_python_files(tmp_path, {"__pycache__", ".git", "venv"})
    assert files == ["app/main.py"]
