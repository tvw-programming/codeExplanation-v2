"""Spring Boot annotation extraction (regex). DI is by type — never imports-as-inject.

Cross-file route mounts onto shared PrefixGraph are deferred: Spring has no
safe literal analogue of Express ``app.use`` / Flask ``register_blueprint`` /
FastAPI ``include_router``. Class-level ``@RequestMapping`` is in-file
containment only. Servlet ``context-path`` lives in config, not code.
``WebMvcConfigurer`` / bean ``RouterFunction`` wiring would require inventing
bean edges — never do that here.

Optional tree-sitter probe (``CEV_TREE_SITTER=1``): Java type/method/
annotation *names* via ``tree_sitter_probe``. Records stay regex; v23
``@Import`` / ``@ComponentScan`` / typed-Impl invent skip-locks unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Stereotype on class OR interface (Spring Data repos are interfaces).
TYPE_RE = re.compile(
    r"@(?P<stereo>RestController|Controller|Service|Repository|Component)\b[^\n]*\n"
    r"(?:@[^\n]+\n)*"
    r"(?:public\s+|protected\s+|private\s+)?(?:final\s+)?"
    r"(?P<kind>class|interface)\s+(?P<name>\w+)",
)
# Spring Data repository interface without a stereotype annotation.
SPRING_DATA_IFACE_RE = re.compile(
    r"(?:public\s+|protected\s+|private\s+)?interface\s+(?P<name>\w+)\s+"
    r"extends\s+[^{]*?\b(?P<base>JpaRepository|CrudRepository|"
    r"PagingAndSortingRepository|ListCrudRepository|ListPagingAndSortingRepository|"
    r"ReactiveCrudRepository|CoroutineCrudRepository|Repository)\s*<",
)
CLASS_MAPPING_RE = re.compile(
    r"@RequestMapping\s*\((?P<body>[^)]*)\)",
)
# Flexible method mapping: capture annotation name + optional paren body.
METHOD_MAPPING_RE = re.compile(
    r"@(?P<ann>GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\b"
    r"(?:\s*\((?P<body>[^)]*)\))?",
)
METHOD_RE = re.compile(
    r"(?:public|protected|private)\s+(?:static\s+)?[\w.<>,\[\]\s]+\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
)
# Access modifier optional — Spring injects package-private constructors too.
CTOR_RE = re.compile(
    r"(?:(?:public|protected|private)\s+)?(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*\{",
)
AUTOWIRED_FIELD_RE = re.compile(
    r"@(?:Autowired|Inject)\b[^;]*?\b(?P<type>\w+)\s+(?P<field>\w+)\s*;",
    re.DOTALL,
)
AUTOWIRED_SETTER_RE = re.compile(
    r"@(?:Autowired|Inject)\b\s*"
    r"(?:public|protected|private)\s+void\s+(?P<setter>set\w+)\s*\(\s*"
    r"(?P<type>[\w.]+)(?:<[^>]*>)?\s+(?P<field>\w+)\s*\)",
    re.DOTALL,
)
CTOR_INJECT_ANN_RE = re.compile(r"@(?:Autowired|Inject)\b")
PRE_AUTHORIZE_RE = re.compile(r"@PreAuthorize\b|@Secured\b")
REQUIRED_ARGS_RE = re.compile(r"@RequiredArgsConstructor\b")
FINAL_FIELD_RE = re.compile(
    r"(?:private|protected|public)\s+final\s+(?P<type>[\w.]+)(?:<[^;]+>)?\s+(?P<field>\w+)\s*;"
)
PATH_IN_BODY_RE = re.compile(
    r"(?:(?:value|path)\s*=\s*)?(?P<quote>[\"'])(?P<path>[^\"']*)(?P=quote)"
)
REQUEST_METHOD_RE = re.compile(r"RequestMethod\.(?P<m>GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)")
PLACEHOLDER_RE = re.compile(r"\$\{|\#\{")
MEDIA_KEY_RE = re.compile(r"(?:produces|consumes|headers)\s*$")


@dataclass
class SpringType:
    name: str
    stereotype: str
    class_path: str
    line: int
    methods: list[dict] = field(default_factory=list)
    injectees: list[dict] = field(default_factory=list)
    kind: str = "class"  # "class" | "interface"


@dataclass
class SpringRoute:
    method: str
    path: str
    handler: str
    controller: str
    line: int
    assumed: bool
    has_security: bool = False


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _split_params(params: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in params.split(","):
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        bits = part.split()
        if len(bits) >= 2:
            out.append((bits[-2].replace("...", ""), bits[-1]))
    return out


def _paths_from_mapping_body(body: str | None) -> list[str]:
    """All path literals from a mapping body; skip produces/consumes/headers."""
    if not body:
        return [""]
    paths: list[str] = []
    for m in PATH_IN_BODY_RE.finditer(body):
        before = body[: m.start()].rstrip()
        if MEDIA_KEY_RE.search(before):
            continue
        paths.append(m.group("path"))
    return paths or [""]


def _path_assumed(path: str) -> bool:
    """Property/SpEL placeholders are unresolved at extract time."""
    return bool(PLACEHOLDER_RE.search(path))


def _http_methods(ann: str, body: str | None) -> list[str]:
    """HTTP methods for a mapping. Bare @RequestMapping → ALL (not silent GET)."""
    mapped = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
    }.get(ann)
    if mapped:
        return [mapped]
    if body:
        found = [m.group("m") for m in REQUEST_METHOD_RE.finditer(body)]
        if found:
            # Preserve order, drop dupes.
            seen: set[str] = set()
            out: list[str] = []
            for mth in found:
                if mth not in seen:
                    seen.add(mth)
                    out.append(mth)
            return out
    # Plain @RequestMapping with no method= matches every HTTP method.
    return ["ALL"]


def _join_paths(class_path: str, path: str) -> str:
    if not class_path and not path:
        return "/"
    if not class_path:
        full = path if path.startswith("/") else f"/{path}" if path else "/"
        return full or "/"
    if not path:
        return class_path if class_path.startswith("/") else f"/{class_path}"
    full = (class_path.rstrip("/") + "/" + path.lstrip("/")).replace("//", "/")
    if not full.startswith("/"):
        full = "/" + full
    return full


def _class_paths_from_window(window: str) -> list[str]:
    """Class-level @RequestMapping path(s); empty list means no class mapping."""
    cms = list(CLASS_MAPPING_RE.finditer(window))
    if not cms:
        return []
    # Last @RequestMapping before the type declaration wins (Spring: one mapping per element).
    return [p for p in _paths_from_mapping_body(cms[-1].group("body")) if p is not None]


def _extract_body(text: str, type_end: int) -> tuple[str, int]:
    body_start = text.find("{", type_end)
    if body_start < 0:
        return "", type_end
    depth = 0
    i = body_start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return text[body_start:i + 1], body_start


def _ctor_injectees(name: str, body: str) -> list[dict]:
    """Constructor injection points. Multi-ctor without @Autowired/@Inject → assumed."""
    ctors = [c for c in CTOR_RE.finditer(body) if c.group("name") == name]
    if not ctors:
        return []

    def _ann_before(ctor_start: int) -> bool:
        window = body[max(0, ctor_start - 120):ctor_start]
        return bool(CTOR_INJECT_ANN_RE.search(window))

    annotated = [c for c in ctors if _ann_before(c.start())]
    if len(ctors) > 1 and not annotated:
        # Ambiguous: Spring picks at runtime — emit all candidates as assumed.
        chosen = ctors
        assumed = True
    elif annotated:
        chosen = annotated
        assumed = False
    else:
        # Single constructor (annotated or not) — Spring always uses it.
        chosen = ctors
        assumed = False

    injectees: list[dict] = []
    for ctor in chosen:
        for typ, field in _split_params(ctor.group("params")):
            if typ and typ[0].isupper():
                injectees.append({
                    "type": typ.split(".")[-1],
                    "field": field,
                    "via": "constructor",
                    "assumed": assumed,
                })
    return injectees


def _field_and_setter_injectees(body: str) -> list[dict]:
    injectees: list[dict] = []
    for af in AUTOWIRED_FIELD_RE.finditer(body):
        injectees.append({
            "type": af.group("type"),
            "field": af.group("field"),
            "via": "field",
            "assumed": False,
        })
    for st in AUTOWIRED_SETTER_RE.finditer(body):
        typ = st.group("type").split(".")[-1]
        injectees.append({
            "type": typ,
            "field": st.group("field"),
            "via": "setter",
            "assumed": False,
        })
    return injectees


def _lombok_injectees(window: str, body: str, existing: list[dict]) -> list[dict]:
    if not REQUIRED_ARGS_RE.search(window):
        return []
    # Only when no constructor/field injectees already found (Lombok generates the ctor).
    if existing:
        return []
    out: list[dict] = []
    for ff in FINAL_FIELD_RE.finditer(body):
        typ = ff.group("type").split(".")[-1]
        if typ and typ[0].isupper():
            out.append({
                "type": typ,
                "field": ff.group("field"),
                "via": "lombok",
                "assumed": False,
            })
    return out


def _emit_routes(
    *,
    routes: list[SpringRoute],
    methods: list[dict],
    ann: str,
    map_body: str | None,
    class_paths: list[str],
    handler: str,
    controller: str,
    line_m: int,
    has_sec: bool,
) -> None:
    http_methods = _http_methods(ann, map_body)
    method_paths = _paths_from_mapping_body(map_body)
    bases = class_paths if class_paths else [""]
    for base in bases:
        for path in method_paths:
            full = _join_paths(base, path)
            path_assumed = _path_assumed(base) or _path_assumed(path)
            # Empty class+method path with no mapping text at all → weak claim.
            empty_claim = (not base and not path and not map_body and ann == "RequestMapping")
            for method in http_methods:
                methods.append({
                    "name": handler,
                    "method": method,
                    "path": full,
                    "line": line_m,
                })
                routes.append(SpringRoute(
                    method=method,
                    path=full or "/",
                    handler=handler,
                    controller=controller,
                    line=line_m,
                    assumed=path_assumed or empty_claim,
                    has_security=has_sec,
                ))


def _append_stereotyped_type(
    text: str,
    m: re.Match[str],
    types: list[SpringType],
    routes: list[SpringRoute],
    seen: set[str],
) -> None:
    name = m.group("name")
    if name in seen:
        return
    seen.add(name)
    stereo = m.group("stereo")
    kind = m.group("kind")
    line = _line_of(text, m.start())
    window = text[max(0, m.start() - 400):m.end()]
    class_paths = _class_paths_from_window(window)
    # Record a single representative classPath (first) for the type card.
    class_path = class_paths[0] if class_paths else ""

    body, body_offset = _extract_body(text, m.end())
    injectees = _ctor_injectees(name, body)
    injectees.extend(_field_and_setter_injectees(body))
    injectees.extend(_lombok_injectees(window, body, injectees))

    methods: list[dict] = []
    if kind == "class":
        for mm in METHOD_MAPPING_RE.finditer(body):
            ann = mm.group("ann")
            map_body = mm.group("body")
            after = body[mm.end():mm.end() + 200]
            sig = METHOD_RE.search(after)
            handler = sig.group("name") if sig else "handler"
            line_m = _line_of(text, body_offset + mm.start())
            has_sec = bool(PRE_AUTHORIZE_RE.search(body[max(0, mm.start() - 120):mm.end() + 80]))
            _emit_routes(
                routes=routes,
                methods=methods,
                ann=ann,
                map_body=map_body,
                class_paths=class_paths,
                handler=handler,
                controller=name,
                line_m=line_m,
                has_sec=has_sec,
            )

    types.append(SpringType(
        name=name,
        stereotype=stereo,
        class_path=class_path,
        line=line,
        methods=methods,
        injectees=injectees,
        kind=kind,
    ))


def _append_spring_data_iface(
    text: str,
    m: re.Match[str],
    types: list[SpringType],
    seen: set[str],
) -> None:
    name = m.group("name")
    if name in seen:
        return
    seen.add(name)
    # Interface only — never invent a *Impl or SimpleJpaRepository node.
    types.append(SpringType(
        name=name,
        stereotype="Repository",
        class_path="",
        line=_line_of(text, m.start()),
        methods=[],
        injectees=[],
        kind="interface",
    ))


def extract_spring(text: str) -> tuple[list[SpringType], list[SpringRoute]]:
    types: list[SpringType] = []
    routes: list[SpringRoute] = []
    seen: set[str] = set()

    for m in TYPE_RE.finditer(text):
        _append_stereotyped_type(text, m, types, routes, seen)

    for m in SPRING_DATA_IFACE_RE.finditer(text):
        _append_spring_data_iface(text, m, types, seen)

    return types, routes


def tree_sitter_decl_names_or_fallback(text: str) -> list[str] | None:
    """Optional tree-sitter plug-in point for Java type/method names.

    Returns ``None`` when the feature flag is off, the substrate is
    missing, or the parse is catastrophic — callers must keep the regex
    path. Successful lists are proven clean-node names only; they are
    **not** consumed by ``extract_spring`` / records yet (deferred until
    EXTRACTOR_VERSION ≥ 24). Annotation names from the probe never invent
    ``@Import`` / ``@ComponentScan`` / typed ``*Impl`` edges.
    """
    from .tree_sitter_probe import probe_java_declarations

    decls = probe_java_declarations(text)
    if decls is None:
        return None
    # Prefer type/method names for the plug-in helper; annotations stay
    # available via probe_java_declarations for experiments.
    return [d.name for d in decls if d.kind != "annotation"]
