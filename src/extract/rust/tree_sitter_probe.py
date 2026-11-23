"""Optional Rust tree-sitter probe (probe-only — not record-authoritative).

When ``CEV_TREE_SITTER=1`` and ``tree-sitter`` + ``tree-sitter-rust`` are
installed, this module parses Rust and lists **proven** fn / struct /
trait / impl / enum names from clean nodes.

Record assembly stays on the regex + PrefixGraph path. Query-backed nest
/ route spans are deferred until parity tests prove no invent risk on
macros and unresolved trait Impl (see feasibility matrix).

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Nodes with ``has_error`` are skipped.
- Never invents ``.nest`` joins, route edges, or trait Impl satisfaction.
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

_RUST_DECL_QUERY = """
(function_item
  name: (identifier) @name) @decl

(function_signature_item
  name: (identifier) @name) @decl

(struct_item
  name: (type_identifier) @name) @decl

(enum_item
  name: (type_identifier) @name) @decl

(trait_item
  name: (type_identifier) @name) @decl

(impl_item
  type: (type_identifier) @name) @decl

(impl_item
  (type_identifier) @name) @decl
"""


@dataclass(frozen=True)
class RustDeclSpan:
    """A declaration proven by a clean tree-sitter node."""

    kind: str  # function | struct | enum | trait | impl
    name: str
    line_range: tuple[int, int]


def probe_rust_parse(text: str) -> ParsedFile | None:
    """Parse Rust when the flag is on and the substrate is available."""
    if not tree_sitter_enabled():
        return None
    parsed = try_parse(text, "rust")
    if parsed is None:
        return None
    if catastrophic_parse(parsed):
        return None
    return parsed


def probe_rust_declarations(text: str) -> list[RustDeclSpan] | None:
    """List clean decls, or None to fall back.

    Empty list = clean parse with no matches (not a fallback).
    """
    parsed = probe_rust_parse(text)
    if parsed is None:
        return None

    out: list[RustDeclSpan] = []
    seen: set[tuple[str, str, tuple[int, int]]] = set()
    for _pattern_idx, capture_map in matches(parsed, _RUST_DECL_QUERY):
        names = capture_map.get("name") or []
        decls = capture_map.get("decl") or []
        if not names or not decls:
            continue
        name_node = names[0]
        decl_node = decls[0]
        if not is_sound(decl_node) or not is_sound(name_node):
            continue
        name = name_node.text.decode("utf-8", errors="replace")
        kind = _kind_for(decl_node.type)
        span = line_range(decl_node)
        key = (kind, name, span)
        if key in seen:
            continue
        seen.add(key)
        out.append(RustDeclSpan(kind=kind, name=name, line_range=span))
    return out


def _kind_for(node_type: str) -> str:
    if node_type in ("function_item", "function_signature_item"):
        return "function"
    if node_type == "struct_item":
        return "struct"
    if node_type == "enum_item":
        return "enum"
    if node_type == "trait_item":
        return "trait"
    if node_type == "impl_item":
        return "impl"
    return "decl"
