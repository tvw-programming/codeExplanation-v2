"""Shared tree-sitter substrate (spike).

Owns grammar loading, query execution, byte/point → 1-indexed line
mapping, and the rule that a syntax error in one file never fails a
run. Extraction *policy* (what edges to emit) stays in
``src/extract/<stack>/``.

Honesty contract
----------------
- Missing / mispinned runtime → ``ParserUnavailable`` (callers fall back).
- Bad source → still returns a ``ParsedFile`` (tree-sitter recovers);
  callers must call ``is_sound`` before reporting facts about a node.
- Never invents edges. Partial trees omit damaged regions; they do not
  guess.

Feature flag: ``CEV_TREE_SITTER=1`` (see ``tree_sitter_enabled``).
Until a stack wires query-backed facts and bumps ``EXTRACTOR_VERSION``,
flag-on only enables probes / experiments — record semantics stay on
the regex/ast path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from src.extract.common import CodeSnippet, trim_snippet

# Env gate for optional substrate experiments. Default off so production
# extract paths are unchanged until a stack opts in + version-bumps.
_ENV_FLAG = "CEV_TREE_SITTER"


class ParserUnavailable(RuntimeError):
    """The substrate is missing or mispinned. Callers degrade to regex/ast."""


# language key -> (pypi module name, loader attribute on that module)
# tree-sitter-typescript: ONE package, TWO grammars (TS vs TSX dialects).
GRAMMARS: dict[str, tuple[str, str]] = {
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "go": ("tree_sitter_go", "language"),
    "java": ("tree_sitter_java", "language"),
    "python": ("tree_sitter_python", "language"),
}

EXTENSION_TO_LANGUAGE = {
    ".java": "java",
    ".js": "javascript",
    ".jsx": "tsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".py": "python",
}


def tree_sitter_enabled() -> bool:
    """True when ``CEV_TREE_SITTER`` is a truthy value (1/true/yes/on)."""
    raw = os.environ.get(_ENV_FLAG, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@lru_cache(maxsize=None)
def _runtime():
    try:
        import tree_sitter
    except ImportError as exc:
        raise ParserUnavailable(
            "tree_sitter is not installed; add 'tree-sitter>=0.25,<0.27' "
            "to requirements (see docs/tree-sitter-substrate-spike.md)"
        ) from exc
    if not hasattr(tree_sitter, "QueryCursor"):
        raise ParserUnavailable(
            "tree_sitter is installed but has no QueryCursor; this wrapper "
            "targets the >=0.25 query API (Query.captures() was removed). "
            "Pin 'tree-sitter>=0.25,<0.27'."
        )
    return tree_sitter


@lru_cache(maxsize=None)
def load_language(key: str):
    """Grammar objects are immutable; cached per process."""
    ts = _runtime()
    try:
        module_name, attr = GRAMMARS[key]
    except KeyError as exc:
        raise ParserUnavailable(f"no tree-sitter grammar registered for {key!r}") from exc
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ParserUnavailable(f"grammar package {module_name!r} is not installed") from e
    return ts.Language(getattr(module, attr)())


@lru_cache(maxsize=None)
def _parser(key: str):
    return _runtime().Parser(load_language(key))


@lru_cache(maxsize=256)
def compile_query(key: str, pattern: str):
    """Compile once per (language, pattern). Invalid patterns are programming
    errors and must fail loudly in tests — never silent empty captures."""
    return _runtime().Query(load_language(key), pattern)


@dataclass
class ParsedFile:
    """One parsed source file for extractor + snippet helpers."""

    language_key: str
    source: bytes
    lines: list[str]
    tree: object
    had_syntax_errors: bool
    error_lines: tuple[int, ...]

    @property
    def root(self):
        return self.tree.root_node


def error_report(node, _acc=None) -> list[int]:
    """1-indexed lines holding an ERROR or MISSING node."""
    acc: list[int] = [] if _acc is None else _acc
    if not node.has_error and not node.is_missing:
        return acc
    if node.type == "ERROR" or node.is_missing:
        acc.append(node.start_point.row + 1)
    for child in node.children:
        error_report(child, acc)
    return acc


def is_sound(node) -> bool:
    """True when this subtree parsed cleanly enough to trust body-derived facts."""
    return not node.has_error


def parse_source(text: str, language_key: str) -> ParsedFile:
    """Never raises for bad source. Raises ``ParserUnavailable`` only when
    the substrate itself is missing."""
    source = text.encode("utf-8")
    tree = _parser(language_key).parse(source)
    errors = tuple(error_report(tree.root_node))
    return ParsedFile(
        language_key=language_key,
        source=source,
        lines=text.splitlines(),
        tree=tree,
        had_syntax_errors=bool(tree.root_node.has_error),
        error_lines=errors,
    )


def try_parse(text: str, language_key: str) -> ParsedFile | None:
    """Parse or return None when the substrate is unavailable.

    Does **not** return None for syntax errors — those yield a ParsedFile
    with ``had_syntax_errors=True``. Callers that want "clean or fallback"
    must check ``had_syntax_errors`` / ``is_sound`` themselves.
    """
    try:
        return parse_source(text, language_key)
    except ParserUnavailable:
        return None


def line_range(node) -> tuple[int, int]:
    """tree-sitter Point.row is 0-indexed; project lineRange is 1-indexed inclusive.

    end_point.column == 0 means the node ends at the start of a line
    (common for a block that closed on the previous line + newline);
    treating that row as the last line would over-report by one.
    """
    start = node.start_point.row + 1
    end_row = node.end_point.row
    if node.end_point.column == 0 and end_row > node.start_point.row:
        end_row -= 1
    return start, end_row + 1


def node_text(parsed: ParsedFile, node) -> str:
    return parsed.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def snippet_for(parsed: ParsedFile, node, *, prefix_nodes=()) -> CodeSnippet:
    """Build a CodeSnippet through ``trim_snippet`` (120-line cap + redact)."""
    start, end = line_range(node)
    for extra in prefix_nodes:
        if extra is not None:
            start = min(start, line_range(extra)[0])
    return trim_snippet(parsed.lines, start, end)


def captures(parsed: ParsedFile, pattern: str, node=None) -> dict[str, list]:
    """Run one query → ``{capture_name: [nodes]}``."""
    query = compile_query(parsed.language_key, pattern)
    cursor = _runtime().QueryCursor(query)
    return dict(cursor.captures(node if node is not None else parsed.root))


def matches(parsed: ParsedFile, pattern: str, node=None) -> list:
    """Grouped matches — use when captures must stay paired (name + args)."""
    query = compile_query(parsed.language_key, pattern)
    return _runtime().QueryCursor(query).matches(node if node is not None else parsed.root)


def catastrophic_parse(parsed: ParsedFile, *, threshold: float = 0.25) -> bool:
    """True when error lines cover more than ``threshold`` of the file.

    Callers should treat such files as unparseable for syntax fidelity and
    fall back (or emit empty) rather than narrating a shred of the tree.
    """
    if not parsed.lines:
        return bool(parsed.had_syntax_errors)
    unique = {ln for ln in parsed.error_lines if 1 <= ln <= len(parsed.lines)}
    return (len(unique) / len(parsed.lines)) > threshold
