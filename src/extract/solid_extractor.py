"""SolidJS extraction — components + createSignal ownership (regex)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import ts_extractor as ts


SIGNAL_RE = re.compile(r"\bcreateSignal\s*\(")
MEMO_RE = re.compile(r"\bcreateMemo\s*\(")
EFFECT_RE = re.compile(r"\bcreateEffect\s*\(")
RESOURCE_RE = re.compile(r"\bcreateResource\s*\(")


@dataclass
class SolidFacts:
    mounts: list[dict]
    signals: list[dict]
    effects: list[dict]


def extract_solid(text: str, file_stem: str) -> SolidFacts:
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
    signals = [{"kind": "createSignal", "line": text[:m.start()].count("\n") + 1, "assumed": True} for m in SIGNAL_RE.finditer(text)]
    signals += [{"kind": "createMemo", "line": text[:m.start()].count("\n") + 1, "assumed": True} for m in MEMO_RE.finditer(text)]
    effects = [{"kind": "createEffect", "line": text[:m.start()].count("\n") + 1, "assumed": True} for m in EFFECT_RE.finditer(text)]
    effects += [{"kind": "createResource", "line": text[:m.start()].count("\n") + 1, "assumed": True} for m in RESOURCE_RE.finditer(text)]
    return SolidFacts(mounts=mounts, signals=signals, effects=effects)
