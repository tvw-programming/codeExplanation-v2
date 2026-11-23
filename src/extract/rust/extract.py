"""Rust crate/module + Axum/Actix/Rocket route heuristics (regex).

Honesty rules (never invent edges):
- HTTP method from get/post helpers or attribute name when present.
- Handler name from ``get(handler)`` / the ``fn`` following an attr — never a
  fake placeholder when the source name is visible.
- Qualified helpers (``axum::routing::get``) count; bare Express-style
  ``.get("/path")`` does **not** (that is not Axum).
- In-file ``.nest("/prefix", router)`` composes only when the nested
  router's routes are visible in this file (let-bound or inline).
- Unresolved nest targets → no invented children.
- Literal in-file method+path → ``assumed=False``; cross-file nest remains a
  known ceiling (miss, not invent).
- Trait Impl unresolved / macros that hide routes → partial (miss, not invent).
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

ROUTE_HEAD_RE = re.compile(r"""\.route\s*\(\s*["'](?P<path>[^"']+)["']\s*,\s*""")
# get(handler) / axum::routing::post(create) — helper takes a handler, not a path.
METHOD_HANDLER_RE = re.compile(
    r"""(?:^|[^:\w])(?:[\w:]+::)?(?P<method>get|post|put|delete|patch)\s*\(\s*(?P<handler>[\w:]+)\s*"""
)

# let api = Router::new() ... ;
ROUTER_LET_RE = re.compile(
    r"""\blet\s+(?:mut\s+)?(?P<var>\w+)\s*=\s*(?P<router>Router\s*::\s*new\s*\(\s*\))(?P<body>[\s\S]*?);"""
)
# .nest("/api", api) — target is an identifier (let-bound router).
NEST_VAR_RE = re.compile(
    r"""\.nest\s*\(\s*["'](?P<prefix>[^"']+)["']\s*,\s*(?P<target>\w+)\s*\)"""
)
NEST_INLINE_HEAD_RE = re.compile(
    r"""\.nest\s*\(\s*["'](?P<prefix>[^"']+)["']\s*,\s*Router\s*::\s*new\s*\(\s*\)"""
)

# Actix / Rocket #[get("/path")] / #[post("/path")]
ATTR_METHOD_PATH_RE = re.compile(
    r"#\[(?P<method>get|post|put|delete|patch)\s*\(\s*\"(?P<path>[^\"]+)\"[^\]]*\)\s*\]",
    re.IGNORECASE,
)
# Rocket #[route(GET, "/path")]
ROCKET_ROUTE_ATTR_RE = re.compile(
    r"#\[route\s*\(\s*(?P<method>GET|POST|PUT|DELETE|PATCH)\s*,\s*\"(?P<path>[^\"]+)\"[^\]]*\)\s*\]",
    re.IGNORECASE,
)
# Actix #[route("/path", method = "GET")]
ACTIX_ROUTE_ATTR_RE = re.compile(
    r"#\[route\s*\(\s*\"(?P<path>[^\"]+)\"\s*,\s*method\s*=\s*\"(?P<method>GET|POST|PUT|DELETE|PATCH)\"[^\]]*\)\s*\]",
    re.IGNORECASE,
)

UNSAFE_RE = re.compile(r"\bunsafe\s*\{")


@dataclass
class RustFacts:
    modules: list[dict]
    uses: list[dict]
    functions: list[dict]
    routes: list[dict]
    unsafe_blocks: list[dict]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _compose_path(prefix: str, path: str) -> str:
    if not prefix:
        return path if path.startswith("/") else "/" + path
    left = prefix.rstrip("/")
    right = path if path.startswith("/") else "/" + path
    return left + right


def _closing_paren(text: str, open_paren_idx: int) -> int | None:
    """Index of ')' matching the '(' at open_paren_idx, or None if unbalanced."""
    depth = 0
    i = open_paren_idx
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        elif ch in ("'", '"'):
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return None


def _method_handlers_from_expr(expr: str) -> list[tuple[str, str]]:
    """Parse get(h).post(c) (optional path quals) → [(METHOD, handler), ...]."""
    return [
        (m.group("method").upper(), m.group("handler"))
        for m in METHOD_HANDLER_RE.finditer(expr)
    ]


def _iter_route_calls(text: str, base_offset: int = 0):
    """Yield (abs_start, path, methods_expr) for each balanced .route(...) call."""
    for m in ROUTE_HEAD_RE.finditer(text):
        # methods expr starts at m.end(); find the '(' of .route( which is before path
        # Actually ROUTE_HEAD ends after the comma following the path; methods begin at m.end().
        # The opening '(' of .route( is just before the path string — find it.
        route_open = text.rfind("(", 0, m.start() + len(".route"))
        # Safer: search backward from m.start() for the '(' that opens .route(
        head = text[m.start(): m.end()]
        local_open = head.find("(")
        if local_open < 0:
            continue
        abs_open = m.start() + local_open
        close = _closing_paren(text, abs_open)
        if close is None:
            continue
        methods_expr = text[m.end(): close]
        yield base_offset + m.start(), m.group("path"), methods_expr


def _iter_inline_nests(text: str, base_offset: int = 0):
    """Yield (abs_start, abs_end, prefix, body_text, body_abs_start) for inline nests."""
    for m in NEST_INLINE_HEAD_RE.finditer(text):
        head = text[m.start(): m.end()]
        local_open = head.find("(")
        if local_open < 0:
            continue
        abs_open = m.start() + local_open
        close = _closing_paren(text, abs_open)
        if close is None:
            continue
        new_open = text.rfind("(", m.start(), m.end())
        new_close = _closing_paren(text, new_open) if new_open >= 0 else None
        if new_close is None or new_close >= close:
            continue
        body_start = new_close + 1
        body = text[body_start: close]
        yield (
            base_offset + m.start(),
            base_offset + close + 1,
            m.group("prefix"),
            body,
            base_offset + body_start,
        )


def _routes_in_text(
    full_text: str,
    span_text: str,
    span_start: int,
    *,
    path_prefix: str = "",
) -> list[dict]:
    """Extract routes from span_text, composing inline nests; skip inventing nothing."""
    routes: list[dict] = []
    covered: list[tuple[int, int]] = []

    for abs_start, abs_end, nest_prefix, body, body_start in _iter_inline_nests(
        span_text, span_start
    ):
        covered.append((abs_start - span_start, abs_end - span_start))
        inner_prefix = _compose_path(path_prefix, nest_prefix) if path_prefix else nest_prefix
        routes.extend(
            _routes_in_text(full_text, body, body_start, path_prefix=inner_prefix)
        )

    def _covered(local_offset: int) -> bool:
        return any(a <= local_offset < b for a, b in covered)

    for abs_start, path, methods_expr in _iter_route_calls(span_text, span_start):
        local = abs_start - span_start
        if _covered(local):
            continue
        pairs = _method_handlers_from_expr(methods_expr)
        if not pairs:
            continue
        full_path = _compose_path(path_prefix, path) if path_prefix else path
        line = _line_of(full_text, abs_start)
        for method, handler in pairs:
            routes.append({
                "method": method,
                "path": full_path,
                "line": line,
                "handler": handler,
                "framework": "axum",
            })
    return routes


def _attr_handler_name(full_text: str, attr_end: int) -> str:
    """Best-effort: fn name after this attribute (and any immediate sibling attrs)."""
    window = full_text[attr_end: attr_end + 400]
    m = re.match(
        r"\s*(?:#\[[^\]]+\]\s*)*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*",
        window,
    )
    return m.group("name") if m else ""


def _attr_routes(full_text: str) -> list[dict]:
    routes: list[dict] = []
    seen_spans: set[tuple[int, str, str]] = set()

    def _add(method: str, path: str, start: int, end: int, framework: str) -> None:
        key = (start, method.upper(), path)
        if key in seen_spans:
            return
        seen_spans.add(key)
        routes.append({
            "method": method.upper(),
            "path": path,
            "line": _line_of(full_text, start),
            "handler": _attr_handler_name(full_text, end),
            "framework": framework,
        })

    for m in ATTR_METHOD_PATH_RE.finditer(full_text):
        _add(m.group("method"), m.group("path"), m.start(), m.end(), "attr_macro")
    for m in ROCKET_ROUTE_ATTR_RE.finditer(full_text):
        _add(m.group("method"), m.group("path"), m.start(), m.end(), "rocket")
    for m in ACTIX_ROUTE_ATTR_RE.finditer(full_text):
        _add(m.group("method"), m.group("path"), m.start(), m.end(), "actix")
    return routes


def extract_rust(text: str) -> RustFacts:
    modules = [{"name": m.group("name"), "line": _line_of(text, m.start())} for m in MOD_RE.finditer(text)]
    uses = [{"path": m.group("path"), "line": _line_of(text, m.start())} for m in USE_RE.finditer(text)]
    functions = [{"name": m.group("name"), "line": _line_of(text, m.start())} for m in FN_RE.finditer(text)]

    # var → (let_start, let_end, router_start) where router_start indexes Router::new()
    let_spans: dict[str, tuple[int, int, int]] = {}
    for m in ROUTER_LET_RE.finditer(text):
        let_spans[m.group("var")] = (m.start(), m.end(), m.start("router"))

    # Nest: var → prefix (in-file only). Unresolved targets invent nothing.
    nest_prefixes: dict[str, str] = {}
    for m in NEST_VAR_RE.finditer(text):
        target = m.group("target")
        if target in let_spans:
            nest_prefixes[target] = m.group("prefix")

    routes: list[dict] = []
    seen: set[tuple[str, str, int, str]] = set()

    def _emit(
        method: str,
        path: str,
        line: int,
        handler: str,
        framework: str,
        *,
        assumed: bool,
        note: str | None = None,
    ) -> None:
        key = (method, path, line, handler)
        if key in seen:
            return
        seen.add(key)
        out: dict = {
            "method": method,
            "path": path,
            "line": line,
            "handler": handler,
            "assumed": assumed,
            "framework": framework,
        }
        if note:
            out["note"] = note
        routes.append(out)

    # Routes inside let-bound routers (compose nest prefix when target is in-file).
    for var, (let_start, let_end, router_start) in let_spans.items():
        prefix = nest_prefixes.get(var, "")
        span_text = text[router_start:let_end]
        for r in _routes_in_text(text, span_text, router_start, path_prefix=prefix):
            _emit(
                r["method"], r["path"], r["line"], r["handler"], r["framework"],
                assumed=False,
            )

    # Top-level routes / inline nests not inside a let-bound span
    top_covered_from_lets = [(s, e) for (s, e, _) in let_spans.values()]

    def _in_let_span(offset: int) -> bool:
        return any(s <= offset < e for s, e in top_covered_from_lets)

    # Outermost inline nests at file scope (inner nests are handled recursively).
    all_inline = list(_iter_inline_nests(text))
    file_inline = []
    for n in all_inline:
        if _in_let_span(n[0]):
            continue
        if any(o[0] < n[0] and n[1] <= o[1] for o in all_inline):
            continue
        file_inline.append(n)
    for abs_start, abs_end, nest_prefix, body, body_start in file_inline:
        for r in _routes_in_text(text, body, body_start, path_prefix=nest_prefix):
            _emit(
                r["method"], r["path"], r["line"], r["handler"], r["framework"],
                assumed=False,
            )

    for abs_start, path, methods_expr in _iter_route_calls(text):
        if _in_let_span(abs_start):
            continue
        if any(n_start <= abs_start < n_end for n_start, n_end, _, _, _ in file_inline):
            continue
        pairs = _method_handlers_from_expr(methods_expr)
        if not pairs:
            continue
        line = _line_of(text, abs_start)
        for method, handler in pairs:
            _emit(method, path, line, handler, "axum", assumed=False)

    for r in _attr_routes(text):
        _emit(
            r["method"], r["path"], r["line"], r["handler"], r["framework"],
            assumed=False,
        )

    unsafe_blocks = [{"line": _line_of(text, m.start())} for m in UNSAFE_RE.finditer(text)]
    return RustFacts(
        modules=modules,
        uses=uses,
        functions=functions,
        routes=routes,
        unsafe_blocks=unsafe_blocks,
    )
