"""Rust crate/module + Axum/Actix/Rocket route heuristics (regex).

Honesty rules (never invent edges):
- HTTP method from get/post helpers or attribute name when present.
- Handler name from ``get(handler)`` / the ``fn`` following an attr — never a
  fake placeholder when the source name is visible.
- Qualified helpers (``axum::routing::get``) count; bare Express-style
  ``.get("/path")`` does **not** (that is not Axum).
- In-file ``.nest("/prefix", router)`` composes when the nested router's
  routes are visible (let-bound or inline).
- Cross-file ``.nest("/prefix", mod::fn())`` joins via shared ``PrefixGraph``
  only on unique literal module resolution (same bar as Express require).
  ``use``-imported nest targets (``use crate::api::router; … nest(…, router())``
  or ``use crate::api; … nest(…, api::router())``) join only when the expanded
  path uniquely resolves the same way — never invent from method sets / guesses.
  Unresolved / ambiguous / external-crate targets → no invented children.
- ``pathResolved False ⇒ assumed True``.
- Trait Impl unresolved / macros that hide routes → partial (miss, not invent).

Optional tree-sitter probe (``CEV_TREE_SITTER=1``): declaration names via
``tree_sitter_probe`` / ``tree_sitter_decl_names_or_fallback``. Records stay
regex + PrefixGraph — query-backed nest/route spans deferred until macro
and trait-Impl parity tests (see feasibility matrix).
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


MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(?P<name>\w+)\s*;", re.MULTILINE)
USE_RE = re.compile(
    r"^\s*(?:pub\s+)?use\s+(?P<path>[\w:]+)(?:\s+as\s+(?P<alias>\w+))?\s*;",
    re.MULTILINE,
)
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
# .nest("/api", api::router()) / crate::api::router()
NEST_PATH_CALL_RE = re.compile(
    r"""\.nest\s*\(\s*["'](?P<prefix>[^"']+)["']\s*,\s*"""
    r"""(?P<path>(?:crate::)?[\w]+(?:::[\w]+)+)\s*\(\s*\)\s*\)"""
)
# .nest("/api", router()) — bare call; join only via unique use-import path.
NEST_USE_CALL_RE = re.compile(
    r"""\.nest\s*\(\s*["'](?P<prefix>[^"']+)["']\s*,\s*(?P<name>\w+)\s*\(\s*\)\s*\)"""
)
NEST_INLINE_HEAD_RE = re.compile(
    r"""\.nest\s*\(\s*["'](?P<prefix>[^"']+)["']\s*,\s*Router\s*::\s*new\s*\(\s*\)"""
)

# fn router(...) -> Router { ... }  (ret type must mention Router)
ROUTER_FN_HEAD_RE = re.compile(
    r"""^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>\w+)\s*"""
    r"""(?:<[^>]*>)?\s*\([^;{]*?\)\s*->\s*(?P<ret>[^{]+?)\s*\{""",
    re.MULTILINE,
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

_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", "target", "__pycache__", ".tox",
    ".pytest_cache", "dist", "build",
})
_MAX_INDEX_FILES = 400


@dataclass
class RustFacts:
    modules: list[dict]
    uses: list[dict]
    functions: list[dict]
    routes: list[dict]
    unsafe_blocks: list[dict]


@dataclass
class RustRouteIndex:
    """Project-level Axum nest mounts. Never invents joins."""

    graph: PrefixGraph = field(default_factory=PrefixGraph)
    # (rel_file, symbol) for let-bound routers and Router-returning fns
    known_routers: set[tuple[str, str]] = field(default_factory=set)
    mounted_routers: set[tuple[str, str]] = field(default_factory=set)
    # (rel_file, local_mod_name) → uniquely resolved child rel_file
    mod_files: dict[tuple[str, str], str] = field(default_factory=dict)
    file_texts: dict[str, str] = field(default_factory=dict)
    # Crate roots (rel paths of main.rs / lib.rs) for crate:: resolution
    crate_roots: list[str] = field(default_factory=list)


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


def _closing_brace(text: str, open_brace_idx: int) -> int | None:
    depth = 0
    i = open_brace_idx
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
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
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
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


def _router_fn_spans(text: str) -> dict[str, tuple[int, int]]:
    """name → (body_start, body_end) for fns whose return type mentions Router."""
    out: dict[str, tuple[int, int]] = {}
    for m in ROUTER_FN_HEAD_RE.finditer(text):
        ret = m.group("ret")
        if "Router" not in ret:
            continue
        brace = m.end() - 1
        if text[brace] != "{":
            # end() is after '{'; head regex consumes '{'
            brace = text.find("{", m.start("ret"))
            if brace < 0:
                continue
        close = _closing_brace(text, brace)
        if close is None:
            continue
        out[m.group("name")] = (brace + 1, close)
    return out


def _mod_candidates(from_file: str, mod_name: str, indexed: set[str]) -> list[str]:
    """Candidate files for ``mod name;`` declared in from_file. Unique resolve only."""
    parent = str(Path(from_file).parent).replace("\\", "/")
    if parent in (".", ""):
        base = mod_name
    else:
        base = f"{parent}/{mod_name}"
    cands: list[str] = []
    for p in (f"{base}.rs", f"{base}/mod.rs"):
        if p in indexed and p not in cands:
            cands.append(p)
    return cands


def _unique_mod_file(from_file: str, mod_name: str, indexed: set[str]) -> str | None:
    cands = _mod_candidates(from_file, mod_name, indexed)
    if len(cands) == 1:
        return cands[0]
    return None


def _find_crate_root_for(file_path: str, crate_roots: list[str]) -> str | None:
    """Pick the crate root file that best contains file_path."""
    if not crate_roots:
        return None
    # Prefer root whose directory is a prefix of file_path; longest wins.
    best: str | None = None
    best_len = -1
    for root in crate_roots:
        root_dir = str(Path(root).parent).replace("\\", "/")
        if root_dir in (".", ""):
            prefix = ""
            plen = 0
        else:
            prefix = root_dir + "/"
            plen = len(prefix)
        if file_path == root or (prefix and file_path.startswith(prefix)) or not prefix:
            if plen > best_len:
                best = root
                best_len = plen
    return best


def _collect_use_path_bindings(text: str) -> dict[str, str]:
    """Map local name → ``use`` path for simple ``use a::b::c [as alias];``.

    Conflicting bindings for the same local name are dropped (never last-wins).
    Brace-group / glob uses are out of scope (USE_RE does not match them).
    """
    bindings: dict[str, str] = {}
    conflicts: set[str] = set()
    for m in USE_RE.finditer(text):
        path = m.group("path")
        parts = [p for p in path.split("::") if p]
        if not parts:
            continue
        local = m.group("alias") or parts[-1]
        if local in conflicts:
            continue
        if local in bindings and bindings[local] != path:
            conflicts.add(local)
            bindings.pop(local, None)
            continue
        bindings[local] = path
    return bindings


def _expand_path_via_use(path: str, use_bindings: dict[str, str]) -> str | None:
    """Rewrite ``api::router`` via ``use crate::api`` → ``crate::api::router``.

    Returns None when the first segment is not a use binding (caller keeps path).
    """
    parts = [p for p in path.split("::") if p]
    if not parts or parts[0] == "crate":
        return None
    bound = use_bindings.get(parts[0])
    if bound is None:
        return None
    if len(parts) == 1:
        return bound
    return bound + "::" + "::".join(parts[1:])


def _resolve_path_call_target(
    from_file: str,
    path: str,
    index: RustRouteIndex,
    *,
    use_bindings: dict[str, str] | None = None,
) -> tuple[str, str] | None:
    """Resolve ``api::router`` / ``crate::api::router`` to unique (file, fn).

    Honesty: only via ``mod`` declarations, unique file candidates, or a
    unique ``use`` rewrite that expands to the same walk. External crates
    and ambiguous modules → None (never invent).
    """
    # Prefer literal / mod walk first; fall back to use expansion only when
    # that fails (same unique-resolve bar as Express require).
    direct = _resolve_path_call_target_raw(from_file, path, index)
    if direct is not None:
        return direct
    if use_bindings:
        expanded = _expand_path_via_use(path, use_bindings)
        if expanded and expanded != path:
            return _resolve_path_call_target_raw(from_file, expanded, index)
    return None


def _resolve_path_call_target_raw(
    from_file: str,
    path: str,
    index: RustRouteIndex,
) -> tuple[str, str] | None:
    """Resolve a fully expanded ``crate::…`` / ``mod::…`` path call target."""
    parts = [p for p in path.split("::") if p]
    if len(parts) < 2:
        return None
    indexed = set(index.file_texts)
    start_file = from_file
    if parts[0] == "crate":
        parts = parts[1:]
        if len(parts) < 2:
            return None
        crate_root = _find_crate_root_for(from_file, index.crate_roots)
        if crate_root is None:
            return None
        start_file = crate_root
    # Walk module segments except the final fn name.
    cur = start_file
    for seg in parts[:-1]:
        # Prefer declared mod in current file; fall back only when unique.
        key = (cur, seg)
        nxt = index.mod_files.get(key)
        if nxt is None:
            nxt = _unique_mod_file(cur, seg, indexed)
        if nxt is None:
            return None
        cur = nxt
    fn_name = parts[-1]
    if (cur, fn_name) not in index.known_routers:
        return None
    return (cur, fn_name)


def _scan_file_mods(rel: str, text: str, indexed: set[str]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for m in MOD_RE.finditer(text):
        name = m.group("name")
        target = _unique_mod_file(rel, name, indexed)
        if target is not None:
            out[(rel, name)] = target
    return out


def _parent_router_near_nest(
    text: str,
    nest_start: int,
    let_spans: dict[str, tuple[int, int, int]],
) -> str | None:
    """Identify which let-bound router owns this .nest call, if any."""
    for var, (let_start, let_end, _router_start) in let_spans.items():
        if let_start <= nest_start < let_end:
            return var
    return None


def build_rust_route_index(
    root: Path,
    *,
    max_files: int = _MAX_INDEX_FILES,
) -> RustRouteIndex:
    """Scan ``.rs`` files for Router symbols and cross-file ``.nest`` mounts.

    Accuracy over coverage: ambiguous ``mod`` targets and non-literal / external
    path calls are skipped — callers must assume, never invent.
    """
    root = Path(root)
    index = RustRouteIndex()
    scanned = 0
    files: list[tuple[str, str]] = []

    for path in root.rglob("*.rs"):
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
        files.append((rel, text))
        index.file_texts[rel] = text
        stem = Path(rel).name
        if stem in ("main.rs", "lib.rs"):
            index.crate_roots.append(rel)

    indexed = set(index.file_texts)

    # Pass 1: known routers (lets + Router-returning fns) and mod maps
    for rel, text in files:
        for m in ROUTER_LET_RE.finditer(text):
            index.known_routers.add((rel, m.group("var")))
        for name in _router_fn_spans(text):
            index.known_routers.add((rel, name))
        index.mod_files.update(_scan_file_mods(rel, text, indexed))

    # Pass 2: in-file + cross-file nest mounts onto PrefixGraph
    for rel, text in files:
        let_spans: dict[str, tuple[int, int, int]] = {}
        for m in ROUTER_LET_RE.finditer(text):
            let_spans[m.group("var")] = (m.start(), m.end(), m.start("router"))
            # Let-bound routers that are never nested remain roots when they
            # appear as the outermost app binding — mark all lets as candidate
            # roots; mounts override via edges.
            index.graph.add_root((rel, m.group("var")), declared_at=_line_of(text, m.start()))

        for name, (_bs, _be) in _router_fn_spans(text).items():
            # Fn routers are roots until mounted (Express-style honesty).
            index.graph.add_root((rel, name), declared_at=None)

        # Local let-target nests
        for m in NEST_VAR_RE.finditer(text):
            target = m.group("target")
            if target not in let_spans:
                continue
            parent_var = _parent_router_near_nest(text, m.start(), let_spans)
            if parent_var is None:
                # Orphan nest on anonymous Router::new() — synth root parent.
                parent_sym = (rel, f"<nest_parent@{_line_of(text, m.start())}>")
                index.graph.add_root(parent_sym, declared_at=_line_of(text, m.start()))
            else:
                parent_sym = (rel, parent_var)
            child_sym = (rel, target)
            index.graph.add_mount(
                parent_sym,
                child_sym,
                m.group("prefix"),
                declared_at=_line_of(text, m.start()),
            )
            index.mounted_routers.add(child_sym)

        use_bindings = _collect_use_path_bindings(text)

        # Cross-file path-call nests: .nest("/api", api::router())
        # (also via unique use rewrite: use crate::api; … api::router())
        for m in NEST_PATH_CALL_RE.finditer(text):
            child = _resolve_path_call_target(
                rel, m.group("path"), index, use_bindings=use_bindings,
            )
            if child is None:
                continue
            parent_var = _parent_router_near_nest(text, m.start(), let_spans)
            if parent_var is None:
                parent_sym = (rel, f"<nest_parent@{_line_of(text, m.start())}>")
                index.graph.add_root(parent_sym, declared_at=_line_of(text, m.start()))
            else:
                parent_sym = (rel, parent_var)
            index.graph.add_mount(
                parent_sym,
                child,
                m.group("prefix"),
                declared_at=_line_of(text, m.start()),
            )
            index.mounted_routers.add(child)

        # Bare use-imported call: use crate::api::router; … .nest("/api", router())
        # Skip sites already matched as path-calls (those contain `::`).
        path_call_spans = {(m.start(), m.end()) for m in NEST_PATH_CALL_RE.finditer(text)}
        for m in NEST_USE_CALL_RE.finditer(text):
            if any(s <= m.start() < e for s, e in path_call_spans):
                continue
            name = m.group("name")
            # Local let-bound routers use NEST_VAR_RE (no call parens); a bare
            # call of a let name is not a use-import join.
            if name in let_spans:
                continue
            use_path = use_bindings.get(name)
            if use_path is None:
                continue
            child = _resolve_path_call_target_raw(rel, use_path, index)
            if child is None:
                continue
            parent_var = _parent_router_near_nest(text, m.start(), let_spans)
            if parent_var is None:
                parent_sym = (rel, f"<nest_parent@{_line_of(text, m.start())}>")
                index.graph.add_root(parent_sym, declared_at=_line_of(text, m.start()))
            else:
                parent_sym = (rel, parent_var)
            index.graph.add_mount(
                parent_sym,
                child,
                m.group("prefix"),
                declared_at=_line_of(text, m.start()),
            )
            index.mounted_routers.add(child)

    return index


def extract_rust(
    text: str,
    *,
    file_path: str = "__local__",
    route_index: RustRouteIndex | None = None,
) -> RustFacts:
    """Extract Rust facts. With ``route_index``, cross-file nests compose."""
    modules = [{"name": m.group("name"), "line": _line_of(text, m.start())} for m in MOD_RE.finditer(text)]
    uses = [{"path": m.group("path"), "line": _line_of(text, m.start())} for m in USE_RE.finditer(text)]
    functions = [{"name": m.group("name"), "line": _line_of(text, m.start())} for m in FN_RE.finditer(text)]

    project_scoped = route_index is not None
    # Build / merge a local view of lets for this file.
    let_spans: dict[str, tuple[int, int, int]] = {}
    for m in ROUTER_LET_RE.finditer(text):
        let_spans[m.group("var")] = (m.start(), m.end(), m.start("router"))

    fn_spans = _router_fn_spans(text)

    if route_index is None:
        graph = PrefixGraph()
        known_local = set(let_spans) | set(fn_spans)
        mounted_local: set[str] = set()
        for var in let_spans:
            graph.add_root((file_path, var))
        for name in fn_spans:
            graph.add_root((file_path, name))
        for m in NEST_VAR_RE.finditer(text):
            target = m.group("target")
            if target not in let_spans:
                continue
            parent_var = _parent_router_near_nest(text, m.start(), let_spans)
            if parent_var is None:
                parent_sym = (file_path, f"<nest_parent@{_line_of(text, m.start())}>")
                graph.add_root(parent_sym)
            else:
                parent_sym = (file_path, parent_var)
            child_sym = (file_path, target)
            graph.add_mount(parent_sym, child_sym, m.group("prefix"), declared_at=_line_of(text, m.start()))
            mounted_local.add(target)
        known_routers = {(file_path, v) for v in known_local}
        mounted_routers = {(file_path, v) for v in mounted_local}
    else:
        graph = route_index.graph
        known_routers = route_index.known_routers
        mounted_routers = route_index.mounted_routers

    routes: list[dict] = []
    seen: set[tuple[str, str, int, str]] = set()

    def _emit_resolved(
        method: str,
        local_path: str,
        line: int,
        handler: str,
        framework: str,
        router_sym: tuple[str, str] | None,
        *,
        inline_composed: bool = False,
    ) -> None:
        notes: list[str] = []
        assumed = False
        path_resolved: bool | None = None
        prefix_chain: list[str] = []

        if inline_composed or router_sym is None:
            # Inline nest already composed the path; treat as resolved when
            # the literals were in-file (no PrefixGraph walk needed).
            full = local_path
            path_resolved = True
            assumed = False
        else:
            res = full_route_path(graph, router_sym, local_path)
            full = res.path or local_path
            if not full.startswith("/") and not full.startswith("<"):
                full = "/" + full
            path_resolved = res.resolved
            prefix_chain = chain_as_strings(res.chain)
            if res.note:
                notes.append(res.note)
            if not res.resolved:
                assumed = True
            # Project-scoped: unmounted router that is not a graph root edge
            # with resolved chain → assumed (mount lives elsewhere / never found).
            if (
                project_scoped
                and router_sym not in graph.roots
                and router_sym not in graph.edges
                and router_sym not in mounted_routers
                and router_sym in known_routers
            ):
                assumed = True
                path_resolved = False
                notes.append(
                    "This router was not found in any .nest(...) mount in the "
                    "files scanned, so the mount prefix is unknown and the path "
                    "shown is router-local."
                )
                prefix_chain = prefix_chain or [f"{router_sym[0]}::{router_sym[1]}"]
            elif (
                project_scoped
                and router_sym in known_routers
                and router_sym not in mounted_routers
                and router_sym in graph.roots
                and router_sym not in graph.edges
            ):
                # Declared as root (unmounted fn/let). Paths are router-local
                # and resolved only if this symbol really is a root app.
                # Keep resolved=True for true roots; for fn routers that are
                # only roots-by-default until mounted, mark assumed when the
                # symbol was never mounted and is not the nesting parent.
                # Honesty: unmounted child-style routers → assumed.
                # Heuristic: Router-returning fns that look like modules stay
                # assumed until mounted; top-level let apps stay resolved.
                if router_sym[1] in fn_spans and router_sym not in mounted_routers:
                    # Still a root in graph — if nothing nests it and it is a
                    # fn, Express-style: assume mount unknown.
                    # But if it's the only router in a binary main, leave be.
                    # Match Express: unmounted known router → assumed.
                    assumed = True
                    path_resolved = False
                    notes.append(
                        "This router was not found in any .nest(...) mount in the "
                        "files scanned, so the mount prefix is unknown and the path "
                        "shown is router-local."
                    )
                    prefix_chain = prefix_chain or [f"{router_sym[0]}::{router_sym[1]}"]

        if path_resolved is False:
            assumed = True

        key = (method, full, line, handler)
        if key in seen:
            return
        seen.add(key)
        out: dict = {
            "method": method,
            "path": full,
            "line": line,
            "handler": handler,
            "assumed": assumed,
            "framework": framework,
            "pathResolved": path_resolved,
            "prefixChain": prefix_chain,
        }
        if notes:
            out["note"] = " ".join(n for n in notes if n)
        routes.append(out)

    # Routes inside let-bound routers — compose via PrefixGraph (not raw prefix).
    for var, (let_start, let_end, router_start) in let_spans.items():
        span_text = text[router_start:let_end]
        # Strip nested let-target coverage: only routes belonging to this let.
        for r in _routes_in_text(text, span_text, router_start, path_prefix=""):
            _emit_resolved(
                r["method"], r["path"], r["line"], r["handler"], r["framework"],
                (file_path, var),
            )

    # Routes inside Router-returning fns (cross-file nest targets).
    for name, (body_start, body_end) in fn_spans.items():
        body = text[body_start:body_end]
        for r in _routes_in_text(text, body, body_start, path_prefix=""):
            _emit_resolved(
                r["method"], r["path"], r["line"], r["handler"], r["framework"],
                (file_path, name),
            )

    # Top-level routes / inline nests not inside a let-bound or fn span
    top_covered = [(s, e) for (s, e, _) in let_spans.values()]
    top_covered.extend((bs - 1, be + 1) for (_n, (bs, be)) in fn_spans.items())

    def _in_owned_span(offset: int) -> bool:
        return any(s <= offset < e for s, e in top_covered)

    all_inline = list(_iter_inline_nests(text))
    file_inline = []
    for n in all_inline:
        if _in_owned_span(n[0]):
            continue
        if any(o[0] < n[0] and n[1] <= o[1] for o in all_inline):
            continue
        file_inline.append(n)
    for abs_start, abs_end, nest_prefix, body, body_start in file_inline:
        for r in _routes_in_text(text, body, body_start, path_prefix=nest_prefix):
            _emit_resolved(
                r["method"], r["path"], r["line"], r["handler"], r["framework"],
                None,
                inline_composed=True,
            )

    for abs_start, path, methods_expr in _iter_route_calls(text):
        if _in_owned_span(abs_start):
            continue
        if any(n_start <= abs_start < n_end for n_start, n_end, _, _, _ in file_inline):
            continue
        pairs = _method_handlers_from_expr(methods_expr)
        if not pairs:
            continue
        line = _line_of(text, abs_start)
        for method, handler in pairs:
            _emit_resolved(method, path, line, handler, "axum", None, inline_composed=True)

    for r in _attr_routes(text):
        _emit_resolved(
            r["method"], r["path"], r["line"], r["handler"], r["framework"],
            None,
            inline_composed=True,
        )

    unsafe_blocks = [{"line": _line_of(text, m.start())} for m in UNSAFE_RE.finditer(text)]
    return RustFacts(
        modules=modules,
        uses=uses,
        functions=functions,
        routes=routes,
        unsafe_blocks=unsafe_blocks,
    )


def tree_sitter_decl_names_or_fallback(text: str) -> list[str] | None:
    """Optional tree-sitter plug-in point for Rust declarations.

    Returns ``None`` when the feature flag is off, the substrate is
    missing, or the parse is catastrophic — callers must keep the regex
    path. Successful lists are proven clean-node names only; they are
    **not** consumed by record builders yet (macros / trait Impl invent
    risk — deferred). Never invents ``.nest`` or route edges.
    """
    from .tree_sitter_probe import probe_rust_declarations

    decls = probe_rust_declarations(text)
    if decls is None:
        return None
    return [d.name for d in decls]
