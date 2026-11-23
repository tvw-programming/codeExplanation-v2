"""Go extraction facts (Fiber-aware routes/middleware).

Regex-based static analysis — see common.py's module docstring for the
scope decision. Record assembly lives in record.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..common import trim_snippet, CodeSnippet

IMPORT_BLOCK_RE = re.compile(r"import\s*\(\s*(?P<body>.*?)\s*\)", re.DOTALL)
IMPORT_LINE_RE = re.compile(r'"(?P<path>[^"]+)"')

STRUCT_RE = re.compile(r"type\s+(?P<name>\w+)\s+struct\s*\{")

FUNC_RE = re.compile(
    r"func\s+(?:\((?P<receiver>[^)]*)\)\s+)?(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
    r"\s*(?P<returns>(?:\([^)]*\)|[\w\*\[\]\.]+)?)\s*\{",
)

# Fiber route group: `v1 := app.Group("/api/v1")` or similar.
# The parent variable is captured as well as the new one: a group's full
# prefix is its own segment appended to its parent's, and `api :=
# app.Group("/api")` followed by `v1 := api.Group("/v1")` only composes
# to "/api/v1" if we know v1 came from api.
ROUTE_GROUP_RE = re.compile(
    r"(?P<var>\w+)\s*:=\s*(?P<parent>\w+)\.Group\(\s*(?P<quote>['\"])(?P<prefix>[^'\"]*)(?P=quote)"
)

# `app := fiber.New()` — the root of a prefix chain, carrying no prefix
# of its own. Matching this rather than assuming the name "app" is what
# lets a chain rooted at `srv := fiber.New()` resolve too.
FIBER_APP_RE = re.compile(r"(?P<var>\w+)\s*:=\s*fiber\.New\(")

# Fiber route registration: `v1.Get("/alumni", alumni.List)` or `app.Get(...)`.
ROUTE_REGISTER_RE = re.compile(
    r"(?P<var>\w+)\.(?P<method>Get|Post|Put|Delete|Patch|Head|Options)\(\s*"
    r"(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)\s*,\s*(?P<handler>[\w.]+)"
)

SIDE_EFFECT_PATTERNS = [
    # pgx/sql-style calls — matched against the real alumni-web repository,
    # which uses .Query/.QueryRow/.Exec/.Begin, not ORM-style .Save()/.Create().
    (re.compile(r"\.(Query|QueryRow|Exec|Begin)\("), "database_call"),
    (re.compile(r"\blog(ger)?\.\w+\("), "log"),
    (re.compile(r"\bos\.(WriteFile|Create|Remove)\("), "file_write"),
]

# Go standard library packages have no dot in their import path.
def _is_stdlib(path: str) -> bool:
    return "." not in path.split("/")[0]


@dataclass
class GoImport:
    path: str
    is_stdlib: bool
    is_internal: bool   # belongs to this repo's own module


@dataclass
class ExtractedGoStruct:
    name: str
    fields: list[tuple[str, str]]   # (name, type)
    line_range: tuple[int, int]
    snippet: CodeSnippet


@dataclass
class ExtractedGoFunction:
    name: str
    signature: str
    line_range: tuple[int, int]
    snippet: CodeSnippet
    receiver: str | None


@dataclass
class ExtractedRoute:
    method: str
    path: str                 # full path including group prefix
    handler: str
    static_or_dynamic: str     # "static" | "dynamic"
    routing_library: str
    protected: bool
    assumed: bool
    note: str | None
    router_var: str = ""       # Fiber router/group variable the route registered on
    line: int | None = None


@dataclass
class ExtractedMiddleware:
    """One .Use(...) / Group(..., mw) registration, in source order."""
    router_var: str
    name: str
    order: int
    line: int
    is_auth: bool
    is_cors: bool
    assumed: bool
    source: str  # "use" | "group"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_matching_brace_end_line(text: str, open_brace_offset: int) -> int:
    depth = 0
    i = open_brace_offset
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return _line_of(text, i)
        i += 1
    return _line_of(text, n - 1)


def extract_module_path(go_mod_text: str) -> str | None:
    m = re.search(r"^module\s+(\S+)", go_mod_text, re.MULTILINE)
    return m.group(1) if m else None


def extract_imports(text: str, module_path: str | None = None) -> list[GoImport]:
    imports: list[GoImport] = []
    block = IMPORT_BLOCK_RE.search(text)
    if block:
        for m in IMPORT_LINE_RE.finditer(block.group("body")):
            path = m.group("path")
            imports.append(GoImport(
                path=path,
                is_stdlib=_is_stdlib(path),
                is_internal=bool(module_path and path.startswith(module_path)),
            ))
    else:
        # Single-import form: import "fmt"
        for m in re.finditer(r'import\s+"([^"]+)"', text):
            path = m.group(1)
            imports.append(GoImport(path=path, is_stdlib=_is_stdlib(path),
                                     is_internal=bool(module_path and path.startswith(module_path))))
    return imports


def extract_structs(text: str) -> list[ExtractedGoStruct]:
    lines = text.splitlines()
    structs: list[ExtractedGoStruct] = []
    for m in STRUCT_RE.finditer(text):
        name = m.group("name")
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, m.end() - 1)
        body_lines = lines[start_line:end_line - 1]
        fields: list[tuple[str, str]] = []
        for raw in body_lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue
            fm = re.match(r"(?P<fname>\w+)\s+(?P<ftype>[\w\*\[\]\.]+)", stripped)
            if fm:
                fields.append((fm.group("fname"), fm.group("ftype")))
        snippet = trim_snippet(lines, start_line, end_line)
        structs.append(ExtractedGoStruct(name=name, fields=fields, line_range=(start_line, end_line), snippet=snippet))
    return structs


def extract_functions(text: str) -> list[ExtractedGoFunction]:
    lines = text.splitlines()
    functions: list[ExtractedGoFunction] = []
    for m in FUNC_RE.finditer(text):
        name = m.group("name")
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, m.end() - 1)
        signature = lines[start_line - 1].strip()
        snippet = trim_snippet(lines, start_line, end_line)
        functions.append(ExtractedGoFunction(
            name=name,
            signature=signature,
            line_range=(start_line, end_line),
            snippet=snippet,
            receiver=m.group("receiver"),
        ))
    return functions


def extract_side_effects(text: str) -> list[tuple[str, int]]:
    effects: list[tuple[str, int]] = []
    for pattern, kind in SIDE_EFFECT_PATTERNS:
        for m in pattern.finditer(text):
            effects.append((kind, _line_of(text, m.start())))
    return effects


USE_CALL_RE = re.compile(r"(?P<var>\w+)\.Use\(\s*(?P<call>[^)]*)\)")

# Group with optional trailing middleware args after the prefix string.
# e.g. api := app.Group("/api", AuthMiddleware, cors.New())
ROUTE_GROUP_WITH_MW_RE = re.compile(
    r"(?P<var>\w+)\s*:=\s*(?P<parent>\w+)\.Group\(\s*"
    r"(?P<quote>['\"])(?P<prefix>[^'\"]*)(?P=quote)"
    r"(?P<rest>\s*,\s*[^)]+)?\)"
)


def _middleware_display_name(expr: str) -> str:
    """Short label for a middleware call/arg (never invent a business title)."""
    cleaned = expr.strip()
    if not cleaned:
        return "middleware"
    # Prefer the callee identifier: package.Func(...), Func, or &Type{}
    m = re.match(r"(?P<name>[\w.]+)(?:\s*\(|$)", cleaned)
    if m:
        return m.group("name")
    return cleaned[:48]


def _split_middleware_args(call_body: str) -> list[str]:
    """Split comma-separated Use/Group middleware args, respecting nesting."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, c in enumerate(call_body):
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth = max(0, depth - 1)
        elif c == "," and depth == 0:
            part = call_body[start:i].strip()
            if part:
                parts.append(part)
            start = i + 1
    tail = call_body[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def extract_middleware(text: str) -> list[ExtractedMiddleware]:
    """Ordered middleware registrations from .Use and Group(..., mw).

    Order is file appearance order (Fiber runs Use hooks in registration
    order on that router). Auth/CORS flags are substring heuristics on the
    argument expression only — same honesty as route.protected.
    """
    events: list[tuple[int, ExtractedMiddleware]] = []
    order = 0

    for m in USE_CALL_RE.finditer(text):
        for arg in _split_middleware_args(m.group("call")):
            name = _middleware_display_name(arg)
            is_auth = bool(re.search(r"(?i)auth|jwt", arg))
            is_cors = bool(re.search(r"(?i)cors", arg))
            events.append((m.start(), ExtractedMiddleware(
                router_var=m.group("var"),
                name=name,
                order=order,
                line=_line_of(text, m.start()),
                is_auth=is_auth,
                is_cors=is_cors,
                assumed=True,
                source="use",
            )))
            order += 1

    for m in ROUTE_GROUP_WITH_MW_RE.finditer(text):
        rest = (m.group("rest") or "").lstrip().lstrip(",").strip()
        if not rest:
            continue
        for arg in _split_middleware_args(rest):
            name = _middleware_display_name(arg)
            is_auth = bool(re.search(r"(?i)auth|jwt", arg))
            is_cors = bool(re.search(r"(?i)cors", arg))
            events.append((m.start(), ExtractedMiddleware(
                router_var=m.group("var"),
                name=name,
                order=order,
                line=_line_of(text, m.start()),
                is_auth=is_auth,
                is_cors=is_cors,
                assumed=True,
                source="group",
            )))
            order += 1

    events.sort(key=lambda item: (item[0], item[1].order))
    # Re-number in stable source order after sort.
    out: list[ExtractedMiddleware] = []
    for i, (_pos, mw) in enumerate(events):
        out.append(ExtractedMiddleware(
            router_var=mw.router_var,
            name=mw.name,
            order=i,
            line=mw.line,
            is_auth=mw.is_auth,
            is_cors=mw.is_cors,
            assumed=mw.assumed,
            source=mw.source,
        ))
    return out


def middleware_chain_for_router(
    router_var: str,
    group_parents: dict[str, tuple[str, str]],
    middleware: list[ExtractedMiddleware],
    roots: set[str],
) -> list[ExtractedMiddleware]:
    """Ancestor-then-self middleware chain for a router var (registration order)."""
    chain_vars: list[str] = []
    seen: set[str] = set()
    current = router_var
    while current and current not in seen:
        seen.add(current)
        chain_vars.append(current)
        if current in group_parents:
            current = group_parents[current][0]
        elif current in roots:
            break
        else:
            break
    chain_vars.reverse()  # root → leaf
    by_var: dict[str, list[ExtractedMiddleware]] = {}
    for mw in middleware:
        by_var.setdefault(mw.router_var, []).append(mw)
    ordered: list[ExtractedMiddleware] = []
    for var in chain_vars:
        ordered.extend(sorted(by_var.get(var, []), key=lambda m: m.order))
    return ordered


def _resolve_group_prefix(
    var: str,
    group_parents: dict[str, tuple[str, str]],
    roots: set[str],
) -> tuple[str, bool]:
    """Walk a group's parent chain to its root and join the segments.

    Returns (full_prefix, fully_resolved). fully_resolved is False when
    the chain runs into a variable this file never defines — a router
    passed in as a parameter, say, where the prefix is decided at the
    call site in another file. The caller marks those paths assumed
    rather than reporting a confidently wrong URL.
    """
    segments: list[str] = []
    seen: set[str] = set()
    current = var

    while current in group_parents:
        if current in seen:  # defensive: a cycle can't happen in valid Go
            return "".join(reversed(segments)), False
        seen.add(current)
        parent, prefix = group_parents[current]
        segments.append(prefix.rstrip("/"))
        current = parent

    full = "".join(reversed(segments))
    return full, current in roots


def extract_routes(text: str, uses_fiber: bool) -> list[ExtractedRoute]:
    """Resolve Fiber route groups and registrations into full paths.

    Protection is a heuristic, and a narrow one on purpose: it looks only
    at `.Use(...)` calls made on the SAME variable as the route
    registration, and only counts a call whose argument looks
    auth-related (contains "auth" or "jwt"). It does NOT scan the whole
    file for the word "auth" — a first version of this did, and it
    produced a false positive on this exact repo: main.go's comments and
    variable names ("AUTH_MODE", "authMode") explain that auth is
    deliberately DISABLED for this dev gateway, but a whole-file
    substring match read that as evidence auth was present. Always
    marked assumed=True regardless of the result, since this is still
    file-local and not real call-graph analysis.
    """
    # var -> (parent var, this group's own prefix segment)
    group_parents: dict[str, tuple[str, str]] = {}
    for m in ROUTE_GROUP_RE.finditer(text):
        group_parents[m.group("var")] = (m.group("parent"), m.group("prefix"))

    roots = {m.group("var") for m in FIBER_APP_RE.finditer(text)}
    roots.add("app")  # the conventional name, even when fiber.New() is elsewhere

    group_prefixes: dict[str, str] = {}
    unresolved_groups: set[str] = set()
    for var in group_parents:
        full, resolved = _resolve_group_prefix(var, group_parents, roots)
        group_prefixes[var] = full
        if not resolved:
            unresolved_groups.add(var)

    all_middleware = extract_middleware(text)
    # Auth on this var OR any ancestor group/app in the chain.
    protected_vars: set[str] = set()
    for mw in all_middleware:
        if mw.is_auth:
            protected_vars.add(mw.router_var)

    def _var_or_ancestor_protected(var: str) -> bool:
        current = var
        seen: set[str] = set()
        while current and current not in seen:
            if current in protected_vars:
                return True
            seen.add(current)
            if current in group_parents:
                current = group_parents[current][0]
            else:
                break
        return False

    routes: list[ExtractedRoute] = []
    for m in ROUTE_REGISTER_RE.finditer(text):
        var = m.group("var")
        prefix = group_prefixes.get(var, "" if var in roots else None)
        # Unresolved either because the variable is unknown here, or
        # because its chain ran off into another file.
        prefix_assumed = prefix is None or var in unresolved_groups
        prefix = prefix or ""

        path = prefix.rstrip("/") + m.group("path")
        is_dynamic = ":" in m.group("path")
        protected = _var_or_ancestor_protected(var)
        notes = []
        if prefix_assumed:
            notes.append("Route group prefix for this variable could not be resolved; path may be incomplete.")
        notes.append(
            "Protected status is inferred only from .Use() / Group(..., mw) calls on this router "
            "or its ancestor groups in this file, matched by an 'auth'/'jwt' substring in the call "
            "— not real call-graph analysis, and it can miss auth applied elsewhere or misread an "
            "unrelated call. Verify before relying on it."
        )
        routes.append(ExtractedRoute(
            method=m.group("method").upper(),
            path=path,
            handler=m.group("handler"),
            static_or_dynamic="dynamic" if is_dynamic else "static",
            routing_library="gofiber" if uses_fiber else "unknown",
            protected=protected,
            assumed=True,
            note=" ".join(notes),
            router_var=var,
            line=_line_of(text, m.start()),
        ))
    return routes


def extract_route_groups(text: str) -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Return (group_parents var→(parent, prefix), fiber app root vars)."""
    group_parents: dict[str, tuple[str, str]] = {}
    for m in ROUTE_GROUP_RE.finditer(text):
        group_parents[m.group("var")] = (m.group("parent"), m.group("prefix"))
    roots = {m.group("var") for m in FIBER_APP_RE.finditer(text)}
    roots.add("app")
    return group_parents, roots
