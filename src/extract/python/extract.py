"""Python extraction via stdlib ast — zero third-party deps.

Honesty: only facts the AST can prove. Route prefixes from other files
stay assumed. In-file APIRouter(prefix=...) literals are composed.
Docstrings via ast.get_docstring (not upward // scan).
"""

from __future__ import annotations

import ast
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


def _attr_chain(node: ast.AST) -> list[str]:
    names: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        names.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        names.append(cur.id)
    return list(reversed(names))


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Map local names bound to APIRouter(prefix='...') literals in this file."""
    prefixes: dict[str, str] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        names = _attr_chain(node.value.func)
        if not names or names[-1] != "APIRouter":
            continue
        prefix = None
        for kw in node.value.keywords:
            if kw.arg == "prefix":
                prefix = _const_str(kw.value)
        if prefix is None:
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                prefixes[t.id] = prefix
    return prefixes


def _compose_path(prefix: str | None, path: str) -> str:
    if not prefix:
        return path or "/"
    if not path or path == "/":
        return prefix if prefix.startswith("/") else "/" + prefix
    left = prefix.rstrip("/")
    right = path if path.startswith("/") else "/" + path
    full = left + right
    return full if full.startswith("/") else "/" + full


def _flask_methods(call: ast.Call) -> list[str] | None:
    """Return explicit Flask methods= list, or None if not present."""
    for kw in call.keywords:
        if kw.arg != "methods":
            continue
        if isinstance(kw.value, (ast.List, ast.Tuple)):
            out: list[str] = []
            for elt in kw.value.elts:
                s = _const_str(elt)
                if s:
                    out.append(s.upper())
            return out or None
    return None


def _decorator_routes(
    node: ast.AST,
    router_prefixes: dict[str, str],
) -> list[tuple[str, str, bool]]:
    """Return list of (METHOD, path, assumed) from FastAPI/Flask-style decorators."""
    results: list[tuple[str, str, bool]] = []
    for d in getattr(node, "decorator_list", []) or []:
        if not isinstance(d, ast.Call):
            continue
        names = _attr_chain(d.func)
        if not names:
            continue
        joined = ".".join(names).lower()
        router_var = names[0] if len(names) >= 2 else None
        method = None
        for m in ("get", "post", "put", "delete", "patch", "options", "head"):
            if names[-1].lower() == m:
                method = m.upper()
                break
            if f".{m}" in f".{joined}":
                method = m.upper()
                break
        flask_methods = None
        if method is None and "route" in joined:
            flask_methods = _flask_methods(d)
            method = "GET"  # Flask default when methods omitted
        if method is None:
            continue
        path = "/"
        assumed = True
        if d.args:
            lit = _const_str(d.args[0])
            if lit is not None:
                path = lit
                assumed = False
        prefix = router_prefixes.get(router_var) if router_var else None
        if prefix:
            path = _compose_path(prefix, path)
            # Prefix was a literal in this file — still mark assumed False for path text.
            assumed = assumed  # stays False if path was literal
        methods = flask_methods if flask_methods else [method]
        for mth in methods:
            results.append((mth, path, assumed))
    return results


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

    router_prefixes = _router_prefixes(tree)

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
        route_specs = _decorator_routes(node, router_prefixes)
        doc = ast.get_docstring(node, clean=True)
        first = route_specs[0] if route_specs else None
        fn = PyFunction(
            name=node.name,
            line_range=(start, end),
            docstring=doc,
            decorators=_decorator_names(node),
            calls=_calls_in(node),
            is_route=bool(route_specs),
            route_method=first[0] if first else None,
            route_path=first[1] if first else None,
            visibility=_visibility(node.name, all_names),
        )
        functions.append(fn)
        deps = _depends_in(node)
        for method, path, assumed in route_specs:
            routes.append(PyRoute(
                method=method,
                path=path,
                handler=node.name,
                line=start,
                assumed=assumed,
                depends=list(deps),
            ))

    return functions, routes, imports, sorted(all_names or [])
