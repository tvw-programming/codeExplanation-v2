"""React / TypeScript (JSX) extraction facts.

Regex-based static analysis — see common.py's module docstring for why,
and the accuracy rule this follows (mark assumed rather than guess).
Record assembly lives in record.py.

Honesty enrichments (EXTRACTOR_VERSION 20):
- Brace-aware JSX prop ranges (nested ``{{ }}`` / arrows); string-aware
  component body extents.
- ``memo`` / ``forwardRef`` bind names recorded when proven at the
  declaration site — never invent mounts from unbound HOC calls.
- Hook owners use the innermost enclosing function when evidence is
  clear; file-stem fallback is ``assumed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..common import trim_snippet, CodeSnippet

IMPORT_RE = re.compile(
    r"""import\s+
        (?:type\s+)?
        (?:
            \{(?P<named>[^}]+)\}          # named imports: { a, b as c }
            |
            (?P<default>\w+)              # default import: X
            (?:\s*,\s*\{(?P<named2>[^}]+)\})?
        )
        \s+from\s+['"](?P<source>[^'"]+)['"]
    """,
    re.VERBOSE,
)

INTERFACE_RE = re.compile(
    r"export\s+interface\s+(?P<name>\w+)(?:\s+extends\s+[\w,\s]+)?\s*\{",
)

FUNCTION_DECL_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
    r"\s*(?::\s*(?P<returns>[^\{]+))?\{",
)

ARROW_CONST_RE = re.compile(
    r"(?:export\s+)?const\s+(?P<name>\w+)\s*(?::\s*[^=]+)?=\s*"
    r"(?:\w+\(\s*)?"                               # optional hook wrapper, e.g. useCallback(
    r"(?:async\s+)?\((?P<params>[^)]*)\)\s*(?::\s*[^=]+?)?=>\s*\{",
)

# Component identity under memo / forwardRef. Only proven wrappers — never
# invent a component from an unbound HOC call.
WRAPPED_CONST_FUNC_RE = re.compile(
    r"(?:export\s+)?const\s+(?P<bind>\w+)\s*(?::\s*[^=]+)?=\s*"
    r"(?P<wrappers>(?:(?:React\.)?(?:memo|forwardRef)\s*\(\s*)+)"
    r"function\s+(?P<inner>\w+)?\s*\((?P<params>[^)]*)\)\s*"
    r"(?::\s*[^\{]+)?\{",
)
WRAPPED_CONST_ARROW_RE = re.compile(
    r"(?:export\s+)?const\s+(?P<bind>\w+)\s*(?::\s*[^=]+)?=\s*"
    r"(?P<wrappers>(?:(?:React\.)?(?:memo|forwardRef)\s*\(\s*)+)"
    r"(?:async\s+)?\((?P<params>[^)]*)\)\s*(?::\s*[^=]+?)?=>\s*\{",
)
WRAPPED_DEFAULT_FUNC_RE = re.compile(
    r"export\s+default\s+"
    r"(?P<wrappers>(?:(?:React\.)?(?:memo|forwardRef)\s*\(\s*)+)"
    r"function\s+(?P<inner>\w+)\s*\((?P<params>[^)]*)\)\s*"
    r"(?::\s*[^\{]+)?\{",
)

# A JSX prop bound directly to an inline arrow/function, e.g. onClick={() => ...}.
# Captures the prop name; the handler itself is anonymous, so this is always
# marked assumed in the eventHandlers output (there is no named function to
# point at with full confidence).
JSX_INLINE_HANDLER_RE = re.compile(r"\bon(?P<event>[A-Z]\w*)=\{")

# api/axios call sites: api.get<T>('/url', ...) or axios.post(`/url/${id}`, ...)
API_CALL_RE = re.compile(
    r"""(?P<client>\bapi|\baxios)\.(?P<method>get|post|put|delete|patch)
        (?:<[^>]*>)?\(\s*
        (?P<quote>['"`])(?P<url>[^'"`]*)(?P=quote)
    """,
    re.VERBOSE,
)

BASE_URL_RE = re.compile(r"baseURL\s*:\s*['\"`](?P<base>[^'\"`]+)['\"`]")

# Handler-ish names, and inline JSX on* props.
HANDLER_NAME_RE = re.compile(r"^(handle|on)[A-Z]")
JSX_ON_PROP_RE = re.compile(r"\bon[A-Z]\w*=\{")

SIDE_EFFECT_PATTERNS = [
    (re.compile(r"\bconsole\.(log|warn|error|info)\("), "log"),
    (re.compile(r"\blocalStorage\.(setItem|removeItem|clear)\("), "local_storage_write"),
    (re.compile(r"\bsessionStorage\.(setItem|removeItem|clear)\("), "session_storage_write"),
    (re.compile(r"\bdocument\.(cookie|title)\s*="), "dom_write"),
]

# Known library names we can recognize without reading package.json, used
# only to decide WHICH imports look like frameworks/libraries vs internal
# aliases — the actual frameworkOrLibrary list is still built from the
# repo's own package.json dependencies in chunker-level code, not guessed
# here.
INTERNAL_IMPORT_PREFIXES = (".", "~", "@/")


@dataclass
class ExtractedField:
    name: str
    type: str | None = None
    description: str | None = None


@dataclass
class ExtractedDataModel:
    name: str
    fields: list[ExtractedField]
    line_range: tuple[int, int]
    snippet: CodeSnippet


@dataclass
class ExtractedFunction:
    name: str
    signature: str
    line_range: tuple[int, int]
    snippet: CodeSnippet
    is_event_handler: bool
    event_type: str | None   # "user_action" | "system_generated" | None
    wrappers: list[str] = field(default_factory=list)  # memo / forwardRef when proven


@dataclass
class ExtractedEventHandler:
    name: str
    signature: str
    event_type: str            # "user_action" | "system_generated"
    line: int
    assumed: bool               # true for an inline JSX handler with no named function
    note: str | None = None


@dataclass
class ExtractedApiCall:
    method: str
    url: str
    url_is_template: bool     # true if the URL contains ${...} -> mark assumed
    line: int


@dataclass
class ExtractedSideEffect:
    kind: str
    line: int


@dataclass
class ImportInfo:
    source: str
    names: list[str]
    is_internal: bool


def extract_imports(text: str) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for m in IMPORT_RE.finditer(text):
        source = m.group("source")
        names: list[str] = []
        if m.group("named"):
            names.extend(n.strip().split(" as ")[0].strip() for n in m.group("named").split(","))
        if m.group("default"):
            names.append(m.group("default"))
        if m.group("named2"):
            names.extend(n.strip().split(" as ")[0].strip() for n in m.group("named2").split(","))
        is_internal = source.startswith(INTERNAL_IMPORT_PREFIXES)
        imports.append(ImportInfo(source=source, names=[n for n in names if n], is_internal=is_internal))
    return imports


def extract_base_url(text: str) -> str | None:
    m = BASE_URL_RE.search(text)
    return m.group("base") if m else None


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_matching_brace_end_offset(text: str, open_brace_offset: int) -> int | None:
    """Offset of the `}` matching `{` at open_brace_offset.

    Skips braces inside string / template literals and line/block comments
    so nested JSX props like ``style={{ ... }}`` and component bodies with
    template literals do not truncate early. Returns None when unbalanced.
    """
    depth = 0
    i = open_brace_offset
    n = len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            quote = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "`":
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "`":
                    i += 1
                    break
                if text[i] == "$" and i + 1 < n and text[i + 1] == "{":
                    # Recurse into ${...}; fail closed if unbalanced.
                    inner_end = _find_matching_brace_end_offset(text, i + 1)
                    if inner_end is None:
                        return None
                    i = inner_end + 1
                    continue
                i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i = min(n, i + 2)
                continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _find_matching_brace_end_line(text: str, open_brace_offset: int) -> int:
    """Line of the matching close brace, or last line when unbalanced."""
    end = _find_matching_brace_end_offset(text, open_brace_offset)
    if end is None:
        return _line_of(text, len(text) - 1 if text else 0)
    return _line_of(text, end)


def extract_interfaces(text: str) -> list[ExtractedDataModel]:
    lines = text.splitlines()
    models: list[ExtractedDataModel] = []
    for m in INTERFACE_RE.finditer(text):
        name = m.group("name")
        start_line = _line_of(text, m.start())
        end_line = _find_matching_brace_end_line(text, m.end() - 1)
        body = "\n".join(lines[start_line:end_line - 1])  # lines strictly inside braces
        fields: list[ExtractedField] = []
        for field_line in body.splitlines():
            field_line = field_line.strip().rstrip(",;")
            fm = re.match(r"(?P<fname>\w+)\??\s*:\s*(?P<ftype>.+)", field_line)
            if fm:
                fields.append(ExtractedField(name=fm.group("fname"), type=fm.group("ftype").strip()))
        snippet = trim_snippet(lines, start_line, end_line)
        models.append(ExtractedDataModel(name=name, fields=fields, line_range=(start_line, end_line), snippet=snippet))
    return models


def _looks_like_handler(name: str) -> bool:
    return bool(HANDLER_NAME_RE.match(name))


def _event_type_for(name: str) -> str | None:
    if not _looks_like_handler(name):
        return None
    system_hints = ("effect", "mount", "success", "error", "settled", "load", "change")
    if any(h in name.lower() for h in system_hints) and not name.lower().startswith("handle"):
        return "system_generated"
    return "user_action"


def _parse_hoc_wrappers(raw: str) -> list[str]:
    """Ordered wrapper names from a `memo(forwardRef(` prefix string."""
    found = re.findall(r"(?:React\.)?(memo|forwardRef)\s*\(", raw or "")
    return list(found)


def extract_functions(text: str) -> list[ExtractedFunction]:
    lines = text.splitlines()
    functions: list[ExtractedFunction] = []
    by_span: dict[tuple[int, int], ExtractedFunction] = {}
    # Body `{` offset → function; prevents duplicate inner `function X` under memo().
    by_brace: dict[int, ExtractedFunction] = {}

    def _add(
        *,
        name: str,
        start_offset: int,
        brace_offset: int,
        wrappers: list[str] | None = None,
    ) -> None:
        start_line = _line_of(text, start_offset)
        end_line = _find_matching_brace_end_line(text, brace_offset)
        span = (start_line, end_line)
        existing = by_brace.get(brace_offset) or by_span.get(span)
        if existing is not None:
            # HOC bind name / wrappers enrich a prior inner `function X` hit.
            if wrappers:
                if not existing.wrappers:
                    existing.wrappers = list(wrappers)
                if name and name != existing.name:
                    existing.name = name
                    existing.is_event_handler = _looks_like_handler(name)
                    existing.event_type = (
                        _event_type_for(name) if existing.is_event_handler else None
                    )
            return
        signature = lines[start_line - 1].strip() if lines else name
        is_handler = _looks_like_handler(name)
        snippet = trim_snippet(lines, start_line, end_line)
        fn = ExtractedFunction(
            name=name,
            signature=signature,
            line_range=span,
            snippet=snippet,
            is_event_handler=is_handler,
            event_type=_event_type_for(name) if is_handler else None,
            wrappers=list(wrappers or []),
        )
        by_span[span] = fn
        by_brace[brace_offset] = fn
        functions.append(fn)

    # HOC-wrapped components first so the exported/bind name wins.
    for m in WRAPPED_CONST_FUNC_RE.finditer(text):
        _add(
            name=m.group("bind"),
            start_offset=m.start(),
            brace_offset=m.end() - 1,
            wrappers=_parse_hoc_wrappers(m.group("wrappers")),
        )

    for m in WRAPPED_CONST_ARROW_RE.finditer(text):
        _add(
            name=m.group("bind"),
            start_offset=m.start(),
            brace_offset=m.end() - 1,
            wrappers=_parse_hoc_wrappers(m.group("wrappers")),
        )

    for m in WRAPPED_DEFAULT_FUNC_RE.finditer(text):
        _add(
            name=m.group("inner"),
            start_offset=m.start(),
            brace_offset=m.end() - 1,
            wrappers=_parse_hoc_wrappers(m.group("wrappers")),
        )

    for pattern in (FUNCTION_DECL_RE, ARROW_CONST_RE):
        for m in pattern.finditer(text):
            _add(
                name=m.group("name"),
                start_offset=m.start(),
                brace_offset=m.end() - 1,
                wrappers=None,
            )

    return functions


def extract_api_calls(text: str) -> list[ExtractedApiCall]:
    calls: list[ExtractedApiCall] = []
    for m in API_CALL_RE.finditer(text):
        url = m.group("url")
        calls.append(ExtractedApiCall(
            method=m.group("method").upper(),
            url=url,
            url_is_template="${" in url,
            line=_line_of(text, m.start()),
        ))
    return calls


def extract_side_effects(text: str) -> list[ExtractedSideEffect]:
    effects: list[ExtractedSideEffect] = []
    for pattern, kind in SIDE_EFFECT_PATTERNS:
        for m in pattern.finditer(text):
            effects.append(ExtractedSideEffect(kind=kind, line=_line_of(text, m.start())))
    return effects


def extract_event_handlers(text: str, functions: list[ExtractedFunction]) -> list[ExtractedEventHandler]:
    """Combine two sources, per the locked "capture every handler, none
    skipped" rule:

    1. Named functions/consts whose name looks like a handler
       (handleX / onX) -> high confidence, name is real.
    2. JSX props bound directly to an inline arrow (onClick={() => ...})
       -> always marked assumed, since there is no named function to
       point at; this is a known shape regex extraction cannot resolve
       to more than "a handler exists here".
    """
    handlers: list[ExtractedEventHandler] = []
    for fn in functions:
        if fn.is_event_handler:
            handlers.append(ExtractedEventHandler(
                name=fn.name,
                signature=fn.signature,
                event_type=fn.event_type or "user_action",
                line=fn.line_range[0],
                assumed=False,
            ))

    named_handler_lines = {h.line for h in handlers}
    named_handler_names = {h.name for h in handlers}
    for m in JSX_INLINE_HANDLER_RE.finditer(text):
        line = _line_of(text, m.start())
        if line in named_handler_lines:
            continue
        # onClick={handleToggle} references a named function — not an
        # anonymous inline arrow. Skip; the named handler already covers it.
        line_text = text.splitlines()[line - 1]
        ref = re.search(r"\bon(?P<ev>[A-Z]\w*)=\{(?P<ident>[A-Za-z_]\w*)\}", line_text)
        if ref and ref.group("ident") in named_handler_names:
            continue
        event = m.group("event")
        handlers.append(ExtractedEventHandler(
            name=f"inline_on{event}_L{line}",
            signature=line_text.strip(),
            event_type="user_action",
            line=line,
            assumed=True,
            note="Inline JSX handler bound directly in markup, not a named function; "
                 "verify what it actually does by reading the line.",
        ))
    return handlers


def find_props_interface(component_name: str, models: list[ExtractedDataModel]) -> ExtractedDataModel | None:
    target = f"{component_name}Props"
    for model in models:
        if model.name == target:
            return model
    return None


# ---------------------------------------------------------------------------
# React JSX mounts / hooks / HTML sinks (visual Slice A)
# ---------------------------------------------------------------------------

# PascalCase JSX opening tags (components). Self-closing or with children.
JSX_COMPONENT_OPEN_RE = re.compile(
    r"<(?P<name>[A-Z][A-Za-z0-9.]*)(?P<attrs>(?:\s[^>]*)?)(/?)\s*>",
)

# Prop bindings: name={...} or name="..." or name='...'
JSX_PROP_RE = re.compile(
    r"""(?P<name>[A-Za-z_][\w]*)\s*=\s*(?:
          \{(?P<expr>[^{}]*)\}
          |
          "(?P<dstr>[^"]*)"
          |
          '(?P<sstr>[^']*)'
        )
    """,
    re.VERBOSE,
)

HOOK_CALL_RE = re.compile(r"\b(?P<name>use[A-Z]\w*)\s*\(")
HTML_SINK_RE = re.compile(r"\bdangerouslySetInnerHTML\b")
# Dynamic children: something.map( ... <Child
MAP_BEFORE_JSX_RE = re.compile(r"\.map\s*\(")

PROVIDER_SUFFIXES = ("Provider", "Context.Provider")


@dataclass
class JsxPropBinding:
    name: str
    value_kind: str          # "literal" | "expression" | "boolean" | "spread"
    value_preview: str | None
    assumed: bool


@dataclass
class JsxMount:
    parent: str
    child: str
    line: int
    props: list[JsxPropBinding]
    assumed: bool
    note: str | None = None


@dataclass
class JsxProvider:
    name: str
    line: int
    assumed: bool = True


@dataclass
class ExtractedHook:
    name: str
    kind: str
    line: int
    owner: str | None
    assumed: bool = False


@dataclass
class SecurityHint:
    id: str
    rule_id: str
    message: str
    line: int
    severity: str = "high"
    assumed: bool = False


def _parse_jsx_props(attrs: str) -> list[JsxPropBinding]:
    """Brace-aware prop scan — nested ``{{ }}`` / arrows keep full ranges."""
    props: list[JsxPropBinding] = []
    if not attrs or not attrs.strip():
        return props
    i = 0
    n = len(attrs)
    seen: set[str] = set()

    def _redact(name: str, preview: str | None) -> str | None:
        if preview is None:
            return None
        if re.search(r"(password|secret|token|api[_-]?key)", name, re.I):
            return "[redacted]"
        return preview[:80]

    while i < n:
        # Skip whitespace.
        while i < n and attrs[i].isspace():
            i += 1
        if i >= n:
            break
        # Spread: {...x}
        if attrs[i] == "{" and i + 1 < n and attrs.startswith("...", i + 1):
            end = _find_matching_brace_end_offset(attrs, i)
            if end is None:
                break
            if "..." not in seen:
                seen.add("...")
                props.append(JsxPropBinding(
                    name="...",
                    value_kind="spread",
                    value_preview=None,
                    assumed=True,
                ))
            i = end + 1
            continue
        m = re.match(r"([A-Za-z_][\w]*)", attrs[i:])
        if not m:
            i += 1
            continue
        name = m.group(1)
        i += m.end()
        while i < n and attrs[i].isspace():
            i += 1
        if i >= n or attrs[i] != "=":
            # Boolean prop with no value — skip (no invent).
            continue
        i += 1
        while i < n and attrs[i].isspace():
            i += 1
        if i >= n:
            break
        if name in seen:
            # Keep first binding; skip duplicates rather than invent merge.
            if attrs[i] == "{":
                end = _find_matching_brace_end_offset(attrs, i)
                i = (end + 1) if end is not None else n
            elif attrs[i] in ("'", '"'):
                q = attrs[i]
                i += 1
                while i < n and attrs[i] != q:
                    if attrs[i] == "\\":
                        i += 2
                        continue
                    i += 1
                i = min(n, i + 1)
            else:
                i += 1
            continue
        seen.add(name)
        ch = attrs[i]
        if ch == "{":
            end = _find_matching_brace_end_offset(attrs, i)
            if end is None:
                break
            expr = attrs[i + 1:end].strip()
            props.append(JsxPropBinding(
                name=name,
                value_kind="expression",
                value_preview=_redact(name, expr),
                assumed="..." in expr,
            ))
            i = end + 1
        elif ch in ("'", '"'):
            q = ch
            i += 1
            start = i
            while i < n and attrs[i] != q:
                if attrs[i] == "\\":
                    i += 2
                    continue
                i += 1
            lit = attrs[start:i]
            props.append(JsxPropBinding(
                name=name,
                value_kind="literal",
                value_preview=_redact(name, lit),
                assumed=False,
            ))
            i = min(n, i + 1)
        else:
            # Unquoted / unknown — do not invent a value.
            break
    return props


def _enclosing_functions(line: int, functions: list[ExtractedFunction]) -> list[ExtractedFunction]:
    enclosing = [
        fn for fn in functions
        if fn.line_range[0] <= line <= fn.line_range[1]
    ]
    enclosing.sort(key=lambda f: (f.line_range[1] - f.line_range[0], f.line_range[0]))
    return enclosing


def _enclosing_component(line: int, functions: list[ExtractedFunction], file_stem: str) -> str:
    """Prefer an uppercase-named function whose span contains `line`."""
    enclosing = _enclosing_functions(line, functions)
    if not enclosing:
        return file_stem
    for fn in enclosing:
        if fn.name[:1].isupper():
            return fn.name
    # Fall back to file stem for lowercase helpers that still return JSX.
    return file_stem


def _hook_owner(
    line: int,
    functions: list[ExtractedFunction],
    file_stem: str,
) -> tuple[str, bool]:
    """Return (owner, assumed). Assumed only when no enclosing function span."""
    enclosing = _enclosing_functions(line, functions)
    if not enclosing:
        return file_stem, True
    # Innermost function is clear evidence — including lowercase helpers.
    return enclosing[0].name, False


def _is_inside_map(text: str, offset: int) -> bool:
    """True when the JSX tag sits inside a nearby `.map(` call (assumed mount)."""
    window_start = max(0, offset - 200)
    prefix = text[window_start:offset]
    # Count open map( vs close ) roughly: if last `.map(` has no balancing
    # close before this tag, treat as dynamic.
    last_map = None
    for m in MAP_BEFORE_JSX_RE.finditer(prefix):
        last_map = m
    if last_map is None:
        return False
    after = prefix[last_map.end():]
    depth = 1
    for c in after:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return False
    return depth > 0


def extract_jsx_mounts(
    text: str,
    functions: list[ExtractedFunction],
    file_stem: str,
) -> tuple[list[JsxMount], list[JsxProvider]]:
    """Parent→child JSX mounts for PascalCase tags in this file.

    Dynamic `{items.map(<Child/>)}` regions are marked assumed. Intrinsic
    HTML tags (lowercase) are ignored — they are not component mounts.
    """
    mounts: list[JsxMount] = []
    providers: list[JsxProvider] = []
    seen: set[tuple[str, str, int]] = set()

    for m in JSX_COMPONENT_OPEN_RE.finditer(text):
        child = m.group("name")
        # Normalize Foo.Provider → treat as provider wrapper
        line = _line_of(text, m.start())
        parent = _enclosing_component(line, functions, file_stem)
        if child == parent:
            continue
        attrs = m.group("attrs") or ""
        assumed = _is_inside_map(text, m.start())
        note = None
        if assumed:
            note = "Mounted inside a .map(...) — static subset only; dynamic children assumed."
        props = _parse_jsx_props(attrs)
        key = (parent, child, line)
        if key in seen:
            continue
        seen.add(key)

        if child.endswith("Provider") or child.endswith(".Provider"):
            providers.append(JsxProvider(name=child, line=line, assumed=True))

        mounts.append(JsxMount(
            parent=parent,
            child=child,
            line=line,
            props=props,
            assumed=assumed,
            note=note,
        ))
    return mounts, providers


def extract_hooks(text: str, functions: list[ExtractedFunction], file_stem: str) -> list[ExtractedHook]:
    hooks: list[ExtractedHook] = []
    for m in HOOK_CALL_RE.finditer(text):
        name = m.group("name")
        line = _line_of(text, m.start())
        owner, assumed = _hook_owner(line, functions, file_stem)
        kind = name if name.startswith("use") else "other"
        hooks.append(ExtractedHook(
            name=name,
            kind=name,
            line=line,
            owner=owner,
            assumed=assumed,
        ))
    return hooks


def extract_html_sink_hints(text: str) -> list[SecurityHint]:
    hints: list[SecurityHint] = []
    for m in HTML_SINK_RE.finditer(text):
        line = _line_of(text, m.start())
        hints.append(SecurityHint(
            id=f"xss_html_sink:L{line}",
            rule_id="xss_html_sink",
            message="dangerouslySetInnerHTML sink in this file.",
            line=line,
            severity="high",
            assumed=False,
        ))
    return hints


def callback_outputs_from_mounts(mounts: list[JsxMount]) -> list[dict]:
    """Props that look like callbacks (onX / handleX) become chunk outputs."""
    outputs: list[dict] = []
    seen: set[str] = set()
    for mount in mounts:
        for prop in mount.props:
            if not re.match(r"^(on|handle)[A-Z]", prop.name):
                continue
            key = f"{mount.child}.{prop.name}"
            if key in seen:
                continue
            seen.add(key)
            outputs.append({
                "name": prop.name,
                "type": "callback",
                "target": mount.child,
                "valuePreview": prop.value_preview,
                "assumed": prop.assumed or mount.assumed,
                "line": mount.line,
            })
    return outputs
