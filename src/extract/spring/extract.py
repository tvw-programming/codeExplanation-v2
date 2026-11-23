"""Spring Boot annotation extraction (regex). DI is by type — never imports-as-inject."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


CLASS_RE = re.compile(
    r"@(?P<stereo>RestController|Controller|Service|Repository|Component)\b[^\n]*\n"
    r"(?:@[^\n]+\n)*"
    r"(?:public\s+|protected\s+|private\s+)?(?:final\s+)?class\s+(?P<name>\w+)",
)
CLASS_MAPPING_RE = re.compile(
    r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?(?P<quote>[\"'])(?P<path>[^\"']*)(?P=quote)",
)
# Flexible method mapping: capture annotation name + optional paren body.
METHOD_MAPPING_RE = re.compile(
    r"@(?P<ann>GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\b"
    r"(?:\s*\((?P<body>[^)]*)\))?",
)
METHOD_RE = re.compile(
    r"(?:public|protected|private)\s+(?:static\s+)?[\w.<>,\[\]\s]+\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
)
CTOR_RE = re.compile(
    r"(?:public|protected|private)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*\{",
)
AUTOWIRED_FIELD_RE = re.compile(
    r"@Autowired\b[^;]*?\b(?P<type>\w+)\s+(?P<field>\w+)\s*;",
    re.DOTALL,
)
PRE_AUTHORIZE_RE = re.compile(r"@PreAuthorize\b|@Secured\b")
REQUIRED_ARGS_RE = re.compile(r"@RequiredArgsConstructor\b")
FINAL_FIELD_RE = re.compile(
    r"(?:private|protected|public)\s+final\s+(?P<type>[\w.]+)(?:<[^;]+>)?\s+(?P<field>\w+)\s*;"
)
PATH_IN_BODY_RE = re.compile(
    r"(?:(?:value|path)\s*=\s*)?(?P<quote>[\"'])(?P<path>[^\"']*)(?P=quote)"
)
REQUEST_METHOD_RE = re.compile(r"RequestMethod\.(?P<m>GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)")


@dataclass
class SpringType:
    name: str
    stereotype: str
    class_path: str
    line: int
    methods: list[dict] = field(default_factory=list)
    injectees: list[dict] = field(default_factory=list)


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


def _path_from_mapping_body(body: str | None) -> str:
    if not body:
        return ""
    # Prefer explicit value=/path=; else first quoted string that looks like a path.
    for m in PATH_IN_BODY_RE.finditer(body):
        # Skip media-type-looking strings when value= absent and key is produces/consumes —
        # simple heuristic: take first quote that starts with / or is empty or looks like a path segment.
        path = m.group("path")
        before = body[: m.start()].rstrip()
        if before.endswith("produces") or before.endswith("consumes") or before.endswith("headers"):
            continue
        return path
    return ""


def _http_method(ann: str, body: str | None) -> str:
    mapped = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
    }.get(ann)
    if mapped:
        return mapped
    if body:
        rm = REQUEST_METHOD_RE.search(body)
        if rm:
            return rm.group("m")
    return "GET"


def _join_paths(class_path: str, path: str) -> str:
    full = (class_path.rstrip("/") + "/" + path.lstrip("/")).replace("//", "/")
    if not full.startswith("/"):
        full = "/" + full if full else class_path or "/"
    return full


def extract_spring(text: str) -> tuple[list[SpringType], list[SpringRoute]]:
    types: list[SpringType] = []
    routes: list[SpringRoute] = []

    for m in CLASS_RE.finditer(text):
        name = m.group("name")
        stereo = m.group("stereo")
        line = _line_of(text, m.start())
        window = text[max(0, m.start() - 400):m.end()]
        cm = list(CLASS_MAPPING_RE.finditer(window))
        class_path = cm[-1].group("path") if cm else ""
        has_required_args = bool(REQUIRED_ARGS_RE.search(window))

        body_start = text.find("{", m.end())
        if body_start < 0:
            body = ""
            body_offset = m.end()
        else:
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
            body = text[body_start:i + 1]
            body_offset = body_start

        injectees: list[dict] = []
        for ctor in CTOR_RE.finditer(body):
            if ctor.group("name") != name:
                continue
            for typ, field in _split_params(ctor.group("params")):
                if typ[0].isupper():
                    injectees.append({"type": typ, "field": field, "via": "constructor", "assumed": False})
        for af in AUTOWIRED_FIELD_RE.finditer(body):
            injectees.append({
                "type": af.group("type"),
                "field": af.group("field"),
                "via": "field",
                "assumed": False,
            })
        # Lombok: @RequiredArgsConstructor → private final fields are inject points.
        if has_required_args and not injectees:
            for ff in FINAL_FIELD_RE.finditer(body):
                typ = ff.group("type").split(".")[-1]
                if typ and typ[0].isupper():
                    injectees.append({
                        "type": typ,
                        "field": ff.group("field"),
                        "via": "lombok",
                        "assumed": False,
                    })

        methods: list[dict] = []
        for mm in METHOD_MAPPING_RE.finditer(body):
            ann = mm.group("ann")
            map_body = mm.group("body")
            path = _path_from_mapping_body(map_body)
            method = _http_method(ann, map_body)
            full = _join_paths(class_path, path)
            after = body[mm.end():mm.end() + 200]
            sig = METHOD_RE.search(after)
            handler = sig.group("name") if sig else "handler"
            line_m = _line_of(text, body_offset + mm.start())
            has_sec = bool(PRE_AUTHORIZE_RE.search(body[max(0, mm.start() - 120):mm.end() + 80]))
            methods.append({"name": handler, "method": method, "path": full, "line": line_m})
            routes.append(SpringRoute(
                method=method,
                path=full or "/",
                handler=handler,
                controller=name,
                line=line_m,
                assumed=bool(class_path == "" and path == ""),
                has_security=has_sec,
            ))

        types.append(SpringType(
            name=name,
            stereotype=stereo,
            class_path=class_path,
            line=line,
            methods=methods,
            injectees=injectees,
        ))

    return types, routes
