"""Vanilla JS — ES module imports + DOM addEventListener (regex)."""

from __future__ import annotations

import re
from dataclasses import dataclass


IMPORT_RE = re.compile(
    r"""import\s+(?:(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?['"](?P<path>[^'"]+)['"]"""
)
REQUIRE_RE = re.compile(r"""require\s*\(\s*['"](?P<path>[^'"]+)['"]\s*\)""")
EXPORT_RE = re.compile(r"""export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>\w+)""")
LISTENER_RE = re.compile(
    r"""(?:(?P<target>\w+)\.)?addEventListener\s*\(\s*['"](?P<event>[^'"]+)['"]\s*,\s*(?P<handler>[\w.]+)"""
)
INNER_HTML_RE = re.compile(r"\.(?:innerHTML|outerHTML)\s*=")
EVAL_RE = re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(")


@dataclass
class JsModuleFacts:
    imports: list[dict]
    exports: list[dict]
    listeners: list[dict]
    sinks: list[dict]


def extract_javascript(text: str) -> JsModuleFacts:
    imports = [{"path": m.group("path"), "line": text[:m.start()].count("\n") + 1, "assumed": m.group("path").startswith(".")} for m in IMPORT_RE.finditer(text)]
    imports += [{"path": m.group("path"), "line": text[:m.start()].count("\n") + 1, "assumed": True, "cjs": True} for m in REQUIRE_RE.finditer(text)]
    exports = [{"name": m.group("name"), "line": text[:m.start()].count("\n") + 1} for m in EXPORT_RE.finditer(text)]
    listeners = [
        {
            "target": m.group("target") or "document",
            "event": m.group("event"),
            "handler": m.group("handler"),
            "line": text[:m.start()].count("\n") + 1,
            "assumed": False,
        }
        for m in LISTENER_RE.finditer(text)
    ]
    sinks = []
    for m in INNER_HTML_RE.finditer(text):
        sinks.append({"kind": "innerHTML", "line": text[:m.start()].count("\n") + 1})
    for m in EVAL_RE.finditer(text):
        sinks.append({"kind": "eval", "line": text[:m.start()].count("\n") + 1})
    return JsModuleFacts(imports=imports, exports=exports, listeners=listeners, sinks=sinks)
