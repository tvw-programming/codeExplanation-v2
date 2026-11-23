"""Vue SFC dual-parse probe (script + template honesty).

When ``CEV_TREE_SITTER=1``:

1. Split ``<script>`` / ``<template>`` with the same SFC boundary regex
   the extractor already trusts (not a full Vue grammar).
2. Parse script with ``javascript`` / ``typescript`` / ``tsx`` based on
   ``lang`` attributes.
3. Parse template body with the ``html`` grammar for tag names only.

Honesty
-------
- Flag off / substrate missing / catastrophic parse → ``None`` (fallback).
- Mount candidates are PascalCase template tags **intersected** with
  script-proven identifiers (imports + top-level decls). Unmatched tags
  are skipped — never invented as mounts.
- Empty script evidence → ``None`` (mismatch) so callers keep the regex
  PascalCase path rather than wiping mounts dishonestly.
- Dynamic ``:is`` / ``<component>`` stay skipped upstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.parse.tree_sitter_support import (
    catastrophic_parse,
    is_sound,
    line_range,
    matches,
    tree_sitter_enabled,
    try_parse,
)

SFC_SCRIPT_RE = re.compile(
    r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
SFC_TEMPLATE_RE = re.compile(
    r"<template(?P<attrs>[^>]*)>(?P<body>.*?)</template>",
    re.DOTALL | re.IGNORECASE,
)
LANG_ATTR_RE = re.compile(r"""\blang\s*=\s*['"](?P<lang>[\w.+-]+)['"]""", re.I)
SETUP_ATTR_RE = re.compile(r"\bsetup\b", re.I)

# Script decls — same family as the TSX probe; no JSX element invent.
# Import aliases (`Foo as Bar`) contribute *both* names so template tags
# using either spelling can resolve without inventing unmatched mounts.
# JS grammar has no `type_identifier`; TS/TSX class names use it.
_SCRIPT_DECL_QUERY_JS = """
(function_declaration
  name: (identifier) @name) @decl

(class_declaration
  name: (identifier) @name) @decl

(lexical_declaration
  (variable_declarator
    name: (identifier) @name)) @decl

(import_specifier
  name: (identifier) @name) @decl

(import_specifier
  alias: (identifier) @name) @decl

(import_clause
  (identifier) @name) @decl
"""

_SCRIPT_DECL_QUERY_TS = """
(function_declaration
  name: (identifier) @name) @decl

(class_declaration
  name: (type_identifier) @name) @decl

(lexical_declaration
  (variable_declarator
    name: (identifier) @name)) @decl

(import_specifier
  name: (identifier) @name) @decl

(import_specifier
  alias: (identifier) @name) @decl

(import_clause
  (identifier) @name) @decl
"""


def _script_decl_query(lang_key: str) -> str:
    return _SCRIPT_DECL_QUERY_JS if lang_key == "javascript" else _SCRIPT_DECL_QUERY_TS

_TEMPLATE_TAG_QUERY = """
(start_tag (tag_name) @name) @tag
(self_closing_tag (tag_name) @name) @tag
"""

BUILTIN_TAGS = frozenset({
    "template", "script", "style", "KeepAlive", "Teleport", "Suspense",
    "Transition", "TransitionGroup", "RouterView", "RouterLink",
    "component", "Component", "slot", "Slot",
})


@dataclass(frozen=True)
class VueScriptDecl:
    name: str
    line_range: tuple[int, int]


@dataclass(frozen=True)
class VueTemplateTag:
    name: str
    line_range: tuple[int, int]  # 1-indexed lines in the *full* SFC text


@dataclass(frozen=True)
class VueDualParseResult:
    script_setup: bool
    script_language: str
    script_decls: list[VueScriptDecl]
    template_tags: list[VueTemplateTag]
    # PascalCase tags proven by script identifiers — safe mount candidates.
    honest_mount_names: frozenset[str]


def _script_language(attrs: str) -> str:
    m = LANG_ATTR_RE.search(attrs or "")
    if not m:
        return "javascript"
    lang = m.group("lang").lower()
    if lang in {"ts", "typescript"}:
        return "typescript"
    if lang in {"tsx"}:
        return "tsx"
    if lang in {"jsx"}:
        return "tsx"
    return "javascript"


def _full_file_line(text: str, body_start: int, local_line: int) -> int:
    """Convert 1-indexed line within a body to 1-indexed full-file line."""
    base = text.count("\n", 0, body_start) + 1
    return base + local_line - 1


def probe_vue_sfc(text: str) -> VueDualParseResult | None:
    """Dual-parse one SFC, or None to fall back to the regex path."""
    if not tree_sitter_enabled():
        return None

    script_m = SFC_SCRIPT_RE.search(text)
    tmpl_m = SFC_TEMPLATE_RE.search(text)
    if script_m is None or tmpl_m is None:
        return None

    script_attrs = script_m.group("attrs") or ""
    script_body = script_m.group("body") or ""
    tmpl_body = tmpl_m.group("body") or ""
    script_setup = bool(SETUP_ATTR_RE.search(script_attrs))
    lang_key = _script_language(script_attrs)

    script_parsed = try_parse(script_body, lang_key)
    if script_parsed is None or catastrophic_parse(script_parsed):
        return None
    tmpl_parsed = try_parse(tmpl_body, "html")
    if tmpl_parsed is None or catastrophic_parse(tmpl_parsed):
        return None

    script_decls: list[VueScriptDecl] = []
    evidence: set[str] = set()
    for _idx, capture_map in matches(script_parsed, _script_decl_query(lang_key)):
        names = capture_map.get("name") or []
        decls = capture_map.get("decl") or []
        if not names:
            continue
        name_node = names[0]
        decl_node = decls[0] if decls else name_node
        if not is_sound(name_node) or not is_sound(decl_node):
            continue
        name = name_node.text.decode("utf-8", errors="replace")
        if not name:
            continue
        evidence.add(name)
        start, end = line_range(decl_node)
        # Rebase to full-file lines for callers that want script spans.
        body_start = script_m.start("body")
        script_decls.append(
            VueScriptDecl(
                name=name,
                line_range=(
                    _full_file_line(text, body_start, start),
                    _full_file_line(text, body_start, end),
                ),
            )
        )

    # Empty evidence → mismatch signal (None) so regex path is kept.
    if not evidence:
        return None

    template_tags: list[VueTemplateTag] = []
    tmpl_base = tmpl_m.start("body")
    for _idx, capture_map in matches(tmpl_parsed, _TEMPLATE_TAG_QUERY):
        names = capture_map.get("name") or []
        tags = capture_map.get("tag") or []
        if not names or not tags:
            continue
        name_node = names[0]
        tag_node = tags[0]
        if not is_sound(name_node) or not is_sound(tag_node):
            continue
        name = name_node.text.decode("utf-8", errors="replace")
        if not name or name in BUILTIN_TAGS:
            continue
        start, end = line_range(tag_node)
        template_tags.append(
            VueTemplateTag(
                name=name,
                line_range=(
                    _full_file_line(text, tmpl_base, start),
                    _full_file_line(text, tmpl_base, end),
                ),
            )
        )

    # PascalCase ∩ script evidence — unmatched tags are not mounts.
    honest = frozenset(
        name for name in evidence
        if name[:1].isupper() and name.isidentifier()
    )
    return VueDualParseResult(
        script_setup=script_setup,
        script_language=lang_key,
        script_decls=script_decls,
        template_tags=template_tags,
        honest_mount_names=honest,
    )


def honest_mount_children(
    text: str,
) -> frozenset[str] | None:
    """Script-proven PascalCase names allowed as mounts, or None to fall back."""
    result = probe_vue_sfc(text)
    if result is None:
        return None
    return result.honest_mount_names
