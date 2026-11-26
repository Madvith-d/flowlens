"""Resolver unit tests (Phase 5A).

Drives the real parser (4A extraction) into the resolver and asserts typed,
evidence-carrying edges plus explicit unresolved/ambiguous diagnostics for the
fixture cases required by the phase: aliases, circular imports, inheritance,
method calls, unresolved dynamic calls, and duplicate symbol names.
"""

from pathlib import Path

from app.services.analysis.parser import parse_python_file
from app.services.analysis.resolver import StaticResolver, SymbolRecord, CallRecord

ANALYSIS = "analysis-test"


def build_records(tmp_path: Path, files: dict[str, str]):
    """Parse a fixture project on disk → resolver records + calls."""
    symbols: list[SymbolRecord] = []
    calls: list[CallRecord] = []
    for rel_path in sorted(files):
        abs_path = tmp_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(files[rel_path], encoding="utf-8")
        parsed = parse_python_file(
            abs_path,
            rel_path,
            analysis_id=ANALYSIS,
            max_file_bytes=1024 * 1024,
            max_calls_per_symbol=2_000,
        )
        for symbol in parsed.symbols:
            symbols.append(
                SymbolRecord(
                    id=symbol.id,
                    kind=symbol.kind,
                    name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    file_path=symbol.file_path,
                    parent_id=symbol.parent_id,
                    start_line=symbol.start_line,
                    bases=tuple(symbol.bases),
                    imports=tuple(symbol.imports),
                )
            )
            for call in symbol.calls:
                calls.append(
                    CallRecord(
                        caller_id=symbol.id,
                        expression=call.callee_expression,
                        line=call.line,
                        column=call.column,
                    )
                )
    return symbols, calls


def resolve(tmp_path: Path, files: dict[str, str]):
    symbols, calls = build_records(tmp_path, files)
    resolver = StaticResolver(ANALYSIS)
    return resolver.resolve(
        symbols,
        calls,
        max_evidence_per_edge=10,
        max_reference_diagnostics=1_000,
    ), {s.qualified_name: s for s in symbols}


def edges_with_names(result, q):
    """(source, target, kind) triples qualified-name pairs for readability."""
    by_id = {symbol.id: symbol.qualified_name for symbol in q.values()}
    return {
        (by_id[edge.source_id], by_id[edge.target_id], edge.kind) for edge in result.edges
    }


FIXTURE = {
    "pkg/__init__.py": "",
    "pkg/base.py": (
        "def standalone():\n"
        "    return helper_local()\n"
        "\n"
        "def helper_local():\n"
        "    return 1\n"
        "\n"
        "class Base:\n"
        "    def ping(self):\n"
        "        return 1\n"
        "\n"
        "    def pong(self):\n"
        "        return self.ping()\n"
    ),
    "pkg/alias.py": (
        "from pkg.base import Base as B, standalone as call_it\n"
        "\n"
        "class Child(B):\n"
        "    def method(self):\n"
        "        call_it()\n"
        "        return self.pong()\n"
        "\n"
        "    def construct(self):\n"
        "        return B()\n"
    ),
    "pkg/circular_a.py": (
        "from pkg import circular_b as cb\n"
        "\n"
        "def a_func():\n"
        "    return cb.b_func()\n"
    ),
    "pkg/circular_b.py": (
        "from pkg import circular_a as ca\n"
        "\n"
        "def b_func():\n"
        "    return ca.a_func()\n"
    ),
    "pkg/dup.py": (
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def helper():\n"
        "    return 2\n"
        "\n"
        "def caller():\n"
        "    return helper()\n"
    ),
    "pkg/absolute.py": (
        "import json\n"
        "\n"
        "def uses_json():\n"
        "    return json.dumps({'a': 1})\n"
        "\n"
        "def calls_sibling():\n"
        "    return pkg.base.standalone()\n"
    ),
    "pkg/sub/__init__.py": "",
    "pkg/sub/mod.py": (
        "from ..base import standalone as far\n"
        "from . import sibling as sib\n"
        "\n"
        "def uses_them():\n"
        "    far()\n"
        "    return sib.sibling_func()\n"
    ),
    "pkg/sub/sibling.py": (
        "def sibling_func():\n"
        "    return 2\n"
    ),
    "pkg/dynamic.py": (
        "class Thing:\n"
        "    def ping(self):\n"
        "        return 1\n"
        "\n"
        "    def invoke(self):\n"
        "        return getattr(self, 'ping')()\n"
    ),
}


def test_lexical_module_call_resolves(tmp_path):
    result, q = resolve(tmp_path, {"single.py": "def a():\n    return b()\n\ndef b():\n    return 1\n"})
    assert ("single:a", "single:b", "CALLS") in edges_with_names(result, q)
    assert result.unresolved_count == 0


def edges_with_names(result, q):
    by_id = {sid: name for sid, name in ((s.id, s.qualified_name) for s in q.values())}
    return {
        (by_id[edge.source_id], by_id[edge.target_id], edge.kind) for edge in result.edges
    }


def test_fixture_edges(tmp_path):
    result, q = resolve(tmp_path, FIXTURE)
    pairs = edges_with_names(result, q)

    # Lexical module-level call.
    assert ("pkg.base:standalone", "pkg.base:helper_local", "CALLS") in pairs
    # self-call resolved lexically.
    assert ("pkg.base:Base.pong", "pkg.base:Base.ping", "CALLS") in pairs
    # Aliases: ``standalone as call_it`` and ``Base as B``.
    assert ("pkg.alias:Child.method", "pkg.base:standalone", "CALLS") in pairs
    assert ("pkg.alias:Child.construct", "pkg.base:Base", "CALLS") in pairs
    # Inheritance edge + inherited method resolution.
    assert ("pkg.alias:Child", "pkg.base:Base", "INHERITS") in pairs
    assert ("pkg.alias:Child.method", "pkg.base:Base.pong", "CALLS") in pairs
    # Circular imports/modules both directions; bindings via package import.
    assert ("pkg.circular_a", "pkg.circular_b", "IMPORTS") in pairs
    assert ("pkg.circular_b", "pkg.circular_a", "IMPORTS") in pairs
    assert ("pkg.circular_a:a_func", "pkg.circular_b:b_func", "CALLS") in pairs
    assert ("pkg.circular_b:b_func", "pkg.circular_a:a_func", "CALLS") in pairs
    # Relative imports resolve to the right modules and symbols.
    assert ("pkg.sub.mod", "pkg.base", "IMPORTS") in pairs
    assert ("pkg.sub.mod", "pkg.sub.sibling", "IMPORTS") in pairs
    assert ("pkg.sub.mod:uses_them", "pkg.base:standalone", "CALLS") in pairs
    assert ("pkg.sub.mod:uses_them", "pkg.sub.sibling:sibling_func", "CALLS") in pairs
    # Absolute module-qualified call.
    assert ("pkg.absolute:calls_sibling", "pkg.base:standalone", "CALLS") in pairs
    # External imports create no edges.
    assert all(target[0] != "json" for target in pairs)
    assert all("json" not in source for source, _, _ in pairs)


def test_edge_kinds_and_evidence(tmp_path):
    result, _q = resolve(tmp_path, FIXTURE)
    assert {edge.kind for edge in result.edges} <= {"CALLS", "IMPORTS", "INHERITS"}
    for edge in result.edges:
        assert edge.evidence, "every dependency edge carries source evidence"
        for item in edge.evidence:
            assert item.file_path
            assert item.line >= 0
            assert item.expression


def test_unresolved_and_ambiguous(tmp_path):
    result, q = resolve(tmp_path, FIXTURE)
    pairs = edges_with_names(result, q)
    # Duplicate module-level name stays unresolved, never guessed…
    assert ("pkg.dup:caller", "pkg.dup:helper", "CALLS") not in pairs
    codes = {item.code for item in result.diagnostics}
    assert "AMBIGUOUS_REFERENCE" in codes
    # …and the exact counters are reported.
    assert result.ambiguous_count >= 1
    # json (external) and pkg.base.standalone-adjacent root remain unresolved.
    assert result.unresolved_count >= 1
    assert "UNRESOLVED_REFERENCE" in codes
    # Dynamic calls are never guessed.
    assert ("pkg.dynamic:Thing.invoke", "pkg.dynamic:Thing.ping", "CALLS") not in pairs


def test_deterministic_and_stable(tmp_path):
    first, _ = resolve(tmp_path, FIXTURE)
    second, _ = resolve(tmp_path, FIXTURE)
    key = lambda r: [(e.source_id, e.target_id, e.kind, e.resolver, e.confidence, tuple(e.evidence)) for e in r.edges]  # noqa: E731
    assert key(first) == key(second)
    # Deduplicated: no (source, target, kind) duplicates.
    seen = [(e.source_id, e.target_id, e.kind) for e in first.edges]
    assert len(seen) == len(set(seen))
    # Confidence aggregation stays conservative.
    for edge in first.edges:
        assert edge.confidence in ("high", "medium", "low")


def test_resolvers_named(tmp_path):
    result, _ = resolve(tmp_path, FIXTURE)
    resolvers = {edge.resolver for edge in result.edges}
    assert {"lexical_module", "lexical_self_method", "import_from", "module_alias", "inherited_method", "base_resolution", "module_import", "module_qualified"} <= resolvers
    # Inherited method resolution is marked medium confidence.
    inherited = [e for e in result.edges if e.resolver == "inherited_method"]
    assert inherited and all(e.confidence == "medium" for e in inherited)
