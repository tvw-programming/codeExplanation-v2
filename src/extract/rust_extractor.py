"""Rust crate/module + Axum/Actix/Rocket route heuristics (regex).

Trait Impl unresolved → assumed. Macros may hide routes → partial.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(?P<name>\w+)\s*;", re.MULTILINE)
USE_RE = re.compile(r"^\s*(?:pub\s+)?use\s+(?P<path>[\w:]+)(?:\s+as\s+\w+)?\s*;", re.MULTILINE)
FN_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*\(", re.MULTILINE)
AXUM_ROUTE_RE = re.compile(
    r"""\.(?P<method>route|get|post|put|delete|patch)\s*\(\s*["'](?P<path>[^"']+)["']"""
)
ACTIX_RE = re.compile(r"#\[(?:get|post|put|delete|patch)\s*\(\s*\"(?P<path>[^\"]+)\"\s*\)\s*\]")
ROCKET_RE = re.compile(r"#\[(?:get|post|put|delete|patch)\s*\(\s*\"(?P<path>[^\"]+)\"")
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
    routes = []
    for m in AXUM_ROUTE_RE.finditer(text):
        method = m.group("method").upper()
        if method == "ROUTE":
            method = "GET"
        routes.append({
            "method": method,
            "path": m.group("path"),
            "line": text[:m.start()].count("\n") + 1,
            "assumed": True,
            "framework": "axum",
        })
    for m in ACTIX_RE.finditer(text):
        routes.append({
            "method": "GET",
            "path": m.group("path"),
            "line": text[:m.start()].count("\n") + 1,
            "assumed": True,
            "framework": "actix",
        })
    for m in ROCKET_RE.finditer(text):
        routes.append({
            "method": "GET",
            "path": m.group("path"),
            "line": text[:m.start()].count("\n") + 1,
            "assumed": True,
            "framework": "rocket",
        })
    unsafe_blocks = [{"line": text[:m.start()].count("\n") + 1} for m in UNSAFE_RE.finditer(text)]
    return RustFacts(modules=modules, uses=uses, functions=functions, routes=routes, unsafe_blocks=unsafe_blocks)
