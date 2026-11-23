"""Vue SFC extractor — script + template tags (regex). Dynamic :is mounts assumed."""

from __future__ import annotations

import re
from dataclasses import dataclass


SFC_SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
SFC_TEMPLATE_RE = re.compile(r"<template(?P<attrs>[^>]*)>(?P<body>.*?)</template>", re.DOTALL | re.IGNORECASE)
COMPONENT_TAG_RE = re.compile(r"<(?P<name>[A-Z][\w]*)\b")
PROPS_RE = re.compile(r"defineProps\s*(?:<[^>]+>)?\s*\(|props\s*:")
EMIT_RE = re.compile(r"defineEmits\s*\(|emits\s*:")
V_ON_RE = re.compile(r"""(?:v-on:|@)(?P<event>[\w.-]+)\s*=\s*['"](?P<handler>[\w]+)""")
V_HTML_RE = re.compile(r"\bv-html\b")


@dataclass
class VueSfc:
    components: list[dict]
    has_props: bool
    has_emits: bool
    events: list[dict]
    has_v_html: bool
    script_setup: bool


def extract_vue_sfc(text: str) -> VueSfc:
    script_setup = False
    for m in SFC_SCRIPT_RE.finditer(text):
        if "setup" in (m.group("attrs") or ""):
            script_setup = True
    tmpl = ""
    for m in SFC_TEMPLATE_RE.finditer(text):
        tmpl += m.group("body") or ""
    components = []
    for m in COMPONENT_TAG_RE.finditer(tmpl):
        name = m.group("name")
        if name in ("template", "script", "style", "KeepAlive", "Teleport", "Suspense"):
            continue
        components.append({"child": name, "assumed": False, "line": text[:m.start()].count("\n") + 1})
    events = [
        {"event": e.group("event"), "handler": e.group("handler"), "assumed": False}
        for e in V_ON_RE.finditer(tmpl)
    ]
    return VueSfc(
        components=components,
        has_props=bool(PROPS_RE.search(text)),
        has_emits=bool(EMIT_RE.search(text)),
        events=events,
        has_v_html=bool(V_HTML_RE.search(tmpl)),
        script_setup=script_setup,
    )
