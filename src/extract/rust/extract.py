"""Rust crate/module + Axum/Actix/Rocket route heuristics (regex).

Trait Impl unresolved → assumed. Macros may hide routes → partial.
HTTP method taken from get/post helpers or attribute name when present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(?P<name>\w+)\s*;", re.MULTILINE)
USE_RE = re.compile(r"^\s*(?:pub\s+)?use\s+(?P<path>[\w:]+)(?:\s+as\s+\w+)?\s*;", re.MULTILINE)
FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*\(",
    re.MULTILINE,
)
# .get("/path") / .post("/path")
AXUM_METHOD_PATH_RE = re.compile(
    r"""\.(?P<method>get|post|put|delete|patch)\s*\(\s*["'](?P<path>[^"']+)["']"""
)
# .route("/path", get(handler)) / .route("/path", post(handler))
AXUM_ROUTE_RE = re.compile(
    r"""\.route\s*\(\s*["'](?P<path>[^"']+)["']\s*,\s*(?P<method>get|post|put|delete|patch)\s*\("""
)
# Actix / Rocket style attributes
ATTR_ROUTE_RE = re.compile(
    r"#\[(?P<method>get|post|put|delete|patch)\s*\(\s*\"(?P<path>[^\"]+)\"\s*\)\s*\]"
)
UNSAFE_RE = re.compile(r"\bunsafe\s*\{")


@dataclass
class RustFacts:
    modules: list[dict]
    uses: list[dict]
    functions: list[dict]
    routes: list[dict]
    unsafe_blocks: list[dict]


def extract_rust(text: str) -> RustFacts:
    modules = [{"name": m.group("name"), "line": text[:m.start()].count("\n") + 1} for m in MOD_RE.finditer(text)]
    uses = [{"path": m.group("path"), "line": text[:m.start()].count("\n") + 1} for m in USE_RE.finditer(text)]
    functions = [{"name": m.group("name"), "line": text[:m.start()].count("\n") + 1} for m in FN_RE.finditer(text)]

    routes: list[dict] = []
    seen: set[tuple[str, str, int]] = set()

    def _add(method: str, path: str, line: int, framework: str) -> None:
        key = (method.upper(), path, line)
        if key in seen:
            return
        seen.add(key)
        routes.append({
            "method": method.upper(),
            "path": path,
            "line": line,
            "assumed": True,
            "framework": framework,
        })

    for m in AXUM_ROUTE_RE.finditer(text):
        _add(m.group("method"), m.group("path"), text[:m.start()].count("\n") + 1, "axum")
    for m in AXUM_METHOD_PATH_RE.finditer(text):
        _add(m.group("method"), m.group("path"), text[:m.start()].count("\n") + 1, "axum")
    for m in ATTR_ROUTE_RE.finditer(text):
        # Actix and Rocket share attribute syntax; label generically as attr_macro.
        _add(m.group("method"), m.group("path"), text[:m.start()].count("\n") + 1, "attr_macro")

    unsafe_blocks = [{"line": text[:m.start()].count("\n") + 1} for m in UNSAFE_RE.finditer(text)]
    return RustFacts(modules=modules, uses=uses, functions=functions, routes=routes, unsafe_blocks=unsafe_blocks)
