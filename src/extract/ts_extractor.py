"""Phase 3 — TypeScript / React (and by extension JS/Angular-shaped)
extraction. Regex-based static analysis — see common.py's module
docstring for why, and the accuracy rule this follows (mark assumed
rather than guess).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .common import trim_snippet, CodeSnippet

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


def _find_matching_brace_end_line(text: str, open_brace_offset: int) -> int:
    """Given the offset of an opening `{`, find the line of its matching
    close. Naive brace counting — doesn't understand strings/comments
    containing braces, which is a known limitation of a regex-based
    extractor (flagged in the plan, not hidden)."""
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


def extract_functions(text: str) -> list[ExtractedFunction]:
    lines = text.splitlines()
    functions: list[ExtractedFunction] = []
    seen_spans: set[tuple[int, int]] = set()

    for pattern in (FUNCTION_DECL_RE, ARROW_CONST_RE):
        for m in pattern.finditer(text):
            name = m.group("name")
            params = m.group("params") or ""
            start_line = _line_of(text, m.start())
            end_line = _find_matching_brace_end_line(text, m.end() - 1)
            if (start_line, end_line) in seen_spans:
                continue
            seen_spans.add((start_line, end_line))
            signature = lines[start_line - 1].strip()
            is_handler = _looks_like_handler(name)
            snippet = trim_snippet(lines, start_line, end_line)
            functions.append(ExtractedFunction(
                name=name,
                signature=signature,
                line_range=(start_line, end_line),
                snippet=snippet,
                is_event_handler=is_handler,
                event_type=_event_type_for(name) if is_handler else None,
            ))
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
    for m in JSX_INLINE_HANDLER_RE.finditer(text):
        line = _line_of(text, m.start())
        if line in named_handler_lines:
            continue
        event = m.group("event")
        handlers.append(ExtractedEventHandler(
            name=f"inline_on{event}_L{line}",
            signature=text.splitlines()[line - 1].strip(),
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
