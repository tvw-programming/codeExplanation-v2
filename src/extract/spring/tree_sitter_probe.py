"""Optional Java tree-sitter probe for Spring stacks (not record-authoritative).

When ``CEV_TREE_SITTER=1`` and ``tree-sitter`` + ``tree-sitter-java`` are
installed, this module can parse Java and list **proven** type / method /
annotation names from clean nodes.

It does **not** invent ``@Import`` / ``@ComponentScan`` bean edges, typed
``*Impl`` nodes, or DI graphs. Record assembly still uses the regex path
and v23 invent skip-locks. Query-backed facts require ``EXTRACTOR_VERSION``
bump when records change.

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Nodes with ``has_error`` are skipped.
- Annotation *names* may be listed; never treat them as proof of wiring.
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

_JAVA_DECL_QUERY = """
(class_declaration
  name: (identifier) @name) @decl

(interface_declaration
  name: (identifier) @name) @decl

(enum_declaration
  name: (identifier) @name) @decl

(method_declaration
  name: (identifier) @name) @decl

(marker_annotation
  name: (identifier) @ann_name) @ann

(annotation
  name: (identifier) @ann_name) @ann
"""


@dataclass(frozen=True)
class JavaDeclSpan:
    """A declaration or annotation name proven by a clean tree-sitter node."""

    kind: str  # class | interface | enum | method | annotation
    name: str
    line_range: tuple[int, int]


def probe_java_parse(text: str) -> ParsedFile | None:
    """Parse Java when the flag is on and the substrate is available.

    Returns None → caller must keep the regex path unchanged.
    """
    if not tree_sitter_enabled():
        return None
    parsed = try_parse(text, "java")
    if parsed is None:
        return None
    if catastrophic_parse(parsed):
        return None
    return parsed


def probe_java_declarations(text: str) -> list[JavaDeclSpan] | None:
    """List clean type/method/annotation names, or None to fall back.

    Empty list means a clean parse with no matches — not a fallback.
    Only ``None`` means fall back. Annotation names are facts about source
    text only; they must never invent bean / Impl edges.
    """
    parsed = probe_java_parse(text)
    if parsed is None:
        return None

    out: list[JavaDeclSpan] = []
    for _pattern_idx, capture_map in matches(parsed, _JAVA_DECL_QUERY):
        # Type / method decls
        names = capture_map.get("name") or []
        decls = capture_map.get("decl") or []
        if names and decls:
            name_node = names[0]
            decl_node = decls[0]
            if is_sound(decl_node) and is_sound(name_node):
                name = name_node.text.decode("utf-8", errors="replace")
                out.append(
                    JavaDeclSpan(
                        kind=_kind_for(decl_node.type),
                        name=name,
                        line_range=line_range(decl_node),
                    )
                )
            continue

        # Annotations — name only; never imply DI / Import wiring.
        ann_names = capture_map.get("ann_name") or []
        anns = capture_map.get("ann") or []
        if ann_names and anns:
            name_node = ann_names[0]
            ann_node = anns[0]
            if is_sound(ann_node) and is_sound(name_node):
                name = name_node.text.decode("utf-8", errors="replace")
                out.append(
                    JavaDeclSpan(
                        kind="annotation",
                        name=name,
                        line_range=line_range(ann_node),
                    )
                )
    return out


def _kind_for(node_type: str) -> str:
    if node_type == "class_declaration":
        return "class"
    if node_type == "interface_declaration":
        return "interface"
    if node_type == "enum_declaration":
        return "enum"
    if node_type == "method_declaration":
        return "method"
    return "decl"
