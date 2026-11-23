"""Python extraction via stdlib ast — zero third-party deps.

Honesty: only facts the AST can prove. Prefer assumed/skip over inventing
joins. In-file APIRouter(prefix=...) / Blueprint(url_prefix=...) literals
compose. Cross-file include_router / register_blueprint / Django include()
joins only when the target module resolves uniquely via the shared
PrefixGraph; otherwise assumed/skip. In-file register_blueprint /
include_router literal mounts compose. Django method stays UNKNOWN unless
the view/CBV is defined in this file with require_*/api_view or HTTP verb
methods. Docstrings via ast.get_docstring (not upward // scan).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..route_prefix import (
    PrefixGraph,
    chain_as_strings,
    full_route_path,
)

# Django URL dispatcher helpers (django.urls).
_DJANGO_ROUTE_FUNCS = frozenset({"path", "re_path", "url"})

_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".eggs",
})
_MAX_INDEX_FILES = 400
_MAX_INCLUDE_DEPTH = 8

# Django views.decorators.http + DRF api_view shorthand.
_DJANGO_REQUIRE_SIMPLE: dict[str, list[str]] = {
    "require_GET": ["GET"],
    "require_POST": ["POST"],
    "require_safe": ["GET", "HEAD"],
}

_HTTP_VERB_METHODS = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "trace",
})



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
    path_resolved: bool | None = None
    prefix_chain: list[str] = field(default_factory=list)
    note: str | None = None
    router_var: str | None = None


@dataclass
class PyImport:
    module: str
    names: list[str]
    line: int


@dataclass
class PythonRouteIndex:
    """Project-level FastAPI / Django mount facts. Never invents joins."""

    # (rel_file, var) → (literal_prefix | None, line, expression|None)
    router_own_prefix: dict[tuple[str, str], tuple[str | None, int | None, str | None]] = field(
        default_factory=dict
    )
    # FastAPI include_router graph: child (file, var) → parent with mount segment
    fastapi_graph: PrefixGraph = field(default_factory=PrefixGraph)
    # Routers that appear as include_router targets (unique resolve only)
    mounted_routers: set[tuple[str, str]] = field(default_factory=set)
    # Dotted module → candidate relative file paths (may be >1 → ambiguous)
    module_files: dict[str, list[str]] = field(default_factory=dict)
    # Relative file → source text (for Django include expansion)
    file_texts: dict[str, str] = field(default_factory=dict)


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


def _call_func_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _kw_str(call: ast.Call, name: str) -> tuple[str | None, str | None]:
    """Return (literal_or_None, expression_repr). None literal ⇒ non-literal/missing."""
    for kw in call.keywords:
        if kw.arg != name:
            continue
        lit = _const_str(kw.value)
        if lit is not None:
            return lit, None
        try:
            return None, ast.unparse(kw.value)
        except Exception:
            return None, "<non-literal>"
    return None, None  # keyword absent → empty prefix (literal "")


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Map local names → in-file router/blueprint path prefixes (literals only).

    FastAPI ``APIRouter(prefix=...)`` and Flask ``Blueprint(..., url_prefix=...)``.
    Non-literal / missing prefix → name omitted (no invented segment).
    """
    prefixes: dict[str, str] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        names = _attr_chain(node.value.func)
        if not names:
            continue
        ctor = names[-1]
        prefix_key = None
        if ctor == "APIRouter":
            prefix_key = "prefix"
        elif ctor == "Blueprint":
            prefix_key = "url_prefix"
        else:
            continue
        prefix = None
        for kw in node.value.keywords:
            if kw.arg == prefix_key:
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


def _string_list_from(node: ast.AST | None) -> list[str] | None:
    """Literal list/tuple of strings → uppercased methods; else None."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out: list[str] = []
    for elt in node.elts:
        s = _const_str(elt)
        if s:
            out.append(s.upper())
    return out or None


def _dedupe_methods(methods: list[str]) -> list[str]:
    out: list[str] = []
    for m in methods:
        u = m.upper()
        if u not in out:
            out.append(u)
    return out


def _flask_methods(call: ast.Call) -> list[str] | None:
    """Return explicit Flask methods= list, or None if not present."""
    for kw in call.keywords:
        if kw.arg != "methods":
            continue
        return _string_list_from(kw.value)
    return None


def _decorator_routes(
    node: ast.AST,
    router_prefixes: dict[str, str],
) -> list[tuple[str, str, bool, str | None]]:
    """Return list of (METHOD, path, assumed, router_var) from FastAPI/Flask decorators."""
    results: list[tuple[str, str, bool, str | None]] = []
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
        methods = flask_methods if flask_methods else [method]
        for mth in methods:
            results.append((mth, path, assumed, router_var))
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


def _handler_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _django_full_path(prefix: str, route: str) -> str:
    """Compose Django route text without inventing characters.

    - Empty prefix + relative ``path()`` string → leading ``/`` for display
      consistency with FastAPI/Flask routes.
    - Regex ``re_path`` / ``url`` literals that start with ``^`` are kept
      verbatim (prepending ``/`` would forge a character not in the pattern).
    - Callers must not pass a regex route under a non-empty prefix (skipped
      upstream — joining path-prefix + regex would invent a pattern).
    """
    if not prefix:
        if not route:
            return "/"
        if route.startswith("/") or route.startswith("^"):
            return route
        return f"/{route}"
    piece = route if route.startswith("/") else f"/{route}"
    return _compose_path(prefix, piece)


def _rel_to_module(rel: str) -> str:
    p = Path(rel.replace("\\", "/"))
    parts = list(p.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _unique_module_file(index: PythonRouteIndex, module: str) -> str | None:
    """Return the sole candidate file for a dotted module, else None (skip)."""
    cands = index.module_files.get(module) or []
    if len(cands) == 1:
        return cands[0]
    return None


def _extract_django_pattern_list(
    elts: list[ast.AST],
    prefix: str,
    routes: list[PyRoute],
    *,
    index: PythonRouteIndex | None = None,
    depth: int = 0,
    seen_modules: set[str] | None = None,
) -> None:
    """Walk a urlpatterns (or inline include) list. Literals only; order preserved."""
    seen_modules = seen_modules if seen_modules is not None else set()
    for elt in elts:
        if not isinstance(elt, ast.Call):
            continue
        fname = _call_func_name(elt)
        if fname not in _DJANGO_ROUTE_FUNCS or not elt.args:
            continue
        route_lit = _const_str(elt.args[0])
        if route_lit is None:
            # Non-literal route argument — skip; never invent a path string.
            continue
        # path-prefix + regex cannot be joined without guessing — skip.
        if prefix and route_lit.startswith("^"):
            continue
        full = _django_full_path(prefix, route_lit)
        line = getattr(elt, "lineno", 1) or 1
        target = elt.args[1] if len(elt.args) > 1 else None

        if isinstance(target, ast.Call) and _call_func_name(target) == "include":
            if not target.args:
                routes.append(PyRoute(
                    method="UNKNOWN", path=full, handler="", line=line, assumed=True,
                    path_resolved=False,
                    note="include() with no target — mount prefix only.",
                ))
                continue
            included = target.args[0]
            # Inline include([...]) — compose prefix in this file only.
            if isinstance(included, (ast.List, ast.Tuple)):
                _extract_django_pattern_list(
                    included.elts, full, routes,
                    index=index, depth=depth, seen_modules=seen_modules,
                )
                continue
            mod = _const_str(included)
            if mod is None:
                routes.append(PyRoute(
                    method="UNKNOWN", path=full, handler="", line=line, assumed=True,
                    path_resolved=False,
                    note="include() target is not a string literal — not joined.",
                ))
                continue
            # Cross-file module join — only when uniquely resolved.
            if (
                index is not None
                and depth < _MAX_INCLUDE_DEPTH
                and mod not in seen_modules
            ):
                target_file = _unique_module_file(index, mod)
                if target_file and target_file in index.file_texts:
                    try:
                        child_tree = ast.parse(index.file_texts[target_file])
                    except SyntaxError:
                        child_tree = None
                    if child_tree is not None:
                        child_routes: list[PyRoute] = []
                        _django_routes_from_tree(
                            child_tree,
                            child_routes,
                            index=index,
                            path_prefix=full,
                            depth=depth + 1,
                            seen_modules=seen_modules | {mod},
                        )
                        if child_routes:
                            routes.extend(child_routes)
                            continue
            # Unresolved / ambiguous / empty — mount point only; do not invent children.
            routes.append(PyRoute(
                method="UNKNOWN",
                path=full,
                handler="",
                line=line,
                assumed=True,
                path_resolved=False,
                note=(
                    f"include({mod!r}) could not be uniquely joined to a urlpatterns "
                    f"module in the files scanned — mount prefix only."
                ),
            ))
            continue

        handler = _handler_unparse(target)
        routes.append(PyRoute(
            method="UNKNOWN",
            path=full,
            handler=handler,
            line=line,
            assumed=False,
            path_resolved=True,
        ))


def _django_routes_from_tree(
    tree: ast.AST,
    routes: list[PyRoute],
    *,
    index: PythonRouteIndex | None = None,
    path_prefix: str = "",
    depth: int = 0,
    seen_modules: set[str] | None = None,
) -> None:
    body = tree.body if isinstance(tree, ast.Module) else []
    for node in body:
        targets: list[str] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.op, ast.Add)
        ):
            targets = [node.target.id]
            value = node.value
        if "urlpatterns" not in targets or value is None:
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        _extract_django_pattern_list(
            value.elts, path_prefix, routes,
            index=index, depth=depth, seen_modules=seen_modules,
        )


def _django_routes(
    tree: ast.AST,
    *,
    index: PythonRouteIndex | None = None,
) -> list[PyRoute]:
    """Extract Django urlpatterns path()/re_path()/url() entries.

    Honesty:
    - method is always UNKNOWN (HTTP method lives on the view, not the pattern).
    - Non-literal route args are skipped.
    - include('other.urls') joins children only when the module resolves uniquely.
    - Inline include([...]) with literal prefixes composes in-file only.
    - Dynamic urlpatterns (call/comprehension/+= of non-list) yield no routes.
    """
    routes: list[PyRoute] = []
    _django_routes_from_tree(tree, routes, index=index)
    return routes



def _module_defs(
    tree: ast.AST,
) -> tuple[dict[str, ast.AST], dict[str, ast.ClassDef]]:
    """Top-level functions and classes only (urlpatterns handlers resolve here)."""
    funcs: dict[str, ast.AST] = {}
    classes: dict[str, ast.ClassDef] = {}
    body = tree.body if isinstance(tree, ast.Module) else []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node
    return funcs, classes


def _decorator_http_methods(node: ast.AST) -> list[str] | None:
    """Explicit Django/DRF method constraints on a function view; else None."""
    found: list[str] = []
    saw = False
    for d in getattr(node, "decorator_list", []) or []:
        last = None
        call: ast.Call | None = None
        if isinstance(d, ast.Name):
            last = d.id
        elif isinstance(d, ast.Attribute):
            chain = _attr_chain(d)
            last = chain[-1] if chain else None
        elif isinstance(d, ast.Call):
            call = d
            chain = _attr_chain(d.func)
            last = chain[-1] if chain else None
        if not last:
            continue
        if last in _DJANGO_REQUIRE_SIMPLE:
            saw = True
            found.extend(_DJANGO_REQUIRE_SIMPLE[last])
            continue
        if call is not None and last in ("require_http_methods", "api_view"):
            methods = _string_list_from(call.args[0]) if call.args else None
            if methods is None:
                for kw in call.keywords:
                    if kw.arg == "methods":
                        methods = _string_list_from(kw.value)
                        break
            if methods:
                saw = True
                found.extend(methods)
            continue
    if not saw:
        return None
    return _dedupe_methods(found) or None


def _cbv_http_methods(cls: ast.ClassDef) -> list[str] | None:
    """HTTP verb methods defined on this class body only (no inherited invent)."""
    found: list[str] = []
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name.lower() in _HTTP_VERB_METHODS:
                found.append(item.name.upper())
    return _dedupe_methods(found) or None


def _resolve_django_handler_methods(
    handler: str,
    funcs: dict[str, ast.AST],
    classes: dict[str, ast.ClassDef],
) -> list[str] | None:
    """Resolve methods only when the view object is defined in this module."""
    if not handler:
        return None
    try:
        expr = ast.parse(handler, mode="eval").body
    except SyntaxError:
        return None

    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "as_view"
        and isinstance(expr.func.value, ast.Name)
    ):
        cls = classes.get(expr.func.value.id)
        if cls is None:
            return None
        return _cbv_http_methods(cls)

    if isinstance(expr, ast.Name):
        fn = funcs.get(expr.id)
        if fn is None:
            return None
        return _decorator_http_methods(fn)

    return None


def _enrich_django_route_methods(routes: list[PyRoute], tree: ast.AST) -> list[PyRoute]:
    """Replace UNKNOWN with in-file view constraints; expand multi-method views."""
    funcs, classes = _module_defs(tree)
    out: list[PyRoute] = []
    for r in routes:
        if r.method != "UNKNOWN":
            out.append(r)
            continue
        methods = _resolve_django_handler_methods(r.handler, funcs, classes)
        if not methods:
            out.append(r)
            continue
        for mth in methods:
            out.append(PyRoute(
                method=mth,
                path=r.path,
                handler=r.handler,
                line=r.line,
                assumed=r.assumed,
                depends=list(r.depends),
                path_resolved=r.path_resolved,
                prefix_chain=list(r.prefix_chain),
                note=r.note,
                router_var=r.router_var,
            ))
    return out


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


# ---------------------------------------------------------------------------
# Project-level FastAPI / Django index (edge production only; resolve is shared)
# ---------------------------------------------------------------------------


def _collect_import_bindings(tree: ast.AST) -> dict[str, tuple[str, str | None]]:
    """local_name → (module_dotted, attr_or_None).

    ``attr is None`` means the local name is the module itself.
    ``attr`` set means ``from module import attr as local``.
    """
    bindings: dict[str, tuple[str, str | None]] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[-1]
                bindings[local] = (alias.name, None)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                # from pkg import mod — treat as submodule pkg.mod when used as module
                bindings[local] = (node.module, alias.name)
    return bindings


def _resolve_router_ref(
    ref: ast.AST,
    *,
    file_path: str,
    bindings: dict[str, tuple[str, str | None]],
    index: PythonRouteIndex,
    local_routers: set[str],
) -> tuple[str, str] | None:
    """Map an include_router argument to a unique (file, var), or None to skip."""
    if isinstance(ref, ast.Name):
        name = ref.id
        if name in local_routers:
            return (file_path, name)
        binding = bindings.get(name)
        if binding is None:
            return None
        mod, attr = binding
        if attr is None:
            return None  # bare module name — not a router var
        # from mod import attr  (attr is the router name)
        target_mod = mod
        target_var = attr
        target_file = _unique_module_file(index, target_mod)
        if target_file is None:
            return None
        if (target_file, target_var) not in index.router_own_prefix and (
            target_file, target_var
        ) not in index.fastapi_graph.roots:
            # Must be a known APIRouter binding in that file
            if (target_file, target_var) not in {
                k for k in index.router_own_prefix
            }:
                # Allow routers recorded with None prefix too — check keys only
                pass
        if (target_file, target_var) in index.router_own_prefix:
            return (target_file, target_var)
        return None

    if isinstance(ref, ast.Attribute) and isinstance(ref.value, ast.Name):
        mod_local = ref.value.id
        var = ref.attr
        binding = bindings.get(mod_local)
        if binding is None:
            return None
        mod, attr = binding
        if attr is None:
            target_mod = mod
        else:
            # from pkg import items — items is submodule pkg.items
            target_mod = f"{mod}.{attr}"
        target_file = _unique_module_file(index, target_mod)
        if target_file is None:
            return None
        if (target_file, var) in index.router_own_prefix:
            return (target_file, var)
        return None

    return None


def build_python_route_index(
    root: Path,
    *,
    max_files: int = _MAX_INDEX_FILES,
) -> PythonRouteIndex:
    """Scan ``.py`` files for FastAPI routers/mounts and Django module paths.

    Accuracy over coverage: ambiguous module names and non-literal prefixes
    are recorded as unresolvable — callers must assume/skip, never invent.
    """
    root = Path(root)
    index = PythonRouteIndex()
    scanned = 0
    py_files: list[tuple[str, str]] = []  # (rel, text)

    for path in root.rglob("*.py"):
        if scanned >= max_files:
            break
        if not path.is_file():
            continue
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _SKIP_DIR_NAMES for part in rel_path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        rel = str(rel_path).replace("\\", "/")
        py_files.append((rel, text))
        index.file_texts[rel] = text
        mod = _rel_to_module(rel)
        if mod:
            index.module_files.setdefault(mod, []).append(rel)

    # First pass: record APIRouter / FastAPI assignments so refs can resolve
    parsed: list[tuple[str, ast.AST]] = []
    for rel, text in py_files:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        parsed.append((rel, tree))
        body = tree.body if isinstance(tree, ast.Module) else []
        for node in body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            names = _attr_chain(node.value.func)
            if not names:
                continue
            kind = names[-1]
            line = getattr(node, "lineno", None)
            for t in node.targets:
                if not isinstance(t, ast.Name):
                    continue
                sym = (rel, t.id)
                if kind == "APIRouter":
                    if any(kw.arg == "prefix" for kw in node.value.keywords):
                        lit, expr = _kw_str(node.value, "prefix")
                    else:
                        lit, expr = "", None
                    index.router_own_prefix[sym] = (lit, line, expr)
                elif kind == "Blueprint":
                    if any(kw.arg == "url_prefix" for kw in node.value.keywords):
                        lit, expr = _kw_str(node.value, "url_prefix")
                    else:
                        lit, expr = "", None
                    index.router_own_prefix[sym] = (lit, line, expr)
                elif kind == "FastAPI":
                    index.fastapi_graph.add_root(sym, declared_at=line)
                elif kind == "Flask":
                    index.fastapi_graph.add_root(sym, declared_at=line)

    # Second pass: include_router mounts (needs router_own_prefix populated)
    for rel, tree in parsed:
        _scan_file_fastapi_mounts_only(tree, rel, index)

    return index


def _scan_file_fastapi_mounts_only(
    tree: ast.AST,
    file_path: str,
    index: PythonRouteIndex,
) -> None:
    bindings = _collect_import_bindings(tree)
    local_routers = {var for (f, var) in index.router_own_prefix if f == file_path}
    local_apps = {
        var for (f, var) in index.fastapi_graph.roots if f == file_path
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr not in ("include_router", "register_blueprint"):
            continue
        if not node.args:
            continue
        parent_names = _attr_chain(node.func)
        if len(parent_names) < 2:
            continue
        parent_var = parent_names[0]
        if parent_var in local_apps:
            parent_sym = (file_path, parent_var)
        elif parent_var in local_routers:
            parent_sym = (file_path, parent_var)
        else:
            continue
        child = _resolve_router_ref(
            node.args[0],
            file_path=file_path,
            bindings=bindings,
            index=index,
            local_routers=local_routers,
        )
        if child is None:
            continue
        kw_name = "prefix" if attr == "include_router" else "url_prefix"
        if any(kw.arg == kw_name for kw in node.keywords):
            lit, expr = _kw_str(node, kw_name)
        else:
            lit, expr = "", None
        line = getattr(node, "lineno", None)
        index.fastapi_graph.add_mount(
            parent_sym, child, lit, declared_at=line, expression=expr,
        )
        index.mounted_routers.add(child)


def _local_fastapi_index(tree: ast.AST, file_path: str) -> PythonRouteIndex:
    """In-file-only FastAPI graph when no project index is available."""
    index = PythonRouteIndex()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        names = _attr_chain(node.value.func)
        if not names:
            continue
        kind = names[-1]
        line = getattr(node, "lineno", None)
        for t in node.targets:
            if not isinstance(t, ast.Name):
                continue
            sym = (file_path, t.id)
            if kind == "APIRouter":
                if any(kw.arg == "prefix" for kw in node.value.keywords):
                    lit, expr = _kw_str(node.value, "prefix")
                else:
                    lit, expr = "", None
                index.router_own_prefix[sym] = (lit, line, expr)
            elif kind == "Blueprint":
                if any(kw.arg == "url_prefix" for kw in node.value.keywords):
                    lit, expr = _kw_str(node.value, "url_prefix")
                else:
                    lit, expr = "", None
                index.router_own_prefix[sym] = (lit, line, expr)
            elif kind == "FastAPI":
                index.fastapi_graph.add_root(sym, declared_at=line)
            elif kind == "Flask":
                index.fastapi_graph.add_root(sym, declared_at=line)
    _scan_file_fastapi_mounts_only(tree, file_path, index)
    return index


def _apply_fastapi_mounts(
    routes: list[PyRoute],
    *,
    file_path: str,
    index: PythonRouteIndex | None,
    tree: ast.AST,
) -> None:
    """Compose include_router mount prefixes onto router-local paths in place.

    When a project ``route_index`` is provided, unmounted APIRouter routes are
    marked assumed (mount prefix unknown). When only in-file facts are available,
    in-file ``include_router`` still composes; an APIRouter with no in-file mount
    keeps its router-local path and is *not* forced assumed (single-file unit
    tests / snippets have no mount site to discover).
    """
    project_scoped = index is not None
    local = _local_fastapi_index(tree, file_path)
    if index is None:
        index = local
    else:
        # Merge this file's routers/roots even when the path is not yet on disk
        # (unit tests / new chunks). Never overwrite a project-scanned mount.
        for sym, meta in local.router_own_prefix.items():
            index.router_own_prefix.setdefault(sym, meta)
        for sym in local.fastapi_graph.roots:
            if sym not in index.fastapi_graph.roots:
                index.fastapi_graph.add_root(sym)
        for child, edge in local.fastapi_graph.edges.items():
            if child not in index.fastapi_graph.edges:
                index.fastapi_graph.edges[child] = edge
                index.mounted_routers.add(child)

    graph = index.fastapi_graph
    for route in routes:
        var = route.router_var
        if not var:
            continue
        sym = (file_path, var)
        # FastAPI app root: path is complete if app is a declared root
        if sym in graph.roots:
            res = full_route_path(graph, sym, route.path)
            route.path = res.path
            route.path_resolved = res.resolved
            route.prefix_chain = chain_as_strings(res.chain)
            if res.note:
                route.note = res.note
            if not res.resolved:
                route.assumed = True
            continue

        if sym not in index.router_own_prefix:
            # Flask @app.route etc. — leave as-is
            continue

        # APIRouter-decorated route
        if sym in graph.edges or sym in index.mounted_routers:
            res = full_route_path(graph, sym, route.path)
            route.path = res.path
            route.path_resolved = res.resolved
            route.prefix_chain = chain_as_strings(res.chain)
            if res.note:
                route.note = res.note
            if not res.resolved:
                route.assumed = True
            elif not route.assumed:
                route.path_resolved = True
        elif project_scoped:
            # Router never found in any include_router — path is router-local.
            route.path_resolved = False
            route.assumed = True
            route.note = (
                "This router/blueprint was not found in any include_router(...) / "
                "register_blueprint(...) call in the files scanned, so the mount "
                "prefix is unknown and the path shown is router-local."
            )
            route.prefix_chain = [f"{file_path}::{var}"]
        else:
            # In-file only, no mount in this snippet — keep router-local path.
            route.path_resolved = True if not route.assumed else False


def extract_python(
    text: str,
    *,
    file_path: str = "__local__",
    route_index: PythonRouteIndex | None = None,
) -> tuple[list[PyFunction], list[PyRoute], list[PyImport], list[str]]:
    """Parse source; return functions, routes, imports, module-level __all__ names.

    When ``route_index`` is provided (project pre-pass), FastAPI
    ``include_router`` mounts and Django ``include()`` modules join only on
    unique literal resolution. Otherwise in-file facts alone are used;
    unresolved cross-file prefixes stay assumed.
    """
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
        for method, path, assumed, router_var in route_specs:
            routes.append(PyRoute(
                method=method,
                path=path,
                handler=node.name,
                line=start,
                assumed=assumed,
                depends=list(deps),
                router_var=router_var,
            ))

    # Compose include_router mounts (in-file and/or project index).
    _apply_fastapi_mounts(
        routes, file_path=file_path, index=route_index, tree=tree,
    )

    # Django urlpatterns — with optional cross-file include() join.
    django = _django_routes(tree, index=route_index)
    routes.extend(_enrich_django_route_methods(django, tree))

    return functions, routes, imports, sorted(all_names or [])
