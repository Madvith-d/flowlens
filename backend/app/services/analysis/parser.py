"""Python AST extraction (Phase 4A).

Static only: files are read and parsed with the standard library `ast` module.
Analyzed code is never imported, executed, or installed, and no attempt is made
to resolve dependencies here — call expressions are recorded as expressions for
the resolver phase.

Extraction covers modules, classes (bases), functions, async functions,
methods, nested definitions, decorators, imports, and call expressions with
file-relative line/column spans. Per-file syntax errors produce diagnostics and
the remaining files continue to be parsed.
"""

import ast
import hashlib
import io
import json
import logging
import tokenize
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

logger = logging.getLogger("flowlens.parser")

# Deterministic ID length (hex chars of a SHA-256 digest).
SYMBOL_ID_LENGTH = 40


@dataclass(frozen=True)
class ParsedCall:
    callee_expression: str
    line: int
    column: int


@dataclass(frozen=True)
class ParsedImport:
    module: str | None
    names: tuple[str, ...]
    level: int
    line: int


@dataclass
class ParsedSymbol:
    id: str
    kind: str
    name: str
    qualified_name: str
    parent_id: str | None
    file_path: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "error"
    file_path: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass
class ParsedFile:
    path: str
    size_bytes: int
    sha256: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    has_syntax_error: bool = False


def module_name_from_path(rel_path: str) -> str:
    """Dotted module name for a snapshot-relative Python file path."""
    parts = list(PurePosixPath(rel_path).parts)
    if not parts:
        return ""
    filename = parts[-1]
    if filename.endswith(".py"):
        stem = filename[:-3]
    else:
        stem = filename
    packages = parts[:-1]
    if stem == "__init__":
        return ".".join(packages) if packages else "__init__"
    return ".".join([*packages, stem])


def symbol_id(analysis_id: str, file_path: str, kind: str, qualified_name: str, start_line: int, end_line: int) -> str:
    """Deterministic, collision-safe symbol ID within one analysis."""
    key = f"{analysis_id}|{file_path}|{kind}|{qualified_name}|{start_line}|{end_line}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:SYMBOL_ID_LENGTH]


def _expression_text(node: ast.AST, limit: int = 300) -> str:
    try:
        text = ast.unparse(node)
    except Exception:  # pragma: no cover - unparse is robust on stdlib ASTs
        text = ast.dump(node)[:limit]
    text = " ".join(text.split())
    return text[:limit]


def _decorator_texts(node: ast.AST) -> list[str]:
    return [_expression_text(decorator) for decorator in getattr(node, "decorator_list", [])]


def _import_record(node: ast.AST) -> ParsedImport:
    if isinstance(node, ast.Import):
        names = tuple(alias.name for alias in node.names)
        return ParsedImport(module=None, names=names, level=0, line=node.lineno)
    names = tuple(alias.name for alias in node.names)
    return ParsedImport(
        module=node.module,
        names=names,
        level=getattr(node, "level", 0) or 0,
        line=node.lineno,
    )


class _FileVisitor:
    """Walks one parsed module, attributing definitions/calls/imports to symbols.

    Defines the symbol tree: module → class/function → (method | nested
    function). Call expressions are attributed to the nearest enclosing symbol
    only, so nested definitions never double-count their own calls.
    """

    def __init__(self, analysis_id: str, file_path: str, module_name: str, max_calls: int) -> None:
        self.analysis_id = analysis_id
        self.file_path = file_path
        self.module_name = module_name
        self.max_calls = max_calls
        self.symbols: list[ParsedSymbol] = []
        self._limit_reached = False

    # ------------------------------------------------------------- helpers
    def _make_symbol(
        self,
        node: ast.AST,
        *,
        kind: str,
        name: str,
        qualified_name: str,
        parent_id: str | None,
        start_line: int,
        end_line: int,
    ) -> ParsedSymbol:
        return ParsedSymbol(
            id=symbol_id(
                self.analysis_id, self.file_path, kind, qualified_name, start_line, end_line
            ),
            kind=kind,
            name=name,
            qualified_name=qualified_name,
            parent_id=parent_id,
            file_path=self.file_path,
            start_line=start_line,
            end_line=end_line,
            start_column=getattr(node, "col_offset", 0),
            end_column=getattr(node, "end_col_offset", 0) or 0,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=_decorator_texts(node),
            bases=(
                [_expression_text(base) for base in node.bases]
                if isinstance(node, ast.ClassDef)
                else []
            ),
        )

    def _record_calls(self, node: ast.AST, symbol: ParsedSymbol) -> None:
        """Attribute call expressions to `symbol`, skipping nested definitions."""
        stack = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Nested definitions own their own calls.
                continue
            if isinstance(child, ast.Call):
                if len(symbol.calls) < self.max_calls:
                    symbol.calls.append(
                        ParsedCall(
                            callee_expression=_expression_text(child.func),
                            line=getattr(child, "lineno", 0),
                            column=getattr(child, "col_offset", 0),
                        )
                    )
            stack.extend(ast.iter_child_nodes(child))

    def _record_imports(self, node: ast.AST, symbol: ParsedSymbol) -> None:
        stack = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                symbol.imports.append(_import_record(child))
            stack.extend(ast.iter_child_nodes(child))

    # ----------------------------------------------------------- traversal
    def visit_module(self, tree: ast.Module, module_qualified_name: str, line_count: int) -> None:
        name = module_qualified_name.rsplit(".", 1)[-1] if module_qualified_name else ""
        module_symbol = ParsedSymbol(
            id=symbol_id(self.analysis_id, self.file_path, "module", module_qualified_name, 1, max(line_count, 1)),
            kind="module",
            name=name,
            qualified_name=module_qualified_name,
            parent_id=None,
            file_path=self.file_path,
            start_line=1,
            end_line=max(line_count, 1),
            start_column=0,
            end_column=0,
        )
        self.symbols.append(module_symbol)
        self._record_imports(tree, module_symbol)
        self._record_calls(tree, module_symbol)
        self._visit_body(tree.body, parent=module_symbol, dot_path=[])

    def _visit_body(self, body: list[ast.stmt], *, parent: ParsedSymbol, dot_path: list[str]) -> None:
        """Walk a body, assigning qualified names as `module:Dotted.Path`."""
        for node in body:
            if isinstance(node, ast.ClassDef):
                child_path = [*dot_path, node.name]
                qualified = f"{self.module_name}:{'.'.join(child_path)}"
                symbol = self._make_symbol(
                    node,
                    kind="class",
                    name=node.name,
                    qualified_name=qualified,
                    parent_id=parent.id,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                )
                self.symbols.append(symbol)
                self._record_calls(node, symbol)
                self._visit_body(node.body, parent=symbol, dot_path=child_path)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_path = [*dot_path, node.name]
                kind = "method" if parent.kind == "class" else "function"
                qualified = f"{self.module_name}:{'.'.join(child_path)}"
                symbol = self._make_symbol(
                    node,
                    kind=kind,
                    name=node.name,
                    qualified_name=qualified,
                    parent_id=parent.id,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                )
                self.symbols.append(symbol)
                self._record_calls(node, symbol)
                self._record_imports(node, symbol)
                self._visit_body(node.body, parent=symbol, dot_path=child_path)


def _decode_source(raw: bytes) -> tuple[str, str]:
    """Decode Python source honoring PEP 263 coding declarations."""
    encoding, _lines = tokenize.detect_encoding(io.BytesIO(raw).readline)
    return raw.decode(encoding), encoding


def parse_python_file(
    abs_path: Path,
    rel_path: str,
    *,
    analysis_id: str,
    max_file_bytes: int,
    max_calls_per_symbol: int,
) -> ParsedFile:
    """Parse one Python file. Never raises for malformed input; emits diagnostics."""
    raw = abs_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    parsed = ParsedFile(path=rel_path, size_bytes=len(raw), sha256=digest)
    if len(raw) > max_file_bytes:
        parsed.diagnostics.append(
            Diagnostic(
                code="FILE_TOO_LARGE",
                message="File exceeds the analysis size limit and was skipped.",
                severity="warning",
                file_path=rel_path,
            )
        )
        return parsed
    try:
        source_text, _encoding = _decode_source(raw)
    except (UnicodeDecodeError, SyntaxError) as exc:
        parsed.diagnostics.append(
            Diagnostic(
                code="SOURCE_ENCODING_ERROR",
                message=f"Source could not be decoded: {type(exc).__name__}.",
                file_path=rel_path,
            )
        )
        return parsed
    try:
        tree = ast.parse(source_text, filename=rel_path)
    except SyntaxError as exc:
        parsed.has_syntax_error = True
        parsed.diagnostics.append(
            Diagnostic(
                code="SYNTAX_ERROR",
                message=f"Syntax error: {exc.msg}",
                file_path=rel_path,
                line=exc.lineno,
                column=exc.offset,
            )
        )
        return parsed
    module_name = module_name_from_path(rel_path)
    line_count = source_text.count("\n") + (0 if source_text.endswith("\n") else 1)
    visitor = _FileVisitor(analysis_id, rel_path, module_name, max_calls_per_symbol)
    visitor.visit_module(tree, module_name, line_count)
    parsed.symbols = visitor.symbols
    return parsed


def collect_python_files(snapshot_root: Path, excluded_names: set[str]) -> list[str]:
    """Snapshot-relative paths of Python files, deterministically sorted."""
    results: list[str] = []
    for path in sorted(snapshot_root.rglob("*.py")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(snapshot_root).parts
        if any(part in excluded_names for part in rel_parts):
            continue
        results.append("/".join(rel_parts))
    return results


def symbol_imports_to_json(imports: list[ParsedImport]) -> str:
    return json.dumps(
        [
            {"module": item.module, "names": list(item.names), "level": item.level, "line": item.line}
            for item in imports
        ],
        separators=(",", ":"),
    )


def symbol_json_list(items: list[str]) -> str:
    return json.dumps(items, separators=(",", ":"))
