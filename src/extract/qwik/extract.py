"""Qwik extraction — component$ / on* $ boundaries (regex)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..react import extract as ts


COMPONENT_DOLLAR_RE = re.compile(r"\bcomponent\$\s*\(")
HANDLER_DOLLAR_RE = re.compile(r"\b(?P<name>on\w+)\$\s*=")
SIGNAL_RE = re.compile(r"\buseSignal\s*\(")
VISIBLE_TASK_RE = re.compile(r"\buseVisibleTask\$\s*\(")


@dataclass
class QwikFacts:
    mounts: list[dict]
    boundaries: list[dict]
    signals: list[dict]


def extract_qwik(text: str, file_stem: str) -> QwikFacts:
    functions = ts.extract_functions(text)
    mounts_raw, _ = ts.extract_jsx_mounts(text, functions, file_stem)
    mounts = [
        {
            "parent": m.parent,
            "child": m.child,
            "line": m.line,
            "assumed": m.assumed,
            "props": [{"name": p.name, "valueKind": p.value_kind, "valuePreview": p.value_preview, "assumed": p.assumed} for p in m.props],
        }
        for m in mounts_raw
    ]
    boundaries = [{"kind": "component$", "line": text[:m.start()].count("\n") + 1, "assumed": False} for m in COMPONENT_DOLLAR_RE.finditer(text)]
    for m in HANDLER_DOLLAR_RE.finditer(text):
        boundaries.append({"kind": "handler$", "name": m.group("name"), "line": text[:m.start()].count("\n") + 1, "assumed": False})
    for m in VISIBLE_TASK_RE.finditer(text):
        boundaries.append({"kind": "useVisibleTask$", "line": text[:m.start()].count("\n") + 1, "assumed": True})
    signals = [{"kind": "useSignal", "line": text[:m.start()].count("\n") + 1, "assumed": True} for m in SIGNAL_RE.finditer(text)]
    return QwikFacts(mounts=mounts, boundaries=boundaries, signals=signals)
