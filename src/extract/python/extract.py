"""Python extraction via stdlib ast — zero third-party deps.

Honesty: only facts the AST can prove. Route prefixes from other files
stay assumed. In-file APIRouter(prefix=...) / Blueprint(url_prefix=...)
literals are composed; in-file include_router / register_blueprint
literal mounts compose too. Django urlpatterns path()/re_path()/url()
literals only; include() is flagged assumed and never joined across
files. HTTP method stays UNKNOWN unless the view (or CBV HTTP verb
methods) is defined in the same file with an explicit constraint.
Docstrings via ast.get_docstring (not upward // scan).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

# Django URL dispatcher helpers (django.urls).
_DJANGO_ROUTE_FUNCS = frozenset({"path", "re_path", "url"})

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


def _local_route_prefixes(tree: ast.AST) -> dict[str, str]:
    """Map local names → in-file router/blueprint path prefixes (literals only).

    - FastAPI ``APIRouter(prefix='...')``
    - Flask ``Blueprint(..., url_prefix='...')``
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


def _mount_prefixes(
    tree: ast.AST,
) -> tuple[dict[str, list[str]], set[str]]:
    """In-file include_router / register_blueprint mounts (literals only).

    Returns (name → mount prefix list, names with non-literal mount prefix).
    Cross-module targets (``users.router``) are skipped — never invent a join.
    """
    mounts: dict[str, list[str]] = {}
    unresolved: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        names = _attr_chain(node.func)
        if not names:
            continue
        last = names[-1]
        if last == "include_router":
            kw_name = "prefix"
        elif last == "register_blueprint":
            kw_name = "url_prefix"
        else:
            continue
        if not node.args or not isinstance(node.args[0], ast.Name):
            continue
        target = node.args[0].id
        prefix_lit: str | None = ""
        saw_kw = False
        for kw in node.keywords:
            if kw.arg != kw_name:
                continue
            saw_kw = True
            lit = _const_str(kw.value)
            if lit is None:
                prefix_lit = None
            else:
                prefix_lit = lit
            break
        if prefix_lit is None:
            unresolved.add(target)
            continue
        # Omitted kw → empty mount segment (still a same-file registration).
        if not saw_kw:
            prefix_lit = ""
        mounts.setdefault(target, []).append(prefix_lit)
    return mounts, unresolved


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
        return _string_list_from(kw.value)
    return None


def _decorator_routes(
    node: ast.AST,
    router_prefixes: dict[str, str],
    mount_prefixes: dict[str, list[str]],
    unresolved_mounts: set[str],
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
        router_prefix = router_prefixes.get(router_var) if router_var else None
        mounts = mount_prefixes.get(router_var, [""]) if router_var else [""]
        if router_var and router_var in unresolved_mounts:
            assumed = True
        methods = flask_methods if flask_methods else [method]
        for mount in mounts:
            composed = path
            if router_prefix:
                composed = _compose_path(router_prefix, composed)
            if mount:
                composed = _compose_path(mount, composed)
            for mth in methods:
                results.append((mth, composed, assumed))
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
        if not isinstance(child, ast.Call):
            continue
        fname = None
        if isinstance(child.func, ast.Name) and child.func.id == "Depends":
            fname = "Depends"
        elif isinstance(child.func, ast.Attribute) and child.func.attr == "Depends":
            fname = "Depends"
        if fname != "Depends":
            continue
        if child.args and isinstance(child.args[0], ast.Name):
            deps.append(child.args[0].id)
        elif child.args and isinstance(child.args[0], ast.Attribute):
            deps.append(child.args[0].attr)
    return deps


def _call_func_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


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


def _extract_django_pattern_list(
    elts: list[ast.AST],
    prefix: str,
    routes: list[PyRoute],
) -> None:
    """Walk a urlpatterns (or inline include) list. Literals only; order preserved."""
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
                ))
                continue
            included = target.args[0]
            # Inline include([...]) — compose prefix in this file only.
            if isinstance(included, (ast.List, ast.Tuple)):
                _extract_django_pattern_list(included.elts, full, routes)
                continue
            # Module-string / other include — mount point only; do not join children.
            routes.append(PyRoute(
                method="UNKNOWN", path=full, handler="", line=line, assumed=True,
            ))
            continue

        handler = _handler_unparse(target)
        routes.append(PyRoute(
            method="UNKNOWN",
            path=full,
            handler=handler,
            line=line,
            assumed=False,
        ))


def _django_routes(tree: ast.AST) -> list[PyRoute]:
    """Extract Django urlpatterns path()/re_path()/url() entries.

    Honesty:
    - method starts UNKNOWN (HTTP method lives on the view, not the pattern).
    - Non-literal route args are skipped.
    - include('other.urls') emits an assumed mount prefix; children are not joined.
    - Inline include([...]) with literal prefixes composes in-file only.
    - Dynamic urlpatterns (call/comprehension/+= of non-list) yield no routes.
    """
    routes: list[PyRoute] = []
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
            # Built by a call/comprehension/binop — do not invent entries.
            continue
        _extract_django_pattern_list(value.elts, "", routes)
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
            # Bare @api_view() / non-literal list — leave UNKNOWN (do not invent GET).
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

    # Class.as_view(...) — only bare ClassName in this file.
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

    # Bare function name in this file.
    if isinstance(expr, ast.Name):
        fn = funcs.get(expr.id)
        if fn is None:
            return None
        return _decorator_http_methods(fn)

    # views.foo / app.views.bar — cross-module; do not invent.
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

    router_prefixes = _local_route_prefixes(tree)
    mount_prefixes, unresolved_mounts = _mount_prefixes(tree)

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
        route_specs = _decorator_routes(
            node, router_prefixes, mount_prefixes, unresolved_mounts,
        )
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

    # Django urlpatterns are module-level assignments, not function decorators.
    django = _django_routes(tree)
    routes.extend(_enrich_django_route_methods(django, tree))

    return functions, routes, imports, sorted(all_names or [])
