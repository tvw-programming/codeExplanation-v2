"""Optional Express / JavaScript tree-sitter probe (probe-only).

When ``CEV_TREE_SITTER=1`` and ``tree-sitter`` + ``tree-sitter-javascript``
are installed, this module parses JS and lists **proven** function /
const-fn / method names from clean nodes.

Record assembly stays on the regex + PrefixGraph path. Call-tree
middleware arity / ``.use`` classification is deferred until parity tests
prove no invent risk (see feasibility matrix).

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Nodes with ``has_error`` are skipped.
- Never invents mounts, route edges, or middleware attachments.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.parse.tree_sitter_support import (
    ParsedFile,
    catastrophic_parse,
    is_sound,
    line_range,
    matches,
    tree_sitter_enabled,
    try_parse,
)

_JS_DECL_QUERY = """
(function_declaration
  name: (identifier) @name) @decl

(class_declaration
  name: (identifier) @name) @decl

(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)])) @decl

(method_definition
  name: [(property_identifier) (private_property_identifier)] @name) @decl
"""


@dataclass(frozen=True)
class JsDeclSpan:
    """A declaration proven by a clean tree-sitter node."""

    kind: str  # function | class | const_fn | method
    name: str
    line_range: tuple[int, int]


def probe_js_parse(text: str) -> ParsedFile | None:
    """Parse JavaScript when the flag is on and the substrate is available."""
    if not tree_sitter_enabled():
        return None
    parsed = try_parse(text, "javascript")
    if parsed is None:
        return None
    if catastrophic_parse(parsed):
        return None
    return parsed


def probe_js_declarations(text: str) -> list[JsDeclSpan] | None:
    """List clean decls, or None to fall back.

    Empty list = clean parse with no matches (not a fallback).
    """
    parsed = probe_js_parse(text)
    if parsed is None:
        return None

    out: list[JsDeclSpan] = []
    for _pattern_idx, capture_map in matches(parsed, _JS_DECL_QUERY):
        names = capture_map.get("name") or []
        decls = capture_map.get("decl") or []
        if not names or not decls:
            continue
        name_node = names[0]
        decl_node = decls[0]
        if not is_sound(decl_node) or not is_sound(name_node):
            continue
        name = name_node.text.decode("utf-8", errors="replace")
        out.append(
            JsDeclSpan(
                kind=_kind_for(decl_node.type),
                name=name,
                line_range=line_range(decl_node),
            )
        )
    return out


def _kind_for(node_type: str) -> str:
    if node_type == "function_declaration":
        return "function"
    if node_type == "class_declaration":
        return "class"
    if node_type == "lexical_declaration":
        return "const_fn"
    if node_type == "method_definition":
        return "method"
    return "decl"
