"""Vanilla JS — ES module imports + DOM addEventListener (regex).

Honesty enrichments (EXTRACTOR_VERSION 22):
- Literal named exports: ``export { a, b as c }``, ``export default Ident``,
  and CJS ``exports.name =`` / ``module.exports = { a, b }`` object keys.
- Literal DOM mount targets from ``getElementById('…')`` /
  ``querySelector('…')`` string literals only — non-literals skipped.
- Dynamic ``import(expr)`` without a string literal is skipped (no invent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


IMPORT_RE = re.compile(
    r"""import\s+(?:(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?['"](?P<path>[^'"]+)['"]"""
)
REQUIRE_RE = re.compile(r"""require\s*\(\s*['"](?P<path>[^'"]+)['"]\s*\)""")
DYNAMIC_IMPORT_LITERAL_RE = re.compile(
    r"""\bimport\s*\(\s*['"](?P<path>[^'"]+)['"]\s*\)"""
)
EXPORT_DECL_RE = re.compile(
    r"""export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>\w+)"""
)
EXPORT_DEFAULT_IDENT_RE = re.compile(
    r"""export\s+default\s+(?P<name>\w+)\s*;"""
)
EXPORT_LIST_RE = re.compile(
    r"""export\s+(?P<default>default\s+)?\{(?P<body>[^}]+)\}"""
)
EXPORTS_ASSIGN_RE = re.compile(
    r"""\bexports\.(?P<name>\w+)\s*="""
)
MODULE_EXPORTS_OBJ_RE = re.compile(
    r"""\bmodule\.exports\s*=\s*\{(?P<body>[^}]*)\}"""
)
LISTENER_RE = re.compile(
    r"""(?:(?P<target>\w+)\.)?addEventListener\s*\(\s*['"](?P<event>[^'"]+)['"]\s*,\s*(?P<handler>[\w.]+)"""
)
DOM_MOUNT_RE = re.compile(
    r"""(?:document\.)?(?P<kind>getElementById|querySelector)\s*\(\s*['"](?P<sel>[^'"]+)['"]\s*\)"""
)
INNER_HTML_RE = re.compile(r"\.(?:innerHTML|outerHTML)\s*=")
EVAL_RE = re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(")


@dataclass
class JsModuleFacts:
    imports: list[dict]
    exports: list[dict]
    listeners: list[dict]
    sinks: list[dict]
    mounts: list[dict] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _export_names_from_list(body: str) -> list[str]:
    """Parse ``a, b as c, default as x`` — identifiers only; skip ``*``."""
    names: list[str] = []
    for part in body.split(","):
        part = part.strip()
        if not part or "*" in part:
            continue
        # `foo as bar` → export binding name is bar (local alias) / foo.
        # Record the exported public name (right of `as`, else the ident).
        m = re.match(r"(?P<local>\w+)(?:\s+as\s+(?P<exported>\w+))?", part)
        if not m:
            continue
        names.append(m.group("exported") or m.group("local"))
    return names


def extract_javascript(text: str) -> JsModuleFacts:
    imports: list[dict] = []
    for m in IMPORT_RE.finditer(text):
        path = m.group("path")
        imports.append({
            "path": path,
            "line": _line_of(text, m.start()),
            # Relative paths are clear local edges; package imports also literal.
            "assumed": False,
        })
    for m in REQUIRE_RE.finditer(text):
        imports.append({
            "path": m.group("path"),
            "line": _line_of(text, m.start()),
            "assumed": False,
            "cjs": True,
        })
    for m in DYNAMIC_IMPORT_LITERAL_RE.finditer(text):
        imports.append({
            "path": m.group("path"),
            "line": _line_of(text, m.start()),
            "assumed": False,
            "dynamic": True,
        })

    exports: list[dict] = []
    seen_exports: set[tuple[str, int]] = set()

    def _add_export(name: str, line: int, *, kind: str = "named") -> None:
        key = (name, line)
        if not name or key in seen_exports:
            return
        seen_exports.add(key)
        exports.append({"name": name, "line": line, "kind": kind, "assumed": False})

    for m in EXPORT_DECL_RE.finditer(text):
        kind = "default" if "export default" in m.group(0) else "named"
        _add_export(m.group("name"), _line_of(text, m.start()), kind=kind)
    for m in EXPORT_DEFAULT_IDENT_RE.finditer(text):
        _add_export(m.group("name"), _line_of(text, m.start()), kind="default")
    for m in EXPORT_LIST_RE.finditer(text):
        line = _line_of(text, m.start())
        for name in _export_names_from_list(m.group("body") or ""):
            kind = "default" if m.group("default") else "named"
            _add_export(name, line, kind=kind)
    for m in EXPORTS_ASSIGN_RE.finditer(text):
        _add_export(m.group("name"), _line_of(text, m.start()), kind="cjs")
    for m in MODULE_EXPORTS_OBJ_RE.finditer(text):
        line = _line_of(text, m.start())
        body = m.group("body") or ""
        for part in body.split(","):
            part = part.strip()
            if not part:
                continue
            # `foo` or `foo: bar` — key is the export name.
            km = re.match(r"(?P<name>\w+)\s*(?::|$)", part)
            if km:
                _add_export(km.group("name"), line, kind="cjs")

    listeners = [
        {
            "target": m.group("target") or "document",
            "event": m.group("event"),
            "handler": m.group("handler"),
            "line": _line_of(text, m.start()),
            "assumed": False,
        }
        for m in LISTENER_RE.finditer(text)
    ]

    mounts: list[dict] = []
    seen_mounts: set[tuple[str, int]] = set()
    for m in DOM_MOUNT_RE.finditer(text):
        sel = m.group("sel")
        line = _line_of(text, m.start())
        key = (sel, line)
        if key in seen_mounts:
            continue
        seen_mounts.add(key)
        mounts.append({
            "kind": m.group("kind"),
            "selector": sel,
            "line": line,
            "assumed": False,
        })

    sinks = []
    for m in INNER_HTML_RE.finditer(text):
        sinks.append({"kind": "innerHTML", "line": _line_of(text, m.start())})
    for m in EVAL_RE.finditer(text):
        sinks.append({"kind": "eval", "line": _line_of(text, m.start())})
    return JsModuleFacts(
        imports=imports,
        exports=exports,
        listeners=listeners,
        sinks=sinks,
        mounts=mounts,
    )
