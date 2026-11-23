"""Express.js route / middleware extraction (regex).

Honesty rules (never invent edges or full URLs):
- Compose mount prefixes only when every segment is a string literal.
- Non-literal mount prefixes / regex route paths → assumed=True + note; skip
  when we cannot name a path without guessing.
- ``app.use(prefix, target)`` is a router mount only when ``target`` is a known
  Router/app binding (local or uniquely resolved ``require('./…')``); otherwise
  it is path-scoped middleware (not a mount).
- Cross-file mounts join via shared ``PrefixGraph`` only on unique literal
  module resolution (same honesty as FastAPI/Django/Go Fiber). Ambiguous /
  missing / package ``require('express')`` → skip inventing children.
- Roots are ``express()`` bindings only — no conventional ``app`` guess.

Optional tree-sitter probe (``CEV_TREE_SITTER=1``): JS declaration names via
``tree_sitter_probe`` / ``tree_sitter_decl_names_or_fallback``. Records stay
regex + PrefixGraph — call-tree middleware arity deferred until parity
tests (see feasibility matrix). Never invents mounts from partial trees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..route_prefix import (
    PrefixGraph,
    chain_as_strings,
    full_route_path,
)

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "all")
HTTP_METHOD_ALT = "|".join(HTTP_METHODS)

EXPRESS_APP_RE = re.compile(
    r"""(?:const|let|var)\s+(?P<var>\w+)\s*=\s*express\s*\(""",
)
ROUTER_RE = re.compile(
    r"""(?:const|let|var)\s+(?P<var>\w+)\s*=\s*(?:express\.)?Router\s*\(""",
)

# Literal-prefix mount: parent.use('/prefix', child)
USE_MOUNT_LIT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*(?P<quote>['"`])(?P<prefix>[^'"`]*)(?P=quote)\s*,\s*(?P<child>\w+)\s*""",
    re.IGNORECASE,
)
# Root mount with no path: parent.use(child) where child is a router id
USE_MOUNT_ROOT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*(?P<child>\w+)\s*\)""",
    re.IGNORECASE,
)
# Non-literal prefix mount: parent.use(expr, child) — mark child assumed
USE_MOUNT_NONLIT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*(?P<prefix_expr>[^,]+?)\s*,\s*(?P<child>\w+)\s*""",
    re.IGNORECASE,
)
# Inline require mount: parent.use('/prefix', require('./x'))
USE_MOUNT_REQUIRE_LIT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*(?P<quote>['"`])(?P<prefix>[^'"`]*)(?P=quote)\s*,\s*"""
    r"""require\s*\(\s*(?P<rq>['"`])(?P<req>[^'"`]+)(?P=rq)\s*\)""",
    re.IGNORECASE,
)
USE_MOUNT_REQUIRE_ROOT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*require\s*\(\s*(?P<rq>['"`])(?P<req>[^'"`]+)(?P=rq)\s*\)\s*\)""",
    re.IGNORECASE,
)
USE_MOUNT_REQUIRE_NONLIT_RE = re.compile(
    r"""(?P<parent>\w+)\.use\(\s*(?P<prefix_expr>[^,]+?)\s*,\s*"""
    r"""require\s*\(\s*(?P<rq>['"`])(?P<req>[^'"`]+)(?P=rq)\s*\)""",
    re.IGNORECASE,
)

REQUIRE_BIND_RE = re.compile(
    r"""(?:const|let|var)\s+(?P<var>\w+)\s*=\s*require\s*\(\s*(?P<q>['"`])(?P<path>[^'"`]+)(?P=q)\s*\)""",
)
MODULE_EXPORTS_RE = re.compile(
    r"""(?:module\s*\.\s*exports|exports)\s*=\s*(?P<var>\w+)\s*;?""",
)
EXPORT_DEFAULT_RE = re.compile(
    r"""export\s+default\s+(?P<var>\w+)\s*;?""",
)

ROUTE_METHOD_RE = re.compile(
    rf"""(?P<var>\w+)\.(?P<method>{HTTP_METHOD_ALT})\(\s*""",
    re.IGNORECASE,
)
ROUTE_CHAIN_RE = re.compile(
    r"""(?P<var>\w+)\.route\(\s*(?P<quote>['"`])(?P<path>[^'"`]*)(?P=quote)\s*\)"""
    r"""(?P<chain>(?:\s*\.\s*(?:get|post|put|delete|patch|head|options|all)\s*\([^;]*)+)""",
    re.IGNORECASE,
)
CHAIN_METHOD_RE = re.compile(
    rf"""\.\s*(?P<method>{HTTP_METHOD_ALT})\s*\(\s*(?P<handler>[A-Za-z_][\w.]*)?""",
    re.IGNORECASE,
)

MW_USE_RE = re.compile(
    r"""(?P<var>\w+)\.use\(\s*(?P<call>[^)]+)\)""",
    re.IGNORECASE,
)

_STRING_LIT_RE = re.compile(r"""^(?P<quote>['"`])(?P<body>(?:\\.|(?!(?P=quote)).)*)(?P=quote)$""")
_REGEX_LIT_RE = re.compile(r"^/(?P<body>(?:\\.|\[(?:\\.|[^\]])*\]|[^/])+)/(?P<flags>[gimsuy]*)")

_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "dist", "build", ".next", "coverage",
})
_MAX_INDEX_FILES = 400
_JS_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")


@dataclass
class ExpressRoute:
    method: str
    path: str
    router_var: str
    line: int
    assumed: bool
    handler: str
    note: str | None = None
    route_middleware: list[str] = field(default_factory=list)
    path_resolved: bool | None = None
    prefix_chain: list[str] = field(default_factory=list)


@dataclass
class ExpressMiddleware:
    router_var: str
    name: str
    order: int
    line: int
    is_auth: bool
    assumed: bool = True
    mount_path: str | None = None  # set for path-scoped .use('/p', fn)


@dataclass
class ExpressRouteIndex:
    """Project-level Express mount facts. Never invents joins."""

    graph: PrefixGraph = field(default_factory=PrefixGraph)
    # (rel_file, var) known as express() root or Router()
    known_routers: set[tuple[str, str]] = field(default_factory=set)
    # rel_file → exported router var (module.exports = X / export default X)
    module_exports: dict[str, str] = field(default_factory=dict)
    # Routers that appear as use() mount targets (unique resolve only)
    mounted_routers: set[tuple[str, str]] = field(default_factory=set)
    # Local binding in a file: (rel_file, local_var) → (target_file, target_var)
    require_bindings: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    file_texts: dict[str, str] = field(default_factory=dict)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _mw_name(call: str) -> str:
    call = call.strip()
    m = re.match(r"([\w.]+)", call)
    return m.group(1) if m else call[:40]


def _looks_auth(name: str) -> bool:
    return bool(re.search(r"(?i)auth|jwt|passport|session", name))


def _split_call_args(args_src: str) -> list[str]:
    """Split top-level comma-separated call args, respecting (), [], {}, strings."""
    args: list[str] = []
    buf: list[str] = []
    depth_paren = depth_brack = depth_brace = 0
    in_str: str | None = None
    escape = False
    i = 0
    while i < len(args_src):
        ch = args_src[i]
        if in_str:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "'\"`":
            in_str = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth_paren += 1
            buf.append(ch)
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
            buf.append(ch)
        elif ch == "[":
            depth_brack += 1
            buf.append(ch)
        elif ch == "]":
            depth_brack = max(0, depth_brack - 1)
            buf.append(ch)
        elif ch == "{":
            depth_brace += 1
            buf.append(ch)
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
            buf.append(ch)
        elif ch == "," and depth_paren == depth_brack == depth_brace == 0:
            piece = "".join(buf).strip()
            if piece:
                args.append(piece)
            buf = []
        else:
            buf.append(ch)
        i += 1
    piece = "".join(buf).strip()
    if piece:
        args.append(piece)
    return args


def _extract_call_args(text: str, open_paren_end: int) -> tuple[str, int] | None:
    """Given index just after '(', return (args_src, close_index_exclusive) or None."""
    depth = 1
    i = open_paren_end
    in_str: str | None = None
    escape = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "'\"`":
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_end:i], i + 1
        i += 1
    return None


def _parse_path_arg(arg: str) -> list[tuple[str, bool, str | None]]:
    """Return list of (path, is_literal_ok, note).

    - String literal → (body, True, None)
    - Array of string literals → one entry per literal; non-literals in the
      array are skipped (never invent)
    - Regex literal → ('<regex:…>', False, note) so callers mark assumed
    - Anything else → empty (skip; do not invent)
    """
    arg = arg.strip()
    sm = _STRING_LIT_RE.match(arg)
    if sm:
        return [(sm.group("body"), True, None)]

    if arg.startswith("[") and arg.endswith("]"):
        inner = arg[1:-1].strip()
        out: list[tuple[str, bool, str | None]] = []
        for part in _split_call_args(inner):
            pm = _STRING_LIT_RE.match(part.strip())
            if pm:
                out.append((pm.group("body"), True, None))
            # Non-literal array elements skipped — honesty.
        return out

    rm = _REGEX_LIT_RE.match(arg)
    if rm:
        body = rm.group("body")
        note = (
            f"Route path is a RegExp literal (/{body}/); "
            "URL not synthesized — marked assumed."
        )
        return [(f"<regex:{body}>", False, note)]

    return []


def _parse_handler_chain(args: list[str]) -> tuple[str, list[str]]:
    """Last identifier-like callable is handler; prior identifiers are route middleware.

    Arrays of identifiers are flattened in order. Inline functions / arrows
    become synthetic inline handlers when they are the terminal callback.
    """
    names: list[str] = []
    for arg in args:
        a = arg.strip()
        if a.startswith("[") and a.endswith("]"):
            for part in _split_call_args(a[1:-1]):
                n = _ident_or_none(part.strip())
                if n:
                    names.append(n)
            continue
        n = _ident_or_none(a)
        if n:
            names.append(n)
            continue
        if re.match(r"^(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)", a):
            names.append("__inline__")
    if not names:
        return "handler", []
    handler = names[-1]
    middleware = [n for n in names[:-1] if n != "__inline__"]
    if handler == "__inline__":
        handler = "inline"
    return handler, middleware


def _ident_or_none(expr: str) -> str | None:
    m = re.match(r"^([A-Za-z_][\w.]*)(?:\s*\(.*\))?\s*$", expr.strip())
    if not m:
        return None
    name = m.group(1)
    if name in ("async", "function", "await"):
        return None
    return name


def _norm_rel(parts: list[str]) -> str:
    out: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if out:
                out.pop()
            continue
        out.append(p)
    return "/".join(out)


def _resolve_require_candidates(
    from_file: str,
    req_path: str,
    indexed_files: set[str],
) -> list[str]:
    """Resolve a relative require() to candidate indexed files. Never packages."""
    if not req_path.startswith("."):
        return []
    from_dir = str(Path(from_file).parent).replace("\\", "/")
    if from_dir in (".", ""):
        joined = req_path
    else:
        joined = f"{from_dir}/{req_path}"
    base = _norm_rel(joined.replace("\\", "/").split("/"))
    cands: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        if p in indexed_files and p not in seen:
            seen.add(p)
            cands.append(p)

    # Exact + suffix variants
    _add(base)
    for suf in _JS_SUFFIXES:
        if base.endswith(suf):
            continue
        _add(base + suf)
    # Directory index
    for suf in _JS_SUFFIXES:
        _add(f"{base}/index{suf}")
    return cands


def _unique_require_file(
    from_file: str,
    req_path: str,
    indexed_files: set[str],
) -> str | None:
    cands = _resolve_require_candidates(from_file, req_path, indexed_files)
    if len(cands) == 1:
        return cands[0]
    return None


def _scan_file_bindings(text: str) -> dict[str, str]:
    """local_var → require path string (relative only kept by caller)."""
    return {m.group("var"): m.group("path") for m in REQUIRE_BIND_RE.finditer(text)}


def _exported_router_var(text: str) -> str | None:
    """Unique default export of a router var, or None if missing/ambiguous."""
    exports = [m.group("var") for m in MODULE_EXPORTS_RE.finditer(text)]
    defaults = [m.group("var") for m in EXPORT_DEFAULT_RE.finditer(text)]
    names = exports + defaults
    if len(names) == 1:
        return names[0]
    if len(set(names)) == 1:
        return names[0]
    return None


def build_express_route_index(
    root: Path,
    *,
    max_files: int = _MAX_INDEX_FILES,
) -> ExpressRouteIndex:
    """Scan JS/TS files for Express apps, routers, and cross-file use() mounts.

    Accuracy over coverage: ambiguous require targets and non-literal prefixes
    are skipped — callers must assume, never invent.
    """
    root = Path(root)
    index = ExpressRouteIndex()
    scanned = 0
    files: list[tuple[str, str]] = []

    for path in root.rglob("*"):
        if scanned >= max_files:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in _JS_SUFFIXES:
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
        files.append((rel, text))
        index.file_texts[rel] = text

    indexed = set(index.file_texts)

    # Pass 1: apps, routers, exports
    for rel, text in files:
        for m in EXPRESS_APP_RE.finditer(text):
            sym = (rel, m.group("var"))
            index.known_routers.add(sym)
            index.graph.add_root(sym, declared_at=_line_of(text, m.start()))
        for m in ROUTER_RE.finditer(text):
            index.known_routers.add((rel, m.group("var")))
        exported = _exported_router_var(text)
        if exported and (rel, exported) in index.known_routers:
            index.module_exports[rel] = exported

    # Pass 2: require bindings that uniquely resolve to an exported router
    for rel, text in files:
        for local, req_path in _scan_file_bindings(text).items():
            target = _unique_require_file(rel, req_path, indexed)
            if target is None:
                continue
            export_var = index.module_exports.get(target)
            if not export_var:
                continue
            index.require_bindings[(rel, local)] = (target, export_var)

    # Pass 3: use() mounts (local ids, require bindings, inline require)
    for rel, text in files:
        _scan_file_express_mounts(rel, text, index)

    return index


def _child_symbol_for_ident(
    file_path: str,
    ident: str,
    index: ExpressRouteIndex,
    local_known: set[str],
) -> tuple[str, str] | None:
    """Map a mount target identifier to a unique (file, var), or None."""
    if ident in local_known:
        return (file_path, ident)
    binding = index.require_bindings.get((file_path, ident))
    if binding is not None:
        return binding
    return None


def _child_symbol_for_require(
    file_path: str,
    req_path: str,
    index: ExpressRouteIndex,
) -> tuple[str, str] | None:
    target = _unique_require_file(file_path, req_path, set(index.file_texts))
    if target is None:
        return None
    export_var = index.module_exports.get(target)
    if not export_var:
        return None
    return (target, export_var)


def _scan_file_express_mounts(
    file_path: str,
    text: str,
    index: ExpressRouteIndex,
) -> None:
    local_known = {var for (f, var) in index.known_routers if f == file_path}
    local_roots = {
        var for (f, var) in index.graph.roots if f == file_path
    }
    # Also treat local routers as valid mount parents (nested mounts).
    local_parents = local_known | local_roots

    def _parent_sym(parent: str) -> tuple[str, str] | None:
        if parent in local_parents:
            return (file_path, parent)
        return None

    # Inline require with literal prefix
    for m in USE_MOUNT_REQUIRE_LIT_RE.finditer(text):
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_require(file_path, m.group("req"), index)
        if child is None:
            continue
        index.graph.add_mount(
            parent, child, m.group("prefix"),
            declared_at=_line_of(text, m.start()),
        )
        index.mounted_routers.add(child)

    for m in USE_MOUNT_REQUIRE_ROOT_RE.finditer(text):
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_require(file_path, m.group("req"), index)
        if child is None:
            continue
        if child not in index.graph.edges:
            index.graph.add_mount(
                parent, child, "",
                declared_at=_line_of(text, m.start()),
            )
            index.mounted_routers.add(child)

    for m in USE_MOUNT_REQUIRE_NONLIT_RE.finditer(text):
        prefix_expr = m.group("prefix_expr").strip()
        if _STRING_LIT_RE.match(prefix_expr):
            continue  # literal handled above
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_require(file_path, m.group("req"), index)
        if child is None:
            continue
        if child not in index.graph.edges:
            index.graph.add_mount(
                parent, child, None,
                declared_at=_line_of(text, m.start()),
                expression=prefix_expr,
            )
            index.mounted_routers.add(child)

    # Identifier mounts (local router or require()-bound local)
    for m in USE_MOUNT_LIT_RE.finditer(text):
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_ident(
            file_path, m.group("child"), index, local_known,
        )
        if child is None:
            continue
        index.graph.add_mount(
            parent, child, m.group("prefix"),
            declared_at=_line_of(text, m.start()),
        )
        index.mounted_routers.add(child)

    for m in USE_MOUNT_ROOT_RE.finditer(text):
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_ident(
            file_path, m.group("child"), index, local_known,
        )
        if child is None:
            continue
        if child not in index.graph.edges:
            index.graph.add_mount(
                parent, child, "",
                declared_at=_line_of(text, m.start()),
            )
            index.mounted_routers.add(child)

    for m in USE_MOUNT_NONLIT_RE.finditer(text):
        prefix_expr = m.group("prefix_expr").strip()
        if _STRING_LIT_RE.match(prefix_expr):
            continue
        # Skip inline require forms (handled above)
        if re.match(r"^require\s*\(", prefix_expr):
            continue
        parent = _parent_sym(m.group("parent"))
        if parent is None:
            continue
        child = _child_symbol_for_ident(
            file_path, m.group("child"), index, local_known,
        )
        if child is None:
            continue
        if child not in index.graph.edges:
            index.graph.add_mount(
                parent, child, None,
                declared_at=_line_of(text, m.start()),
                expression=prefix_expr,
            )
            index.mounted_routers.add(child)


def _local_express_index(text: str, file_path: str) -> ExpressRouteIndex:
    """In-file-only Express graph when no project index is available."""
    index = ExpressRouteIndex()
    index.file_texts[file_path] = text
    for m in EXPRESS_APP_RE.finditer(text):
        sym = (file_path, m.group("var"))
        index.known_routers.add(sym)
        index.graph.add_root(sym, declared_at=_line_of(text, m.start()))
    for m in ROUTER_RE.finditer(text):
        index.known_routers.add((file_path, m.group("var")))
    exported = _exported_router_var(text)
    if exported and (file_path, exported) in index.known_routers:
        index.module_exports[file_path] = exported
    _scan_file_express_mounts(file_path, text, index)
    return index


def _merge_local_into_index(
    index: ExpressRouteIndex,
    local: ExpressRouteIndex,
) -> None:
    """Merge this file's facts; never overwrite a project-scanned mount."""
    for sym in local.known_routers:
        index.known_routers.add(sym)
    for sym in local.graph.roots:
        if sym not in index.graph.roots:
            index.graph.add_root(sym)
    for child, edge in local.graph.edges.items():
        if child not in index.graph.edges:
            index.graph.edges[child] = edge
            index.mounted_routers.add(child)
    for f, var in local.module_exports.items():
        index.module_exports.setdefault(f, var)
    for k, v in local.require_bindings.items():
        index.require_bindings.setdefault(k, v)
    for f, text in local.file_texts.items():
        index.file_texts.setdefault(f, text)


def extract_express(
    text: str,
    *,
    file_path: str = "__local__",
    route_index: ExpressRouteIndex | None = None,
) -> tuple[list[ExpressRoute], list[ExpressMiddleware], dict[str, str]]:
    """Return routes, middleware, and resolved mount prefixes (var→prefix).

    When ``route_index`` is provided (project pre-pass), cross-file
    ``app.use(prefix, require('./…'))`` mounts join only on unique literal
    resolution. Otherwise in-file facts alone are used.
    """
    project_scoped = route_index is not None
    local = _local_express_index(text, file_path)
    if route_index is None:
        index = local
    else:
        index = route_index
        _merge_local_into_index(index, local)

    graph = index.graph
    local_known = {var for (f, var) in index.known_routers if f == file_path}
    # Identifiers known in this file for middleware-vs-mount discrimination
    known = set(local_known)
    for (f, local_var), _target in index.require_bindings.items():
        if f == file_path:
            known.add(local_var)

    # Public mount map: child var → resolved prefix (this file's children)
    mounts: dict[str, str] = {}
    for child, edge in graph.edges.items():
        if not isinstance(child, tuple) or len(child) != 2:
            continue
        child_file, child_var = child
        if child_file != file_path:
            continue
        res = full_route_path(graph, child, "")
        mounts[child_var] = res.path

    middleware: list[ExpressMiddleware] = []
    order = 0
    for m in MW_USE_RE.finditer(text):
        call = m.group("call").strip()
        var = m.group("var")
        args = _split_call_args(call)
        mount_path: str | None = None
        mw_args = args

        if args and _STRING_LIT_RE.match(args[0].strip()):
            mount_path = _STRING_LIT_RE.match(args[0].strip()).group("body")  # type: ignore[union-attr]
            mw_args = args[1:]
            # Router mount — already in graph; skip as middleware.
            if len(mw_args) == 1:
                ident = _ident_or_none(mw_args[0])
                if ident in known:
                    continue
                if re.match(r"^require\s*\(", mw_args[0].strip()):
                    continue
        elif len(args) == 1 and _ident_or_none(args[0]) in known:
            continue
        elif len(args) == 1 and re.match(r"^require\s*\(", args[0].strip()):
            continue

        for arg in mw_args:
            name = _mw_name(arg)
            if not name:
                continue
            middleware.append(ExpressMiddleware(
                router_var=var,
                name=name,
                order=order,
                line=_line_of(text, m.start()),
                is_auth=_looks_auth(name) or _looks_auth(arg),
                mount_path=mount_path,
            ))
            order += 1

    routes: list[ExpressRoute] = []
    seen: set[tuple[str, str, int, str]] = set()

    def _add_route(
        var: str,
        method: str,
        path: str,
        line: int,
        handler: str,
        path_ok: bool,
        path_note: str | None,
        route_mw: list[str],
    ) -> None:
        method = method.upper()
        if method == "USE":
            return
        notes: list[str] = []
        assumed = False
        path_resolved: bool | None = None
        prefix_chain: list[str] = []

        if handler == "inline":
            handler = f"inline_L{line}"

        # Regex paths: report the token only — never invent a joined URL.
        if path.startswith("<regex:"):
            full = path
            assumed = True
            path_resolved = False
            if path_note:
                notes.append(path_note)
        else:
            sym = (file_path, var)
            res = full_route_path(graph, sym, path)
            full = res.path or "/"
            if not full.startswith("/") and not full.startswith("<"):
                full = "/" + full
            path_resolved = res.resolved
            prefix_chain = chain_as_strings(res.chain)
            if res.note:
                notes.append(res.note)
            if not res.resolved:
                assumed = True
            # Project-scoped: unmounted router that is not an express() root
            # → assumed (mount lives elsewhere / never found).
            if (
                project_scoped
                and sym not in graph.roots
                and sym not in graph.edges
                and sym not in index.mounted_routers
                and sym in index.known_routers
            ):
                assumed = True
                path_resolved = False
                notes.append(
                    "This router was not found in any app.use(...) mount in the "
                    "files scanned, so the mount prefix is unknown and the path "
                    "shown is router-local."
                )
                prefix_chain = prefix_chain or [f"{file_path}::{var}"]
            elif (
                not project_scoped
                and sym not in graph.roots
                and sym not in graph.edges
                and var in local_known
            ):
                # In-file only: unmounted router → assumed (existing honesty).
                assumed = True
                path_resolved = False
                notes.append(
                    "Router variable not mounted (or not declared) in this file; "
                    "path prefix may be incomplete."
                )

        if not path_ok:
            assumed = True
            path_resolved = False
            if path_note:
                notes.append(path_note)

        # Hard rule: pathResolved False ⇒ assumed True
        if path_resolved is False:
            assumed = True

        key = (method, full, line, handler)
        if key in seen:
            return
        seen.add(key)
        routes.append(ExpressRoute(
            method=method,
            path=full,
            router_var=var,
            line=line,
            assumed=assumed,
            handler=handler,
            note=" ".join(n for n in notes if n) or None,
            route_middleware=route_mw,
            path_resolved=path_resolved,
            prefix_chain=prefix_chain,
        ))

    # Chained .route(path).get().post()
    for m in ROUTE_CHAIN_RE.finditer(text):
        var = m.group("var")
        path = m.group("path")
        line = _line_of(text, m.start())
        for cm in CHAIN_METHOD_RE.finditer(m.group("chain")):
            handler = cm.group("handler") or f"inline_L{line}"
            if handler in ("async", "function"):
                handler = f"inline_L{line}"
            _add_route(var, cm.group("method"), path, line, handler, True, None, [])

    # METHOD(path, …) including arrays and regex
    for m in ROUTE_METHOD_RE.finditer(text):
        method = m.group("method")
        var = m.group("var")
        parsed = _extract_call_args(text, m.end())
        if parsed is None:
            continue
        args_src, _ = parsed
        args = _split_call_args(args_src)
        if not args:
            continue
        path_entries = _parse_path_arg(args[0])
        if not path_entries:
            # Non-literal / non-regex path — skip rather than invent.
            continue
        handler, route_mw = _parse_handler_chain(args[1:])
        line = _line_of(text, m.start())
        if handler == "inline":
            handler = f"inline_L{line}"
        for path, path_ok, path_note in path_entries:
            _add_route(var, method, path, line, handler, path_ok, path_note, route_mw)

    return routes, middleware, mounts


def tree_sitter_decl_names_or_fallback(text: str) -> list[str] | None:
    """Optional tree-sitter plug-in point for Express/JS declarations.

    Returns ``None`` when the feature flag is off, the substrate is
    missing, or the parse is catastrophic — callers must keep the regex
    path. Successful lists are proven clean-node names only; they are
    **not** consumed by record builders yet (middleware arity parity
    deferred). Never invents mounts or route edges.
    """
    from .tree_sitter_probe import probe_js_declarations

    decls = probe_js_declarations(text)
    if decls is None:
        return None
    return [d.name for d in decls]
