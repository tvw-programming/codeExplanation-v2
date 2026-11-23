"""Express.js in-file route / middleware extraction (regex).

Honesty rules (never invent edges or full URLs):
- Compose mount prefixes only when every segment is a string literal in this file.
- Non-literal mount prefixes / regex route paths → assumed=True + note; skip when
  we cannot name a path without guessing.
- `app.use(prefix, target)` is a router mount only when `target` is a known
  Router/app binding; otherwise it is path-scoped middleware (not a mount).
- Cross-file mounts stay unresolved here (shared prefix resolver is separate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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


@dataclass
class ExpressMiddleware:
    router_var: str
    name: str
    order: int
    line: int
    is_auth: bool
    assumed: bool = True
    mount_path: str | None = None  # set for path-scoped .use('/p', fn)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _mw_name(call: str) -> str:
    call = call.strip()
    m = re.match(r"([\w.]+)", call)
    return m.group(1) if m else call[:40]


def _looks_auth(name: str) -> bool:
    return bool(re.search(r"(?i)auth|jwt|passport|session", name))


def _full_path(prefix: str, path: str) -> str:
    full = (prefix.rstrip("/") + "/" + path.lstrip("/")) if prefix else path
    if not full.startswith("/"):
        full = "/" + full
    return full or "/"


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


def _resolve_mount_prefix(
    var: str,
    mount_edges: dict[str, tuple[str, str, bool]],
    roots: set[str],
) -> tuple[str, bool, str | None]:
    """Walk child→parent mount edges. Returns (prefix, resolved, note)."""
    segments: list[str] = []
    seen: set[str] = set()
    current = var
    assumed = False
    note: str | None = None

    while current in mount_edges:
        if current in seen:
            return "".join(reversed(segments)), False, (
                f"Mount cycle involving `{current}`; path prefix may be incomplete."
            )
        seen.add(current)
        parent, prefix, lit_ok = mount_edges[current]
        if not lit_ok:
            assumed = True
            note = (
                f"Mount prefix for `{current}` is not a string literal; "
                "full URL cannot be determined statically."
            )
            # Keep walking ancestors for any literal segments we *can* prove,
            # but never invent the missing segment.
        else:
            segments.append(prefix.rstrip("/"))
        current = parent

    full = "".join(reversed(segments))
    if current not in roots and var in mount_edges:
        assumed = True
        note = note or (
            f"Mount parent chain for `{var}` does not reach an express() / "
            "Router root declared in this file; path prefix may be incomplete."
        )
    elif current not in roots and var not in mount_edges and var not in roots:
        # No mount and not a root — likely a router only used from another file.
        assumed = True
        note = (
            "Router variable not mounted (or not declared) in this file; "
            "path prefix may be incomplete."
        )
    return full, not assumed, note


def extract_express(text: str) -> tuple[list[ExpressRoute], list[ExpressMiddleware], dict[str, str]]:
    """Return routes, middleware, and resolved in-file mount prefixes (var→prefix)."""
    roots: set[str] = {m.group("var") for m in EXPRESS_APP_RE.finditer(text)}
    roots.add("app")  # conventional even when express() binding is elsewhere
    routers: set[str] = {m.group("var") for m in ROUTER_RE.finditer(text)}
    known = roots | routers

    # child_var → (parent_var, prefix_segment, literal_ok)
    mount_edges: dict[str, tuple[str, str, bool]] = {}

    for m in USE_MOUNT_LIT_RE.finditer(text):
        parent, child, prefix = m.group("parent"), m.group("child"), m.group("prefix")
        if child not in known:
            # Path-scoped middleware — handled below; not a router mount.
            continue
        mount_edges[child] = (parent, prefix, True)

    for m in USE_MOUNT_ROOT_RE.finditer(text):
        parent, child = m.group("parent"), m.group("child")
        if child not in known:
            continue
        # Prefer a more specific literal-prefix edge if already recorded.
        if child not in mount_edges:
            mount_edges[child] = (parent, "", True)

    for m in USE_MOUNT_NONLIT_RE.finditer(text):
        parent, child = m.group("parent"), m.group("child")
        prefix_expr = m.group("prefix_expr").strip()
        if child not in known:
            continue
        if _STRING_LIT_RE.match(prefix_expr):
            continue  # already handled as literal
        # Only record non-literal when we do not already have a literal edge.
        if child not in mount_edges:
            mount_edges[child] = (parent, "", False)

    resolved_prefixes: dict[str, str] = {}
    prefix_assumed: dict[str, bool] = {}
    prefix_notes: dict[str, str | None] = {}
    for var in known:
        full, ok, note = _resolve_mount_prefix(var, mount_edges, roots)
        resolved_prefixes[var] = full
        prefix_assumed[var] = not ok
        prefix_notes[var] = note

    # Public mount map: only routers that have an in-file mount edge (or root).
    mounts: dict[str, str] = {
        var: resolved_prefixes[var]
        for var in mount_edges
    }

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
            # Router mount — already in mount_edges; skip as middleware.
            if len(mw_args) == 1 and _ident_or_none(mw_args[0]) in known:
                continue
        elif len(args) == 1 and _ident_or_none(args[0]) in known:
            # parent.use(router) root mount
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
        prefix = resolved_prefixes.get(var, "")
        assumed = prefix_assumed.get(var, var not in known)
        notes: list[str] = []
        if prefix_notes.get(var):
            notes.append(prefix_notes[var] or "")
        if not path_ok:
            assumed = True
            if path_note:
                notes.append(path_note)
        if handler == "inline":
            handler = f"inline_L{line}"
        # Regex paths: report the token only — never invent a joined URL.
        if path.startswith("<regex:"):
            full = path
            assumed = True
        else:
            full = _full_path(prefix, path)
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
