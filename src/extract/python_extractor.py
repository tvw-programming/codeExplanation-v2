"""Python extraction via stdlib ast — zero third-party deps.

Honesty: only facts the AST can prove. Route prefixes from other files
stay assumed. Docstrings via ast.get_docstring (not upward // scan).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class PyFunction:
    name: str
    line_range: tuple[int, int]
    docstring: str | None
    decorators: list[str]
    calls: list[str]
    is_route: bool = False
    route_method: str | None = None
    route_path: str | None = None
    visibility: str = "public_by_convention"


@dataclass
class PyRoute:
    method: str
    path: str
    handler: str
    line: int
    assumed: bool
    depends: list[str] = field(default_factory=list)


@dataclass
class PyImport:
    module: str
    names: list[str]
    line: int


def _decorator_names(node: ast.AST) -> list[str]:
    out: list[str] = []
    for d in getattr(node, "decorator_list", []) or []:
        if isinstance(d, ast.Name):
            out.append(d.id)
        elif isinstance(d, ast.Attribute):
            parts = []
            cur: ast.AST = d
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            out.append(".".join(reversed(parts)))
        elif isinstance(d, ast.Call):
            if isinstance(d.func, ast.Attribute):
                parts = []
                cur: ast.AST = d.func
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                out.append(".".join(reversed(parts)))
            elif isinstance(d.func, ast.Name):
                out.append(d.func.id)
    return out


def _decorator_route(node: ast.AST) -> tuple[str, str, bool] | None:
    """Return (METHOD, path, assumed) from FastAPI/Flask-style decorators."""
    for d in getattr(node, "decorator_list", []) or []:
        if not isinstance(d, ast.Call):
            continue
        names = []
        cur: ast.AST = d.func
        while isinstance(cur, ast.Attribute):
            names.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            names.append(cur.id)
        names = list(reversed(names))
        joined = ".".join(names).lower()
        method = None
        for m in ("get", "post", "put", "delete", "patch", "options", "head"):
            if names and names[-1].lower() == m:
                method = m.upper()
                break
            if f".{m}" in f".{joined}":
                method = m.upper()
                break
        if method is None and "route" in joined:
            method = "GET"
        if method is None:
            continue
        path = "/"
        assumed = True
        if d.args:
            arg0 = d.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                path = arg0.value
                assumed = False
        return method, path, assumed
    return None


def _calls_in(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                names.append(child.func.attr)
    return names


def _depends_in(node: ast.AST) -> list[str]:
    deps: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "Depends":
            if child.args and isinstance(child.args[0], ast.Name):
                deps.append(child.args[0].id)
            elif child.args and isinstance(child.args[0], ast.Attribute):
                deps.append(child.args[0].attr)
    return deps


def _visibility(name: str, all_names: set[str] | None) -> str:
    if all_names is not None:
        if name in all_names:
            return "declared_in_all"
        if name.startswith("_"):
            return "private_by_underscore"
        return "public_by_convention"
    if name.startswith("_"):
        return "private_by_underscore"
    return "public_by_convention"


def extract_python(text: str) -> tuple[list[PyFunction], list[PyRoute], list[PyImport], list[str]]:
    """Parse source; return functions, routes, imports, module-level __all__ names."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], [], [], []

    all_names: set[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        all_names = {
                            elt.value for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        }

    imports: list[PyImport] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(PyImport(module=alias.name, names=[alias.asname or alias.name], line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append(PyImport(
                module=mod,
                names=[a.asname or a.name for a in node.names],
                line=node.lineno,
            ))

    functions: list[PyFunction] = []
    routes: list[PyRoute] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        if node.decorator_list:
            start = min(d.lineno for d in node.decorator_list if hasattr(d, "lineno"))
        end = getattr(node, "end_lineno", None) or node.lineno
        route = _decorator_route(node)
        doc = ast.get_docstring(node, clean=True)
        fn = PyFunction(
            name=node.name,
            line_range=(start, end),
            docstring=doc,
            decorators=_decorator_names(node),
            calls=_calls_in(node),
            is_route=route is not None,
            route_method=route[0] if route else None,
            route_path=route[1] if route else None,
            visibility=_visibility(node.name, all_names),
        )
        functions.append(fn)
        if route:
            method, path, assumed = route
            routes.append(PyRoute(
                method=method,
                path=path,
                handler=node.name,
                line=start,
                assumed=assumed,
                depends=_depends_in(node),
            ))

    return functions, routes, imports, sorted(all_names or [])
