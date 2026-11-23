"""SolidJS extraction — components + createSignal ownership (regex).

Honesty enrichments (EXTRACTOR_VERSION 22):
- Signal / effect / resource call sites attribute ``owner`` via the shared
  React innermost-enclosing-function helper when the span is clear;
  file-stem fallback is ``assumed`` (never invent an owner).
- JSX mounts still reuse React brace-aware helpers; no Solid-only invent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..react import extract as ts


SIGNAL_RE = re.compile(r"\b(?P<kind>createSignal|createMemo)\s*\(")
EFFECT_RE = re.compile(r"\b(?P<kind>createEffect|createResource)\s*\(")


@dataclass
class SolidFacts:
    mounts: list[dict]
    signals: list[dict]
    effects: list[dict]


def _owned_calls(
    text: str,
    pattern: re.Pattern[str],
    functions: list,
    file_stem: str,
) -> list[dict]:
    out: list[dict] = []
    for m in pattern.finditer(text):
        line = text[: m.start()].count("\n") + 1
        owner, assumed = ts._hook_owner(line, functions, file_stem)
        out.append({
            "kind": m.group("kind"),
            "line": line,
            "owner": owner,
            "assumed": assumed,
        })
    return out


def extract_solid(text: str, file_stem: str) -> SolidFacts:
    functions = ts.extract_functions(text)
    mounts_raw, _ = ts.extract_jsx_mounts(text, functions, file_stem)
    mounts = [
        {
            "parent": m.parent,
            "child": m.child,
            "line": m.line,
            "assumed": m.assumed,
            "props": [
                {
                    "name": p.name,
                    "valueKind": p.value_kind,
                    "valuePreview": p.value_preview,
                    "assumed": p.assumed,
                }
                for p in m.props
            ],
        }
        for m in mounts_raw
    ]
    signals = _owned_calls(text, SIGNAL_RE, functions, file_stem)
    effects = _owned_calls(text, EFFECT_RE, functions, file_stem)
    return SolidFacts(mounts=mounts, signals=signals, effects=effects)
