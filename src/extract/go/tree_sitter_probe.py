"""Optional Go tree-sitter probe (spike — not yet record-authoritative).

When ``CEV_TREE_SITTER=1`` and ``tree-sitter`` + ``tree-sitter-go`` are
installed, this module can parse Go source and list **proven** top-level
function / method / type names from clean nodes.

It does **not** invent Fiber routes, Impl edges, or mounts. Record
assembly in ``extract.py`` / ``record.py`` still uses the regex path.
Query-backed replacement of regex facts requires an ``EXTRACTOR_VERSION``
bump (see store docs/tree-sitter-substrate-spike.md).

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Nodes with ``has_error`` are skipped (no guessed names from ERROR trees).
- Never emits edges — names + line ranges only.
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
_GO_DECL_QUERY = """
(function_declaration
  name: (identifier) @name) @decl

(method_declaration
  name: (field_identifier) @name) @decl

(type_declaration
  (type_spec
    name: (type_identifier) @name
    type: [(struct_type) (interface_type) (type_identifier) (pointer_type)
           (slice_type) (array_type) (map_type) (channel_type)
           (function_type) (generic_type)])) @decl
"""


@dataclass(frozen=True)
class GoDeclSpan:
    """A declaration proven by a clean tree-sitter node."""

    kind: str  # "function" | "method" | "type"
    name: str
    line_range: tuple[int, int]


def probe_go_parse(text: str) -> ParsedFile | None:
    """Parse Go when the flag is on and the substrate is available.

    Returns None → caller must keep the regex/ast path unchanged.
    """
    if not tree_sitter_enabled():
        return None
    parsed = try_parse(text, "go")
    if parsed is None:
        return None
    if catastrophic_parse(parsed):
        return None
    return parsed


def probe_go_declarations(text: str) -> list[GoDeclSpan] | None:
    """List clean function/method/type declarations, or None to fall back.

    Empty list means the file parsed cleanly but had no matching decls —
    that is *not* a fallback signal. Only ``None`` means fall back.
    """
    parsed = probe_go_parse(text)
    if parsed is None:
        return None

    out: list[GoDeclSpan] = []
    for _pattern_idx, capture_map in matches(parsed, _GO_DECL_QUERY):
        # capture_map: dict[str, list[Node]] in QueryCursor.matches API
        names = capture_map.get("name") or []
        decls = capture_map.get("decl") or []
        if not names or not decls:
            continue
        name_node = names[0]
        decl_node = decls[0]
        # Skip damaged declarations entirely — never invent a name/span.
        if not is_sound(decl_node) or not is_sound(name_node):
            continue
        name = name_node.text.decode("utf-8", errors="replace")
        kind = _kind_for(decl_node.type)
        out.append(GoDeclSpan(kind=kind, name=name, line_range=line_range(decl_node)))
    return out


def _kind_for(node_type: str) -> str:
    if node_type == "function_declaration":
        return "function"
    if node_type == "method_declaration":
        return "method"
    return "type"
