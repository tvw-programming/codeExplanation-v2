"""Optional TSX/TypeScript tree-sitter probe.

When ``CEV_TREE_SITTER=1`` and ``tree-sitter`` + ``tree-sitter-typescript``
are installed, this module parses TSX (or TS) and lists **proven**
declaration names from clean nodes.

``extract_functions`` overlays matching line ranges (version 24). It does
**not** invent JSX mounts, dynamic ``:is``/tag edges, or hook owners.

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Nodes with ``has_error`` are skipped (no guessed names from ERROR trees).
- Name mismatch with regex → extract keeps the full regex path.
- Never emits mounts or edges — names + line ranges only.
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

# Grouped query so name + declaration node stay paired.
# Covers function/class/interface/type + const arrow/fn bindings + methods.
# Does **not** query JSX element tags (mount invent risk).
_TSX_DECL_QUERY = """
(function_declaration
  name: (identifier) @name) @decl

(class_declaration
  name: (type_identifier) @name) @decl

(interface_declaration
  name: (type_identifier) @name) @decl

(type_alias_declaration
  name: (type_identifier) @name) @decl

(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)])) @decl

(method_definition
  name: [(property_identifier) (private_property_identifier)] @name) @decl
"""


@dataclass(frozen=True)
class TsxDeclSpan:
    """A declaration proven by a clean tree-sitter node."""

    kind: str  # function | class | interface | type | const_fn | method
    name: str
    line_range: tuple[int, int]


def probe_tsx_parse(text: str, *, language_key: str = "tsx") -> ParsedFile | None:
    """Parse TSX/TS when the flag is on and the substrate is available.

    Returns None → caller must keep the regex path unchanged.
    ``language_key`` is ``tsx`` (default) or ``typescript``.
    """
    if not tree_sitter_enabled():
        return None
    if language_key not in {"tsx", "typescript"}:
        return None
    parsed = try_parse(text, language_key)
    if parsed is None:
        return None
    if catastrophic_parse(parsed):
        return None
    return parsed


def probe_tsx_declarations(
    text: str,
    *,
    language_key: str = "tsx",
) -> list[TsxDeclSpan] | None:
    """List clean declarations, or None to fall back.

    Empty list means a clean parse with no matching decls — not a fallback.
    Only ``None`` means fall back.
    """
    parsed = probe_tsx_parse(text, language_key=language_key)
    if parsed is None:
        return None

    out: list[TsxDeclSpan] = []
    for _pattern_idx, capture_map in matches(parsed, _TSX_DECL_QUERY):
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
            TsxDeclSpan(
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
    if node_type == "interface_declaration":
        return "interface"
    if node_type == "type_alias_declaration":
        return "type"
    if node_type == "lexical_declaration":
        return "const_fn"
    if node_type == "method_definition":
        return "method"
    return "decl"
