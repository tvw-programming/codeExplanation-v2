"""Go extraction facts (Fiber-aware routes/middleware).

Regex-based static analysis — see common.py's module docstring for the
scope decision. Record assembly lives in record.py.

Honesty (Fiber enrichments):
- Generics: type params on funcs/structs/interfaces are captured; no
  invented constraints beyond the literal text.
- Interfaces: method *names/signatures* only — never invent which
  concrete type satisfies an interface (no Impl edges).
- Closure middleware factories: funcs returning fiber.Handler are
  listed as factories; application sites stay assumed when only the
  definition is visible.
- All()/Add(): All → one method=ALL node; Add only when method strings
  are literals — otherwise skip (never invent verbs).
- app.Route(prefix, func(r){...}) is skipped (regex cannot scope the
  closure parameter safely).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..common import trim_snippet, CodeSnippet

IMPORT_BLOCK_RE = re.compile(r"import\s*\(\s*(?P<body>.*?)\s*\)", re.DOTALL)
IMPORT_LINE_RE = re.compile(r'"(?P<path>[^"]+)"')

STRUCT_RE = re.compile(
    r"type\s+(?P<name>\w+)(?:\s*\[(?P<typeparams>[^\]]*)\])?\s+struct\s*\{"
)

INTERFACE_RE = re.compile(
    r"type\s+(?P<name>\w+)(?:\s*\[(?P<typeparams>[^\]]*)\])?\s+interface\s*\{"
)

# Start of a named func/method — params are balanced separately so nested
# `func(T)` in the parameter list does not truncate the match.
FUNC_START_RE = re.compile(
    r"func\s+(?:\((?P<receiver>[^)]*)\)\s+)?(?P<name>\w+)"
    r"(?:\s*\[(?P<typeparams>[^\]]*)\])?\s*\("
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

# All(path, handler) — every HTTP method at the exact path (not Use prefix).
ROUTE_ALL_RE = re.compile(
    r"(?P<var>\w+)\.All\(\s*(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)\s*,\s*(?P<handler>[\w.]+)"
)

# Add([]string{"GET","POST"}, path, handler) — only string-literal methods.
# Note: must not stop at the empty `[]` of `[]string{...}`.
ROUTE_ADD_RE = re.compile(
    r"(?P<var>\w+)\.Add\(\s*"
    r"(?P<methods>\[\](?:string|any)\s*\{[^}]*\}|\[[^\]]*\])\s*,\s*"
    r"(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)\s*,\s*(?P<handler>[\w.]+)"
)

SIDE_EFFECT_PATTERNS = [
    # pgx/sql-style calls — matched against the real alumni-web repository,
    # which uses .Query/.QueryRow/.Exec/.Begin, not ORM-style .Save()/.Create().
    (re.compile(r"\.(Query|QueryRow|Exec|Begin)\("), "database_call"),
    (re.compile(r"\blog(ger)?\.\w+\("), "log"),
    (re.compile(r"\bos\.(WriteFile|Create|Remove)\("), "file_write"),
]

# Interface method line: Name(args) returns — or embedded interface name alone.
INTERFACE_METHOD_RE = re.compile(
    r"^(?P<name>\w+)\s*\((?P<params>.*)\)\s*(?P<returns>.*)$"
)
INTERFACE_EMBED_RE = re.compile(r"^(?P<name>\*?[\w.]+)(?:\s*\[.*\])?$")


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
    type_params: str | None = None


@dataclass
class ExtractedGoInterface:
    """Interface type — methods only; never which concrete type implements it."""
    name: str
    methods: list[tuple[str, str]]  # (name, signature line)
    embedded: list[str]             # embedded interface type names (not expanded)
    line_range: tuple[int, int]
    snippet: CodeSnippet
    type_params: str | None = None


@dataclass
class ExtractedGoFunction:
    name: str
    signature: str
    line_range: tuple[int, int]
    snippet: CodeSnippet
    receiver: str | None
    type_params: str | None = None
    returns: str | None = None
    returns_fiber_handler: bool = False


@dataclass
class ExtractedMiddlewareFactory:
    """A function/method that returns fiber.Handler (closure middleware idiom)."""
    name: str
    line: int
    receiver: str | None
    assumed: bool
    note: str


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


def _find_matching_paren_end(text: str, open_paren_offset: int) -> int | None:
    """Index of the ')' matching the '(' at open_paren_offset, or None."""
    depth = 0
    i = open_paren_offset
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _returns_fiber_handler(returns: str) -> bool:
    """True when the declared return clause mentions fiber.Handler."""
    return "fiber.Handler" in (returns or "")


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
        type_params = (m.group("typeparams") or "").strip() or None
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, m.end() - 1)
        body_lines = lines[start_line:end_line - 1]
        fields: list[tuple[str, str]] = []
        for raw in body_lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue
            # Named fields only — embedded types (no field name) are skipped
            # rather than inventing a name.
            fm = re.match(r"(?P<fname>\w+)\s+(?P<ftype>[\w\*\[\]\.]+)", stripped)
            if fm:
                fields.append((fm.group("fname"), fm.group("ftype")))
        snippet = trim_snippet(lines, start_line, end_line)
        structs.append(ExtractedGoStruct(
            name=name,
            fields=fields,
            line_range=(start_line, end_line),
            snippet=snippet,
            type_params=type_params,
        ))
    return structs


def extract_interfaces(text: str) -> list[ExtractedGoInterface]:
    """Interface declarations with method signatures; no Impl satisfaction edges."""
    lines = text.splitlines()
    out: list[ExtractedGoInterface] = []
    for m in INTERFACE_RE.finditer(text):
        name = m.group("name")
        type_params = (m.group("typeparams") or "").strip() or None
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, m.end() - 1)
        body_lines = lines[start_line:end_line - 1]
        methods: list[tuple[str, str]] = []
        embedded: list[str] = []
        for raw in body_lines:
            stripped = raw.strip().rstrip(";").strip()
            if not stripped or stripped.startswith("//"):
                continue
            # Strip trailing line comment.
            if "//" in stripped:
                stripped = stripped.split("//", 1)[0].strip()
            if not stripped:
                continue
            mm = INTERFACE_METHOD_RE.match(stripped)
            if mm:
                methods.append((mm.group("name"), stripped))
                continue
            em = INTERFACE_EMBED_RE.match(stripped)
            if em:
                embedded.append(em.group("name"))
                # Do not expand embedded methods — that would invent edges.
        snippet = trim_snippet(lines, start_line, end_line)
        out.append(ExtractedGoInterface(
            name=name,
            methods=methods,
            embedded=embedded,
            line_range=(start_line, end_line),
            snippet=snippet,
            type_params=type_params,
        ))
    return out


def extract_functions(text: str) -> list[ExtractedGoFunction]:
    lines = text.splitlines()
    functions: list[ExtractedGoFunction] = []
    for m in FUNC_START_RE.finditer(text):
        name = m.group("name")
        receiver = m.group("receiver")
        type_params = (m.group("typeparams") or "").strip() or None
        open_paren = m.end() - 1
        close_paren = _find_matching_paren_end(text, open_paren)
        if close_paren is None:
            continue
        rest = text[close_paren + 1:close_paren + 1 + 400]
        brace = rest.find("{")
        if brace < 0:
            continue
        returns = rest[:brace].strip() or None
        brace_offset = close_paren + 1 + brace
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, brace_offset)
        signature = lines[start_line - 1].strip()
        snippet = trim_snippet(lines, start_line, end_line)
        functions.append(ExtractedGoFunction(
            name=name,
            signature=signature,
            line_range=(start_line, end_line),
            snippet=snippet,
            receiver=receiver,
            type_params=type_params,
            returns=returns,
            returns_fiber_handler=_returns_fiber_handler(returns or ""),
        ))
    return functions


def extract_middleware_factories(text: str) -> list[ExtractedMiddlewareFactory]:
    """Funcs/methods that return fiber.Handler — the closure-middleware idiom.

    Presence of the factory is certain from the signature; *where* it is
    applied may be another file, so assumed=True and we never invent
    route attachments from the definition alone.
    """
    out: list[ExtractedMiddlewareFactory] = []
    for fn in extract_functions(text):
        if not fn.returns_fiber_handler:
            continue
        out.append(ExtractedMiddlewareFactory(
            name=fn.name,
            line=fn.line_range[0],
            receiver=fn.receiver,
            assumed=True,
            note=(
                "Returns fiber.Handler (closure middleware factory). "
                "Application via .Use / Group may be in another file; "
                "not attached to routes from this definition alone."
            ),
        ))
    return out


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


def _parse_add_method_literals(methods_expr: str) -> list[str] | None:
    """Parse Add([]string{...}) / Add([...]) method literals. None → skip."""
    inner = methods_expr.strip()
    # Prefer composite-literal body inside {...}; fall back to [ ... ].
    brace = re.search(r"\{([^}]*)\}", inner)
    if brace:
        body = brace.group(1).strip()
    elif inner.startswith("[") and inner.endswith("]"):
        body = inner[1:-1].strip()
    else:
        return None
    if not body:
        return None
    literals = re.findall(r'''(["'])(\w+)\1''', body)
    if not literals:
        return None
    rebuilt_check = body
    for quote, meth in literals:
        rebuilt_check = rebuilt_check.replace(f"{quote}{meth}{quote}", "", 1)
    rebuilt_check = re.sub(r"[\s,]", "", rebuilt_check)
    if rebuilt_check:
        return None  # identifier / expression — never invent
    return [meth.upper() for _q, meth in literals]


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

    All() emits one method=ALL node (Fiber registers every verb). Add()
    emits one node per *literal* method string; non-literal method slices
    are skipped. app.Route(...) closure groups are skipped.
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

    def _prefix_for(var: str) -> tuple[str, bool]:
        prefix = group_prefixes.get(var, "" if var in roots else None)
        prefix_assumed = prefix is None or var in unresolved_groups
        return (prefix or ""), prefix_assumed

    def _make_route(
        *,
        var: str,
        method: str,
        path_suffix: str,
        handler: str,
        offset: int,
        extra_notes: list[str] | None = None,
    ) -> ExtractedRoute:
        prefix, prefix_assumed = _prefix_for(var)
        path = prefix.rstrip("/") + path_suffix
        is_dynamic = ":" in path_suffix
        protected = _var_or_ancestor_protected(var)
        notes = list(extra_notes or [])
        if prefix_assumed:
            notes.append(
                "Route group prefix for this variable could not be resolved; "
                "path may be incomplete."
            )
        notes.append(
            "Protected status is inferred only from .Use() / Group(..., mw) calls on this router "
            "or its ancestor groups in this file, matched by an 'auth'/'jwt' substring in the call "
            "— not real call-graph analysis, and it can miss auth applied elsewhere or misread an "
            "unrelated call. Verify before relying on it."
        )
        return ExtractedRoute(
            method=method,
            path=path,
            handler=handler,
            static_or_dynamic="dynamic" if is_dynamic else "static",
            routing_library="gofiber" if uses_fiber else "unknown",
            protected=protected,
            assumed=True,
            note=" ".join(notes),
            router_var=var,
            line=_line_of(text, offset),
        )

    routes: list[ExtractedRoute] = []
    for m in ROUTE_REGISTER_RE.finditer(text):
        routes.append(_make_route(
            var=m.group("var"),
            method=m.group("method").upper(),
            path_suffix=m.group("path"),
            handler=m.group("handler"),
            offset=m.start(),
        ))

    for m in ROUTE_ALL_RE.finditer(text):
        routes.append(_make_route(
            var=m.group("var"),
            method="ALL",
            path_suffix=m.group("path"),
            handler=m.group("handler"),
            offset=m.start(),
            extra_notes=[
                "Fiber All() registers every HTTP method at this exact path; "
                "emitted as one ALL node rather than inventing per-verb edges."
            ],
        ))

    for m in ROUTE_ADD_RE.finditer(text):
        methods = _parse_add_method_literals(m.group("methods"))
        if methods is None:
            # Non-literal method list — skip rather than invent verbs.
            continue
        for method in methods:
            routes.append(_make_route(
                var=m.group("var"),
                method=method,
                path_suffix=m.group("path"),
                handler=m.group("handler"),
                offset=m.start(),
                extra_notes=[
                    "Method taken from a string literal in Add([]string{...}); "
                    "non-literal Add method slices are skipped."
                ],
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
