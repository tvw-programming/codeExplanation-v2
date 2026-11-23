"""Vue SFC extractor — script + template tags (regex).

Honesty enrichments (EXTRACTOR_VERSION 22):
- Template child lines map to full-file offsets (not template-local).
- PascalCase mounts skip / mark assumed when ``:is`` / ``v-bind:is`` present.
- Simple literal / bound props on child tags when evidenced in attributes.
- ``ref`` / ``computed`` / ``reactive`` / ``watch*`` / ``onMounted`` etc.
  attributed to the SFC stem under ``<script setup>`` (unambiguous owner);
  otherwise file-stem fallback is ``assumed``. Prefer skip over invent —
  dynamic ``<component :is>`` and unmatched kebab tags are not mounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


SFC_SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
SFC_TEMPLATE_RE = re.compile(r"<template(?P<attrs>[^>]*)>(?P<body>.*?)</template>", re.DOTALL | re.IGNORECASE)
# Opening PascalCase tag with attribute blob up to `>` / `/>`.
COMPONENT_TAG_RE = re.compile(
    r"<(?P<name>[A-Z][\w]*)(?P<attrs>(?:\s[^>]*)?)(/?)\s*>",
)
PROPS_RE = re.compile(r"defineProps\s*(?:<[^>]+>)?\s*\(|props\s*:")
EMIT_RE = re.compile(r"defineEmits\s*\(|emits\s*:")
V_ON_RE = re.compile(r"""(?:v-on:|@)(?P<event>[\w.-]+)\s*=\s*['"](?P<handler>[\w]+)""")
V_HTML_RE = re.compile(r"\bv-html\b")
DYNAMIC_IS_RE = re.compile(r"""(?::is|v-bind:is)\s*=""")

# Composition API call sites — owner is unambiguous under script setup.
SIGNAL_CALL_RE = re.compile(
    r"\b(?P<kind>ref|reactive|computed|shallowRef|shallowReactive)\s*\("
)
WATCH_CALL_RE = re.compile(r"\b(?P<kind>watchEffect|watchPostEffect|watchSyncEffect|watch)\s*\(")
LIFECYCLE_CALL_RE = re.compile(
    r"\b(?P<kind>onBeforeMount|onMounted|onBeforeUpdate|onUpdated|"
    r"onBeforeUnmount|onUnmounted|onActivated|onDeactivated|onErrorCaptured)\s*\("
)

# Attr bindings: name="…" / name='…' / :name="…" / v-bind:name="…"
ATTR_BIND_RE = re.compile(
    r"""(?:(?P<bound>:|v-bind:)(?P<bname>[\w.-]+)|(?P<lname>[\w.-]+))\s*=\s*
        (?:
          "(?P<dstr>[^"]*)"
          |
          '(?P<sstr>[^']*)'
        )
    """,
    re.VERBOSE,
)

BUILTIN_TAGS = frozenset({
    "template", "script", "style", "KeepAlive", "Teleport", "Suspense",
    "Transition", "TransitionGroup", "RouterView", "RouterLink",
})


@dataclass
class VueSfc:
    components: list[dict]
    has_props: bool
    has_emits: bool
    events: list[dict]
    has_v_html: bool
    script_setup: bool
    signals: list[dict] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _parse_child_props(attrs: str) -> list[dict]:
    """Literal / bound props only — skip event listeners and dynamic ``:is``."""
    props: list[dict] = []
    if not attrs or not attrs.strip():
        return props
    seen: set[str] = set()
    for m in ATTR_BIND_RE.finditer(attrs):
        if m.group("bound"):
            name = m.group("bname") or ""
            if name in ("is", "key"):
                continue
            preview = m.group("dstr") if m.group("dstr") is not None else m.group("sstr")
            kind = "expression"
            assumed = False
        else:
            name = m.group("lname") or ""
            if name.startswith("v-") or name.startswith("on") or name in ("is", "key", "ref"):
                continue
            preview = m.group("dstr") if m.group("dstr") is not None else m.group("sstr")
            kind = "literal"
            assumed = False
        if not name or name in seen:
            continue
        seen.add(name)
        props.append({
            "name": name,
            "valueKind": kind,
            "valuePreview": (preview[:80] if preview is not None else None),
            "assumed": assumed,
        })
    return props


def _script_call_facts(
    text: str,
    *,
    script_setup: bool,
    file_stem: str,
) -> tuple[list[dict], list[dict]]:
    """Attribute Composition API calls. Prefer skip when owner is unclear."""
    signals: list[dict] = []
    effects: list[dict] = []
    # Only scan script bodies — template text must not invent signal sites.
    script_spans: list[tuple[int, int]] = []
    for m in SFC_SCRIPT_RE.finditer(text):
        body = m.group("body") or ""
        # Body starts after the opening tag.
        start = m.start("body")
        script_spans.append((start, start + len(body)))

    def _in_script(offset: int) -> bool:
        return any(a <= offset < b for a, b in script_spans)

    owner = file_stem
    # Under <script setup> the SFC itself is the clear owner.
    assumed = not script_setup

    for m in SIGNAL_CALL_RE.finditer(text):
        if not _in_script(m.start()):
            continue
        signals.append({
            "kind": m.group("kind"),
            "line": _line_of(text, m.start()),
            "owner": owner,
            "assumed": assumed,
        })
    for m in WATCH_CALL_RE.finditer(text):
        if not _in_script(m.start()):
            continue
        effects.append({
            "kind": m.group("kind"),
            "line": _line_of(text, m.start()),
            "owner": owner,
            "assumed": assumed,
        })
    for m in LIFECYCLE_CALL_RE.finditer(text):
        if not _in_script(m.start()):
            continue
        effects.append({
            "kind": m.group("kind"),
            "line": _line_of(text, m.start()),
            "owner": owner,
            "assumed": assumed,
        })
    return signals, effects


def extract_vue_sfc(text: str, file_stem: str = "Component") -> VueSfc:
    script_setup = False
    for m in SFC_SCRIPT_RE.finditer(text):
        if "setup" in (m.group("attrs") or ""):
            script_setup = True

    components: list[dict] = []
    events: list[dict] = []
    has_v_html = False
    seen_mounts: set[tuple[str, int]] = set()

    for tmpl_m in SFC_TEMPLATE_RE.finditer(text):
        tmpl = tmpl_m.group("body") or ""
        tmpl_base = tmpl_m.start("body")
        if V_HTML_RE.search(tmpl):
            has_v_html = True
        for m in COMPONENT_TAG_RE.finditer(tmpl):
            name = m.group("name")
            if name in BUILTIN_TAGS:
                continue
            attrs = m.group("attrs") or ""
            # Dynamic component identity — do not invent a stable child edge.
            if DYNAMIC_IS_RE.search(attrs) or name == "Component":
                continue
            file_offset = tmpl_base + m.start()
            line = _line_of(text, file_offset)
            key = (name, line)
            if key in seen_mounts:
                continue
            seen_mounts.add(key)
            components.append({
                "child": name,
                "assumed": False,
                "line": line,
                "props": _parse_child_props(attrs),
            })
        for e in V_ON_RE.finditer(tmpl):
            events.append({
                "event": e.group("event"),
                "handler": e.group("handler"),
                "assumed": False,
                "line": _line_of(text, tmpl_base + e.start()),
            })

    signals, effects = _script_call_facts(text, script_setup=script_setup, file_stem=file_stem)
    return VueSfc(
        components=components,
        has_props=bool(PROPS_RE.search(text)),
        has_emits=bool(EMIT_RE.search(text)),
        events=events,
        has_v_html=has_v_html,
        script_setup=script_setup,
        signals=signals,
        effects=effects,
    )
