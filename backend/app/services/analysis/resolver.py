"""Dependency resolution (Phase 5A) over stored symbol/call/import records.

The resolver is a pure transformation: it consumes plain records (symbols,
calls, imports) produced by *any* extraction pipeline and emits typed,
deduplicated dependency edges plus explicit unresolved/ambiguous diagnostics.
It never imports, executes, or installs analyzed code and never guesses: an
ambiguous or unresolvable reference stays unresolved rather than being pinned
to a wrong symbol.

Resolution strategies (each edge records its `resolver` name and confidence):

* ``lexical_module`` (high) — a call to a name that is uniquely defined in
  the caller's own module.
* ``import_from`` (high) — a call to a name bound by ``from m import x`` /
  ``from m import x as y`` (absolute or relative) where ``m:x`` exists.
* ``module_alias`` (high) — a call through a bound module
  (``import m as x`` / ``from p import m as x``).
* ``module_qualified`` (high) — ``module.attr(...)`` (any depth) where the
  absolute module and attribute path exist in the snapshot.
* ``lexical_self_method`` (high) — ``self.name(...)`` resolved to a method of
  the lexically enclosing class.
* ``inherited_method`` (medium) — ``self.name(...)`` only defined on an
  ancestor class resolvable within the snapshot.
* ``class_method`` (medium) — ``ClassName.name(...)`` where ``ClassName`` is
  a resolvable class in the caller's module.
* ``module_import`` (high) — IMPORTS edge from a module onto a module that is
  itself part of the snapshot (imports of external/stdlib modules are out of
  scope: they are not edges and not diagnostics).
* ``base_resolution`` (high) — INHERITS edge from a class onto a resolvable
  base class.

Aggregation: edges are deduplicated on ``(source, target, kind)``; the stored
``confidence`` is the weakest (most conservative) of the contributing
resolutions and ``resolver`` names the strategy of the strongest
contribution (ties broken lexicographically). Two definitions sharing a
qualified name make that name ambiguous, not guessed. ``CONTAINS`` is never
produced here — it is structural and derived from ``Symbol.parent_id`` at
graph-build time.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("flowlens.resolver")

EDGE_ID_LENGTH = 40
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

# Sentinel for "resolvable but not uniquely" (never silently guessed).
_AMBIGUOUS = object()


# -------------------------------------------------------------------- records
@dataclass(frozen=True)
class ImportRecord:
    """One import statement as seen by the extraction pipeline."""

    module: str | None
    names: tuple[str, ...]
    bindings: tuple[str, ...]
    level: int
    line: int


def import_records_from_json(raw: str) -> tuple[ImportRecord, ...]:
    """Parse the stored per-symbol imports JSON (post- and pre-5A shapes)."""
    items = json.loads(raw or "[]")
    records: list[ImportRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        names = tuple(str(name) for name in item.get("names", ()))
        raw_bindings = item.get("bindings")
        if isinstance(raw_bindings, list) and len(raw_bindings) == len(names):
            bindings = tuple(str(name) for name in raw_bindings)
        else:
            bindings = names
        records.append(
            ImportRecord(
                module=item.get("module"),
                names=names,
                bindings=bindings,
                level=int(item.get("level", 0) or 0),
                line=int(item.get("line", 0) or 0),
            )
        )
    return tuple(records)


@dataclass(frozen=True)
class SymbolRecord:
    id: str
    kind: str
    name: str
    qualified_name: str
    file_path: str
    parent_id: str | None
    start_line: int
    bases: tuple[str, ...]
    imports: tuple[ImportRecord, ...]


@dataclass(frozen=True)
class CallRecord:
    caller_id: str
    expression: str
    line: int
    column: int


@dataclass(frozen=True)
class Evidence:
    file_path: str
    line: int
    column: int
    expression: str


@dataclass(frozen=True)
class EdgeRecord:
    source_id: str
    target_id: str
    kind: str
    confidence: str
    resolver: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ResolverDiagnostic:
    code: str
    message: str
    severity: str
    file_path: str | None
    line: int | None
    column: int | None


@dataclass
class ResolutionResult:
    edges: list[EdgeRecord] = field(default_factory=list)
    diagnostics: list[ResolverDiagnostic] = field(default_factory=list)
    unresolved_count: int = 0
    ambiguous_count: int = 0


class DependencyResolver(Protocol):
    """Resolver interface, independent of how records were extracted."""

    def resolve(
        self,
        symbols: list[SymbolRecord],
        calls: list[CallRecord],
        *,
        max_evidence_per_edge: int,
        max_reference_diagnostics: int,
    ) -> ResolutionResult: ...


def edge_id(analysis_id: str, source_id: str, target_id: str, kind: str) -> str:
    """Deterministic, collision-safe edge ID within one analysis."""
    key = f"{analysis_id}|{source_id}|{target_id}|{kind}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:EDGE_ID_LENGTH]


# ---------------------------------------------------------------------- index
class _ResolverIndex:
    """Lookups over one analysis' symbols: modules, names, children."""

    def __init__(self, symbols: list[SymbolRecord]) -> None:
        self.symbols_by_id: dict[str, SymbolRecord] = {s.id: s for s in symbols}
        self.module_of_file: dict[str, str] = {}
        self.module_ids: dict[str, str] = {}
        self.qname: dict[str, SymbolRecord] = {}
        self.ambiguous_qnames: set[str] = set()
        self.by_module_and_name: dict[tuple[str, str], list[SymbolRecord]] = {}
        self.children_of: dict[str, list[SymbolRecord]] = {}
        for symbol in symbols:
            if symbol.qualified_name in self.qname:
                # Duplicate qualified name (e.g. a redefinition): ambiguous.
                self.ambiguous_qnames.add(symbol.qualified_name)
                self.qname.pop(symbol.qualified_name, None)
            else:
                self.qname[symbol.qualified_name] = symbol
            if symbol.parent_id:
                self.children_of.setdefault(symbol.parent_id, []).append(symbol)
            if symbol.kind == "module":
                self.module_of_file[symbol.file_path] = symbol.qualified_name
                self.module_ids[symbol.qualified_name] = symbol.id
        for symbol in symbols:
            self.by_module_and_name.setdefault((self.module_of(symbol), symbol.name), []).append(symbol)

    def module_of(self, symbol: SymbolRecord) -> str:
        module = symbol.qualified_name.split(":", 1)[0]
        return module or "__init__"

    def qname_symbol(self, qualified_name: str) -> SymbolRecord | None:
        """Unique symbol for a qualified name; ambiguous names resolve to None."""
        if qualified_name in self.ambiguous_qnames:
            return None
        return self.qname.get(qualified_name)

    def matches_in_module(self, module: str, name: str) -> list[SymbolRecord]:
        return self.by_module_and_name.get((module, name), [])

    def children_named(self, parent_id: str, name: str, kinds: tuple[str, ...]) -> list[SymbolRecord]:
        return [
            symbol
            for symbol in self.children_of.get(parent_id, ())
            if symbol.name == name and symbol.kind in kinds
        ]

    def enclosing_class(self, symbol: SymbolRecord) -> SymbolRecord | None:
        """Nearest enclosing class along the lexical parent chain."""
        current = symbol
        seen: set[str] = {symbol.id}
        while current.parent_id and current.parent_id not in seen:
            seen.add(current.parent_id)
            parent = self.symbols_by_id.get(current.parent_id)
            if parent is None:
                return None
            if parent.kind == "class":
                return parent
            current = parent
        return None


class _ImportMap:
    """Name bindings visible per module file (module scope + caller symbol)."""

    def __init__(self, index: _ResolverIndex, symbols: list[SymbolRecord]) -> None:
        self.index = index
        self._file_imports: dict[str, list[ImportRecord]] = {}
        self._symbol_imports: dict[str, list[ImportRecord]] = {}
        for symbol in symbols:
            if symbol.imports:
                self._file_imports.setdefault(symbol.file_path, []).extend(symbol.imports)
                if symbol.kind != "module":
                    self._symbol_imports.setdefault(symbol.id, []).extend(symbol.imports)
        self._binding_cache: dict[str, dict[str, str]] = {}

    def _base_module(self, module: str | None, level: int, file_path: str) -> str | None:
        """Absolute module prefix of a (possibly relative) import."""
        if level == 0:
            return module
        module_name = self.index.module_of_file.get(file_path)
        if module_name is None:
            return None
        # The containing package: for a package __init__ it is the module
        # itself; for a plain module file it is the parent package. Each
        # additional dot climbs one package further.
        parts = module_name.split(".")
        package_parts = parts if file_path.endswith("__init__.py") else parts[:-1]
        for _ in range(level - 1):
            if not package_parts:
                return None
            package_parts = package_parts[:-1]
        base = ".".join(package_parts)
        return f"{base}.{module}" if module else base

    def bindings_for(self, file_path: str, symbol_id: str | None) -> dict[str, str]:
        """Bound name → fully-qualified target (``module`` or ``module:name``)."""
        cache_key = f"{file_path}|{symbol_id or ''}"
        cached = self._binding_cache.get(cache_key)
        if cached is not None:
            return cached
        bindings: dict[str, str] = {}
        for record in self._file_imports.get(file_path, []):
            self._add_record_bindings(bindings, record, file_path)
        if symbol_id:
            for record in self._symbol_imports.get(symbol_id, []):
                self._add_record_bindings(bindings, record, file_path)
        self._binding_cache[cache_key] = bindings
        return bindings

    def _add_record_bindings(
        self, bindings: dict[str, str], record: ImportRecord, file_path: str
    ) -> None:
        pairs = (
            list(zip(record.names, record.bindings))
            if record.bindings and len(record.bindings) == len(record.names)
            else list(zip(record.names, record.names))
        )
        for name, binding in pairs:
            if record.module is None and record.level == 0:
                # Plain ``import x.y [as z]``: bind to snapshot modules only.
                if name in self.index.module_ids:
                    bindings[binding] = name
                    root = name.split(".")[0]
                    if root in self.index.module_ids:
                        bindings.setdefault(root, root)
                continue
            base = self._base_module(record.module, record.level, file_path)
            if base is None:
                continue
            target = f"{base}:{name}"
            if self.index.qname_symbol(target) is not None:
                bindings[binding] = target
                continue
            submodule = f"{base}.{name}"
            if submodule in self.index.module_ids:
                bindings[binding] = submodule


class _EdgeAccumulator:
    """Aggregates evidence per (source, target, kind) deterministically."""

    def __init__(self, max_evidence: int) -> None:
        self.max_evidence = max_evidence
        self._entries: dict[tuple[str, str, str], dict] = {}

    def add(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        resolver: str,
        confidence: str,
        evidence: Evidence,
    ) -> None:
        if source_id == target_id:
            return  # self-references carry no dependency information
        key = (source_id, target_id, kind)
        entry = self._entries.get(key)
        if entry is None:
            self._entries[key] = {
                "resolvers": [(resolver, confidence)],
                "evidence": [evidence],
                "evidence_keys": {(evidence.file_path, evidence.line, evidence.column)},
            }
            return
        entry["resolvers"].append((resolver, confidence))
        evidence_key = (evidence.file_path, evidence.line, evidence.column)
        if len(entry["evidence"]) < self.max_evidence and evidence_key not in entry["evidence_keys"]:
            entry["evidence_keys"].add(evidence_key)
            entry["evidence"].append(evidence)

    def result(self) -> list[EdgeRecord]:
        records: list[EdgeRecord] = []
        for key in sorted(self._entries):
            source_id, target_id, kind = key
            entry = self._entries[key]
            ranked = sorted(entry["resolvers"], key=lambda rc: (_CONFIDENCE_RANK.get(rc[1], 99), rc[0]))
            # Conservative: stored confidence is the weakest contribution, the
            # resolver names the strongest strategy (lexicographic tie-break).
            confidence = max(
                (confidence for _, confidence in entry["resolvers"]),
                key=lambda c: _CONFIDENCE_RANK.get(c, 99),
            )
            evidence = tuple(sorted(entry["evidence"], key=lambda e: (e.line, e.column, e.expression)))
            records.append(
                EdgeRecord(
                    source_id=source_id,
                    target_id=target_id,
                    kind=kind,
                    confidence=confidence,
                    resolver=ranked[0][0],
                    evidence=evidence,
                )
            )
        return records


# -------------------------------------------------------------------- resolver
class StaticResolver:
    """Deterministic resolver for stored static-analysis records."""

    def __init__(self, analysis_id: str) -> None:
        self.analysis_id = analysis_id

    def resolve(
        self,
        symbols: list[SymbolRecord],
        calls: list[CallRecord],
        *,
        max_evidence_per_edge: int,
        max_reference_diagnostics: int,
    ) -> ResolutionResult:
        index = _ResolverIndex(symbols)
        imports = _ImportMap(index, symbols)
        accumulator = _EdgeAccumulator(max_evidence_per_edge)
        result = ResolutionResult()
        warnings: dict[tuple[str, str, str], dict] = {}

        self._emit_import_edges(index, imports, accumulator)
        self._emit_inheritance_edges(index, imports, accumulator, warnings)

        for call in sorted(calls, key=lambda c: (c.caller_id, c.line, c.column, c.expression)):
            caller = index.symbols_by_id.get(call.caller_id)
            if caller is None:
                continue  # caller beyond the symbol budget; nothing to attribute
            self._resolve_call(index, imports, accumulator, caller, call, warnings)

        self._collect_reference_diagnostics(warnings, result, max_reference_diagnostics)
        result.edges = accumulator.result()
        logger.info(
            "resolution finished",
            extra={
                "context": {
                    "analysis_id": self.analysis_id,
                    "edges": len(result.edges),
                    "unresolved": result.unresolved_count,
                    "ambiguous": result.ambiguous_count,
                }
            },
        )
        return result

    # ------------------------------------------------------------ import edges
    def _emit_import_edges(
        self,
        index: _ResolverIndex,
        imports: _ImportMap,
        accumulator: _EdgeAccumulator,
    ) -> None:
        """IMPORTS edges between snapshot modules; external imports stay out.

        For from-imports the edge targets what is actually depended on: a
        submodule when the imported name is itself a snapshot module, else the
        module that defines the imported symbols.
        """
        seen: set[tuple[str, str, str]] = set()
        for symbol in sorted(index.symbols_by_id.values(), key=lambda s: s.id):
            if symbol.kind != "module":
                continue
            for record in symbol.imports:
                targets: list[tuple[str, str]] = []  # (module_id, expression)
                if record.module is None and record.level == 0:
                    # Plain ``import x.y``: edge onto the imported module.
                    for name in record.names:
                        if name in index.module_ids:
                            targets.append((index.module_ids[name], f"import {name}"))
                else:
                    base = imports._base_module(record.module, record.level, symbol.file_path)
                    if not base or base == symbol.qualified_name:
                        continue
                    module_targets: list[str] = []
                    for name in record.names:
                        submodule = f"{base}.{name}"
                        if submodule in index.module_ids:
                            module_targets.append(submodule)
                    if not module_targets:
                        module_targets.append(base)
                    expression = f"from {'.' * record.level}{record.module or ''} import {', '.join(record.names)}"
                    for target_module in module_targets:
                        if target_module in index.module_ids:
                            targets.append((index.module_ids[target_module], expression))
                for target_id, expression in targets:
                    if target_id == symbol.id:
                        continue
                    key = (symbol.id, target_id, record.line)
                    if key in seen:
                        continue
                    seen.add(key)
                    accumulator.add(
                        source_id=symbol.id,
                        target_id=target_id,
                        kind="IMPORTS",
                        resolver="module_import",
                        confidence="high",
                        evidence=Evidence(
                            file_path=symbol.file_path,
                            line=record.line,
                            column=0,
                            expression=expression,
                        ),
                    )

    # ------------------------------------------------------- inheritance edges
    def _emit_inheritance_edges(
        self,
        index: _ResolverIndex,
        imports: _ImportMap,
        accumulator: _EdgeAccumulator,
        warnings: dict[tuple[str, str, str], dict],
    ) -> None:
        """INHERITS edges for base classes resolvable within the snapshot."""
        for symbol in sorted(index.symbols_by_id.values(), key=lambda s: s.id):
            if symbol.kind != "class":
                continue
            bindings = imports.bindings_for(symbol.file_path, None)
            for base in symbol.bases:
                if not base:
                    continue
                target = self._resolve_name(index, bindings, imports, symbol, base)
                if target is _AMBIGUOUS:
                    self._warn(
                        warnings,
                        symbol,
                        f"class {symbol.name}({base})",
                        Evidence(symbol.file_path, symbol.start_line, 0, base),
                        "ambiguous",
                    )
                    continue
                if not isinstance(target, SymbolRecord) or target.kind != "class":
                    continue  # external bases (object, framework classes) stay out of scope
                accumulator.add(
                    source_id=symbol.id,
                    target_id=target.id,
                    kind="INHERITS",
                    resolver="base_resolution",
                    confidence="high",
                    evidence=Evidence(
                        file_path=symbol.file_path,
                        line=symbol.start_line,
                        column=0,
                        expression=f"class {symbol.name}({base})",
                    ),
                )

    # ------------------------------------------------------------------ calls
    def _resolve_call(
        self,
        index: _ResolverIndex,
        imports: _ImportMap,
        accumulator: _EdgeAccumulator,
        caller: SymbolRecord,
        call: CallRecord,
        warnings: dict[tuple[str, str, str], dict],
    ) -> None:
        expression = call.expression
        evidence = Evidence(
            file_path=caller.file_path,
            line=call.line,
            column=call.column,
            expression=expression,
        )
        bindings = imports.bindings_for(caller.file_path, caller.id)
        parts = expression.split(".")

        if len(parts) == 1:
            target = self._resolve_name(index, bindings, imports, caller, expression)
            if target is _AMBIGUOUS:
                self._warn(warnings, caller, expression, evidence, "ambiguous")
                return
            if not isinstance(target, SymbolRecord):
                self._warn(warnings, caller, expression, evidence, "unresolved")
                return
            accumulator.add(
                source_id=caller.id,
                target_id=target.id,
                kind="CALLS",
                resolver="import_from" if bindings.get(expression) == target.qualified_name else "lexical_module",
                confidence="high",
                evidence=evidence,
            )
            return

        if parts[0] == "self":
            self._resolve_self_method(
                index, imports, accumulator, caller, parts[-1], evidence, warnings
            )
            return

        binding_target = bindings.get(parts[0])
        if binding_target is not None:
            self._resolve_bound_call(index, caller, binding_target, parts[1:], evidence, accumulator)
            return

        module = index.module_of(caller)
        class_symbol = index.matches_in_module(module, parts[0])
        if len(class_symbol) == 1 and class_symbol[0].kind == "class" and len(parts) == 2:
            self._resolve_class_method(
                index, caller, class_symbol[0], parts[1], evidence, accumulator, warnings
            )
            return
        if len(class_symbol) > 1:
            self._warn(warnings, caller, expression, evidence, "ambiguous")
            return

        self._resolve_module_qualified_call(index, caller, parts, evidence, accumulator, warnings)

    def _resolve_bound_call(
        self,
        index: _ResolverIndex,
        caller: SymbolRecord,
        binding_target: str,
        rest: list[str],
        evidence: Evidence,
        accumulator: _EdgeAccumulator,
    ) -> None:
        """Call through a bound module: ``alias.attr(...)`` / ``alias(...)``."""
        root_symbol = index.qname_symbol(binding_target)
        if not rest:
            if root_symbol is not None:
                accumulator.add(
                    source_id=caller.id,
                    target_id=root_symbol.id,
                    kind="CALLS",
                    resolver="import_from",
                    confidence="high",
                    evidence=evidence,
                )
            return
        if root_symbol is None:
            return  # bound to something outside the catalogued snapshot
        qualified = f"{root_symbol.qualified_name.split(':', 1)[0]}:{'.'.join(rest)}"
        target = index.qname_symbol(qualified)
        if target is not None:
            accumulator.add(
                source_id=caller.id,
                target_id=target.id,
                kind="CALLS",
                resolver="module_alias",
                confidence="high",
                evidence=evidence,
            )

    def _resolve_self_method(
        self,
        index: _ResolverIndex,
        imports: _ImportMap,
        accumulator: _EdgeAccumulator,
        caller: SymbolRecord,
        attribute: str,
        evidence: Evidence,
        warnings: dict[tuple[str, str, str], dict],
    ) -> None:
        """``self.attr(...)`` → method of the lexical class, else of an ancestor."""
        enclosing_class = index.enclosing_class(caller)
        if enclosing_class is None:
            self._warn(warnings, caller, evidence.expression, evidence, "unresolved")
            return
        candidates = index.children_named(enclosing_class.id, attribute, ("method",))
        if len(candidates) == 1:
            accumulator.add(
                source_id=caller.id,
                target_id=candidates[0].id,
                kind="CALLS",
                resolver="lexical_self_method",
                confidence="high",
                evidence=evidence,
            )
            return
        if len(candidates) > 1:
            self._warn(warnings, caller, evidence.expression, evidence, "ambiguous")
            return
        inherited = self._method_on_ancestor(index, imports, enclosing_class, attribute)
        if isinstance(inherited, SymbolRecord):
            accumulator.add(
                source_id=caller.id,
                target_id=inherited.id,
                kind="CALLS",
                resolver="inherited_method",
                confidence="medium",
                evidence=evidence,
            )
            return
        if inherited is _AMBIGUOUS:
            self._warn(warnings, caller, evidence.expression, evidence, "ambiguous")
            return
        self._warn(warnings, caller, evidence.expression, evidence, "unresolved")

    def _method_on_ancestor(
        self,
        index: _ResolverIndex,
        imports: _ImportMap,
        enclosing: SymbolRecord,
        attribute: str,
    ):
        """Breadth-first walk over resolvable bases; cycle-safe."""
        visited: set[str] = {enclosing.id}
        queue = [enclosing]
        while queue:
            current = queue.pop(0)
            current_bindings = imports.bindings_for(current.file_path, None)
            for base in current.bases:
                base_symbol = self._resolve_name(index, current_bindings, imports, current, base)
                if not isinstance(base_symbol, SymbolRecord) or base_symbol.kind != "class":
                    continue
                if base_symbol.id in visited:
                    continue  # inheritance cycles never loop the walk
                visited.add(base_symbol.id)
                candidates = index.children_named(base_symbol.id, attribute, ("method",))
                if len(candidates) == 1:
                    return candidates[0]
                if len(candidates) > 1:
                    return _AMBIGUOUS
                queue.append(base_symbol)
        return None

    def _resolve_class_method(
        self,
        index: _ResolverIndex,
        caller: SymbolRecord,
        class_symbol: SymbolRecord,
        attribute: str,
        evidence: Evidence,
        accumulator: _EdgeAccumulator,
        warnings: dict[tuple[str, str, str], dict],
    ) -> None:
        candidates = index.children_named(class_symbol.id, attribute, ("method", "function"))
        if len(candidates) == 1:
            accumulator.add(
                source_id=caller.id,
                target_id=candidates[0].id,
                kind="CALLS",
                resolver="class_method",
                confidence="medium",
                evidence=evidence,
            )
            return
        kind = "ambiguous" if len(candidates) > 1 else "unresolved"
        self._warn(warnings, caller, evidence.expression, evidence, kind)

    def _resolve_module_qualified_call(
        self,
        index: _ResolverIndex,
        caller: SymbolRecord,
        parts: list[str],
        evidence: Evidence,
        accumulator: _EdgeAccumulator,
        warnings: dict[tuple[str, str, str], dict],
    ) -> None:
        """``module.attr(...)`` (any depth) against absolute snapshot modules."""
        for split in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:split])
            attribute = ".".join(parts[split:])
            target = index.qname_symbol(f"{module_path}:{attribute}")
            if target is not None:
                accumulator.add(
                    source_id=caller.id,
                    target_id=target.id,
                    kind="CALLS",
                    resolver="module_qualified",
                    confidence="high",
                    evidence=evidence,
                )
                return
        self._warn(warnings, caller, evidence.expression, evidence, "unresolved")

    # ------------------------------------------------------------- name utils
    def _resolve_name(
        self,
        index: _ResolverIndex,
        bindings: dict[str, str],
        imports: _ImportMap,
        caller: SymbolRecord,
        name: str,
    ):
        """Bare name → bound import target, else unique name in the module.

        Returns a SymbolRecord, None (unresolved), or the _AMBIGUOUS sentinel.
        """
        if "." in name or not name:
            return None
        binding_target = bindings.get(name)
        if binding_target is not None:
            symbol = index.qname_symbol(binding_target)
            if symbol is None and binding_target in index.ambiguous_qnames:
                return _AMBIGUOUS
            return symbol  # None = bound outside the catalogued snapshot
        matches = index.matches_in_module(index.module_of(caller), name)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return _AMBIGUOUS
        return None

    def _warn(
        self,
        warnings: dict[tuple[str, str, str], dict],
        caller: SymbolRecord,
        expression: str,
        evidence: Evidence,
        kind: str,
    ) -> None:
        key = (caller.file_path, expression, kind)
        entry = warnings.get(key)
        if entry is None:
            warnings[key] = {
                "kind": kind,
                "line": evidence.line,
                "column": evidence.column,
                "count": 1,
            }
        else:
            entry["count"] += 1

    # ------------------------------------------------------------- diagnostics
    def _collect_reference_diagnostics(
        self,
        warnings: dict[tuple[str, str, str], dict],
        result: ResolutionResult,
        max_reference_diagnostics: int,
    ) -> None:
        """One diagnostic row per (file, expression, kind); counters stay exact."""
        truncated = False
        for (file_path, expression, kind) in sorted(warnings):
            entry = warnings[(file_path, expression, kind)]
            count = entry["count"]
            if kind == "unresolved":
                result.unresolved_count += count
            else:
                result.ambiguous_count += count
            if len(result.diagnostics) >= max_reference_diagnostics:
                truncated = True
                continue
            plural = "s" if count != 1 else ""
            if kind == "unresolved":
                code, message = (
                    "UNRESOLVED_REFERENCE",
                    f"Call target '{expression}' could not be resolved to a symbol"
                    f" ({count} occurrence{plural}).",
                )
            else:
                code, message = (
                    "AMBIGUOUS_REFERENCE",
                    f"Call target '{expression}' matches multiple symbols and was left"
                    f" unresolved ({count} occurrence{plural}).",
                )
            result.diagnostics.append(
                ResolverDiagnostic(
                    code=code,
                    message=message,
                    severity="warning",
                    file_path=file_path,
                    line=entry["line"],
                    column=entry["column"],
                )
            )
        if truncated:
            result.diagnostics.append(
                ResolverDiagnostic(
                    code="UNRESOLVED_LIMIT_REACHED",
                    message=(
                        "More unresolved or ambiguous references exist than the per-analysis"
                        " diagnostic limit; summary counters remain exact but individual"
                        " diagnostic rows were truncated."
                    ),
                    severity="warning",
                    file_path=None,
                    line=None,
                    column=None,
                )
            )
