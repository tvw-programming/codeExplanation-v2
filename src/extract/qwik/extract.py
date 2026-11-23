"""Qwik extraction — component$ / on*$ boundaries (regex).

Honesty enrichments (EXTRACTOR_VERSION 22):
- ``const Name = component$(...)`` / ``export default component$(...)``
  bind names recorded when proven at the declaration site — never invent
  a component from an unbound ``component$`` call.
- Synthetic function spans for proven ``component$`` bodies so shared
  React JSX mount + hook-owner helpers attribute parents/owners locally.
- ``useSignal`` / ``useStore`` / ``useTask$`` ownership uses the same
  innermost-enclosing-function rule; file-stem fallback is ``assumed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..react import extract as ts


COMPONENT_CONST_RE = re.compile(
    r"(?:export\s+)?(?:const|let)\s+(?P<bind>\w+)\s*(?::\s*[^=]+)?=\s*"
    r"component\$\s*\(",
)
COMPONENT_DEFAULT_RE = re.compile(
    r"export\s+default\s+component\$\s*\(",
)
# After component$( … either `function Name(` or `(...) => {`
INNER_FUNC_RE = re.compile(
    r"(?:function\s+(?P<inner>\w+)?\s*\((?P<fparams>[^)]*)\)\s*\{)"
    r"|"
    r"(?:async\s+)?\((?P<aparams>[^)]*)\)\s*(?::\s*[^=]+?)?=>\s*\{",
)
HANDLER_DOLLAR_RE = re.compile(r"\b(?P<name>on\w+)\$\s*=")
SIGNAL_RE = re.compile(r"\b(?P<kind>useSignal|useStore|useComputed\$)\s*\(")
TASK_RE = re.compile(r"\b(?P<kind>useVisibleTask\$|useTask\$|useResource\$)\s*\(")


@dataclass
class QwikFacts:
    mounts: list[dict]
    boundaries: list[dict]
    signals: list[dict]
    effects: list[dict] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _component_dollar_functions(text: str, file_stem: str) -> list[ts.ExtractedFunction]:
    """Proven component$ bind → ExtractedFunction span for mount/hook owners."""
    found: list[ts.ExtractedFunction] = []
    seen_braces: set[int] = set()

    def _try_add(bind: str, call_open_paren: int) -> None:
        # Scan from just after `component$(` for the inner function/arrow body.
        inner = INNER_FUNC_RE.search(text, call_open_paren)
        if inner is None:
            return
        brace_open = inner.end() - 1
        if text[brace_open] != "{" or brace_open in seen_braces:
            return
        end_off = ts._find_matching_brace_end_offset(text, brace_open)
        if end_off is None:
            return
        seen_braces.add(brace_open)
        start_line = _line_of(text, inner.start())
        end_line = _line_of(text, end_off)
        name = bind
        if inner.group("inner"):
            # Prefer explicit inner function name when present.
            name = inner.group("inner") or bind
        params = inner.group("fparams") if inner.group("fparams") is not None else (inner.group("aparams") or "")
        snippet = ts.trim_snippet(text.splitlines(), start_line, end_line)
        found.append(ts.ExtractedFunction(
            name=name,
            signature=f"component$({name})",
            line_range=(start_line, end_line),
            snippet=snippet,
            is_event_handler=False,
            event_type=None,
            wrappers=["component$"],
        ))

    for m in COMPONENT_CONST_RE.finditer(text):
        _try_add(m.group("bind"), m.end() - 1)
    for m in COMPONENT_DEFAULT_RE.finditer(text):
        _try_add(file_stem, m.end() - 1)
    return found


def _merge_functions(
    base: list[ts.ExtractedFunction],
    extra: list[ts.ExtractedFunction],
) -> list[ts.ExtractedFunction]:
    """Prefer component$ spans; drop overlapping plain parses of the same brace."""
    by_span: dict[tuple[int, int], ts.ExtractedFunction] = {
        (f.line_range[0], f.line_range[1]): f for f in base
    }
    for f in extra:
        key = (f.line_range[0], f.line_range[1])
        by_span[key] = f
    return list(by_span.values())


def extract_qwik(text: str, file_stem: str) -> QwikFacts:
    base_fns = ts.extract_functions(text)
    qwik_fns = _component_dollar_functions(text, file_stem)
    functions = _merge_functions(base_fns, qwik_fns)

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

    boundaries: list[dict] = []
    for m in COMPONENT_CONST_RE.finditer(text):
        boundaries.append({
            "kind": "component$",
            "name": m.group("bind"),
            "line": _line_of(text, m.start()),
            "assumed": False,
        })
    for m in COMPONENT_DEFAULT_RE.finditer(text):
        # Default export — bind name is the file stem only when no inner name.
        inner = INNER_FUNC_RE.search(text, m.end() - 1)
        name = file_stem
        if inner and inner.group("inner"):
            name = inner.group("inner")
        boundaries.append({
            "kind": "component$",
            "name": name,
            "line": _line_of(text, m.start()),
            "assumed": False,
        })
    # Unbound component$(...) — record the boundary without inventing a name.
    bound_offsets = {b["line"] for b in boundaries}
    for m in re.finditer(r"\bcomponent\$\s*\(", text):
        line = _line_of(text, m.start())
        if line in bound_offsets:
            continue
        boundaries.append({
            "kind": "component$",
            "line": line,
            "assumed": True,
        })

    for m in HANDLER_DOLLAR_RE.finditer(text):
        boundaries.append({
            "kind": "handler$",
            "name": m.group("name"),
            "line": _line_of(text, m.start()),
            "assumed": False,
        })

    signals: list[dict] = []
    for m in SIGNAL_RE.finditer(text):
        line = _line_of(text, m.start())
        owner, assumed = ts._hook_owner(line, functions, file_stem)
        signals.append({
            "kind": m.group("kind"),
            "line": line,
            "owner": owner,
            "assumed": assumed,
        })

    effects: list[dict] = []
    for m in TASK_RE.finditer(text):
        line = _line_of(text, m.start())
        owner, assumed = ts._hook_owner(line, functions, file_stem)
        effects.append({
            "kind": m.group("kind"),
            "line": line,
            "owner": owner,
            "assumed": assumed,
        })
        boundaries.append({
            "kind": m.group("kind"),
            "line": line,
            "owner": owner,
            "assumed": assumed,
        })

    return QwikFacts(
        mounts=mounts,
        boundaries=boundaries,
        signals=signals,
        effects=effects,
    )
