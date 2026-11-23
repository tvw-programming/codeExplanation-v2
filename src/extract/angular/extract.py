"""Dedicated Angular extractor — does NOT reuse React TS regexes.

Extracts @Component metadata, @Input/@Output and signal input()/output(),
class methods, template event bindings, and parent→child mounts when a
project selector index confirms a template tag usage.

Honesty: never invent mounts from unmatched custom tags or from
`imports: [...]` alone. Duplicate selectors → skip (ambiguous). Dynamic
`*ngFor` / `@for` contexts → assumed when a confirmed match exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


COMPONENT_RE = re.compile(
    r"@Component\s*\(\s*\{(?P<body>.*?)\}\s*\)\s*"
    r"(?:export\s+)?(?:default\s+)?class\s+(?P<name>\w+)",
    re.DOTALL,
)
SELECTOR_RE = re.compile(r"""selector\s*:\s*['"]([^'"]+)['"]""")
TEMPLATE_URL_RE = re.compile(r"""templateUrl\s*:\s*['"]([^'"]+)['"]""")
TEMPLATE_INLINE_RE = re.compile(r"template\s*:\s*(?P<q>`|['\"])(?P<body>.*?)(?P=q)", re.DOTALL)
INPUT_RE = re.compile(
    r"@(?:Input|input)\s*(?:\([^)]*\))?\s*(?:public\s+|protected\s+|private\s+)?(?P<name>\w+)"
)
OUTPUT_RE = re.compile(
    r"@(?:Output|output)\s*(?:\([^)]*\))?\s*(?:public\s+|protected\s+|private\s+)?(?P<name>\w+)"
)
# Signal-based APIs: user = input(...); saved = output(...); also input.required()
SIGNAL_INPUT_RE = re.compile(
    r"(?:readonly\s+)?(?P<name>\w+)\s*=\s*input(?:\.\w+)?\s*(?:<[^>]*>)?\s*\("
)
SIGNAL_OUTPUT_RE = re.compile(
    r"(?:readonly\s+)?(?P<name>\w+)\s*=\s*output(?:\.\w+)?\s*(?:<[^>]*>)?\s*\("
)
METHOD_RE = re.compile(
    r"(?:public\s+|protected\s+|private\s+|async\s+)*(?P<name>\w+)\s*\([^)]*\)\s*(?::\s*[\w<>\[\]| ]+)?\s*\{"
)
INJECT_RE = re.compile(r"(?:constructor\s*\((?P<params>[^)]*)\)|inject\s*\(\s*(?P<tok>[\w]+))")
TEMPLATE_EVENT_RE = re.compile(r"""\((?P<event>[\w.]+)\)\s*=\s*['"](?P<handler>\w+)\s*\(""")
HTTP_RE = re.compile(
    r"""this\.http\.(?P<method>get|post|put|delete|patch)\s*\(\s*['"`](?P<url>[^'"`]+)"""
)

# Opening tags in templates (element name + attrs). Closing tags ignored.
TEMPLATE_OPEN_TAG_RE = re.compile(
    r"<\s*(?P<tag>[A-Za-z][\w.-]*)(?P<attrs>(?:\s[^>]*)?)(?P<self>/?)\s*>",
)
# Input bindings on a child tag: [name]="..." or name="..." / name='...'
TEMPLATE_INPUT_BIND_RE = re.compile(
    r"""(?:\[(?P<bound>[\w.]+)\]|(?P<attr>[\w.]+))\s*=\s*(?:
          "(?P<dstr>[^"]*)"
          |
          '(?P<sstr>[^']*)'
        )
    """,
    re.VERBOSE,
)
# Skip dirs when building a project selector index.
# Checked only against path parts *relative to root* (never absolute
# prefixes like /tmp on the host).
_SKIP_DIR_NAMES = frozenset({
    "node_modules", "dist", "build", ".git", ".angular", "coverage",
    "__pycache__", ".venv", "venv", "out", ".turbo",
})

# Intrinsic HTML5 + common SVG — never treated as component mounts.
_HTML_BUILTINS = frozenset({
    "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base",
    "bdi", "bdo", "blockquote", "body", "br", "button", "canvas", "caption",
    "cite", "code", "col", "colgroup", "data", "datalist", "dd", "del",
    "details", "dfn", "dialog", "div", "dl", "dt", "em", "embed", "fieldset",
    "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "head", "header", "hgroup", "hr", "html", "i", "iframe", "img",
    "input", "ins", "kbd", "label", "legend", "li", "link", "main", "map",
    "mark", "menu", "meta", "meter", "nav", "noscript", "object", "ol",
    "optgroup", "option", "output", "p", "param", "picture", "pre", "progress",
    "q", "rp", "rt", "ruby", "s", "samp", "script", "search", "section",
    "select", "slot", "small", "source", "span", "strong", "style", "sub",
    "summary", "sup", "table", "tbody", "td", "template", "textarea", "tfoot",
    "th", "thead", "time", "title", "tr", "track", "u", "ul", "var", "video",
    "wbr",
    # SVG subset commonly seen in templates
    "svg", "path", "g", "circle", "rect", "line", "polyline", "polygon",
    "ellipse", "text", "tspan", "defs", "clippath", "mask", "use", "symbol",
    "view", "image", "foreignobject",
})

_ANGULAR_BUILTINS = frozenset({
    "ng-container", "ng-template", "ng-content", "ng-component",
    "router-outlet", "router-link",
})

_MAX_INDEX_FILES = 800


@dataclass
class AngularComponent:
    name: str
    selector: str | None
    template_url: str | None
    inputs: list[str]
    outputs: list[str]
    methods: list[dict]
    inject_tokens: list[str]
    template_events: list[dict]
    api_calls: list[dict]
    line: int
    assumed: bool = False


@dataclass
class SelectorEntry:
    """One indexable selector fragment → declaring component class."""

    key: str                 # element tag or attribute name (lowercased)
    kind: str                # "element" | "attribute"
    component: str
    file_path: str
    line: int
    raw_selector: str


@dataclass
class AngularMountProp:
    name: str
    value_kind: str          # "literal" | "expression"
    value_preview: str | None
    assumed: bool = False


@dataclass
class AngularMount:
    """Parent component → child component via confirmed selector usage."""

    parent: str
    child: str
    selector: str
    line: int
    assumed: bool
    note: str | None = None
    props: list[AngularMountProp] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _dedupe_preserve(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def extract_angular_component(text: str, template_text: str | None = None) -> AngularComponent | None:
    m = COMPONENT_RE.search(text)
    if not m:
        return None
    body = m.group("body")
    name = m.group("name")
    sel = SELECTOR_RE.search(body)
    turl = TEMPLATE_URL_RE.search(body)
    inline = TEMPLATE_INLINE_RE.search(body)
    tmpl = template_text or (inline.group("body") if inline else "")

    inputs = [x.group("name") for x in INPUT_RE.finditer(text)]
    inputs += [x.group("name") for x in SIGNAL_INPUT_RE.finditer(text)]
    outputs = [x.group("name") for x in OUTPUT_RE.finditer(text)]
    outputs += [x.group("name") for x in SIGNAL_OUTPUT_RE.finditer(text)]
    inputs = _dedupe_preserve(inputs)
    outputs = _dedupe_preserve(outputs)

    methods: list[dict] = []
    skip = {"constructor", "ngOnInit", "ngOnDestroy", "ngOnChanges"}
    for mm in METHOD_RE.finditer(text):
        n = mm.group("name")
        if n in skip or n.startswith("ng"):
            continue
        if n[0].islower() or n.startswith("on") or n.startswith("handle"):
            methods.append({"name": n, "line": _line_of(text, mm.start())})

    inject_tokens: list[str] = []
    for im in INJECT_RE.finditer(text):
        if im.group("params"):
            for part in im.group("params").split(","):
                part = part.strip()
                tm = re.search(r":\s*(\w+)", part)
                if tm:
                    inject_tokens.append(tm.group(1))
                else:
                    bits = part.split()
                    if bits:
                        inject_tokens.append(bits[0].lstrip("privateprotectedpublicreadonly"))
        if im.group("tok"):
            inject_tokens.append(im.group("tok"))

    events = [
        {"event": e.group("event"), "handler": e.group("handler"), "assumed": False}
        for e in TEMPLATE_EVENT_RE.finditer(tmpl or "")
    ]
    api_calls = [
        {
            "method": a.group("method").upper(),
            "url": a.group("url"),
            "line": _line_of(text, a.start()),
            "assumed": False,
        }
        for a in HTTP_RE.finditer(text)
    ]

    return AngularComponent(
        name=name,
        selector=sel.group(1) if sel else None,
        template_url=turl.group(1) if turl else None,
        inputs=inputs,
        outputs=outputs,
        methods=methods,
        inject_tokens=inject_tokens,
        template_events=events,
        api_calls=api_calls,
        line=_line_of(text, m.start()),
        assumed=not bool(sel),
    )


def load_template_sibling(root: Path, file_path: str, template_url: str | None) -> str | None:
    if not template_url:
        return None
    base = (root / file_path).parent
    candidate = (base / template_url).resolve()
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
# Selector index + template usage mounts
# ---------------------------------------------------------------------------

def parse_selector_fragments(raw: str) -> list[tuple[str, str]]:
    """Split a selector string into (kind, key) fragments we can index.

    Only element and attribute selectors are indexed. Class (`.x`),
    pseudo, and combinators are skipped — high invent risk.
    """
    fragments: list[tuple[str, str]] = []
    if not raw or not raw.strip():
        return fragments
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Attribute-only: [appHighlight] or [appHighlight=...]
        attr_only = re.fullmatch(r"\[([^=\]\s/]+)[^\]]*\]", part)
        if attr_only:
            fragments.append(("attribute", attr_only.group(1).lower()))
            continue
        # Class-only — skip
        if part.startswith("."):
            continue
        # Element, optionally with attrs/classes: app-foo, app-foo[type=x], app-foo.bar
        m = re.match(r"^([A-Za-z][\w.-]*)", part)
        if not m:
            continue
        tag = m.group(1).lower()
        if tag in _HTML_BUILTINS or tag in _ANGULAR_BUILTINS:
            # Host-element selectors on builtins are unusual; skip rather than invent.
            continue
        fragments.append(("element", tag))
        # Also index attribute parts on the same compound selector.
        for am in re.finditer(r"\[([^=\]\s/]+)[^\]]*\]", part):
            fragments.append(("attribute", am.group(1).lower()))
    return fragments


def build_selector_index(
    root: Path,
    *,
    max_files: int = _MAX_INDEX_FILES,
) -> dict[str, list[SelectorEntry]]:
    """Map selector key → declaring component entries across the project.

    Keys are lowercased element tags or attribute names. Duplicate
    declarations for the same key are retained so resolvers can skip
    ambiguous matches instead of inventing a winner.
    """
    root = Path(root)
    index: dict[str, list[SelectorEntry]] = {}
    scanned = 0

    for path in root.rglob("*"):
        if scanned >= max_files:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".ts", ".js", ".mts", ".cts"):
            continue
        if path.name.endswith(".d.ts"):
            continue
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            continue
        # Skip known junk / dependency trees (relative parts only)
        if any(part in _SKIP_DIR_NAMES for part in rel_path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "@Component" not in text:
            continue
        scanned += 1
        rel = str(rel_path).replace("\\", "/")
        for m in COMPONENT_RE.finditer(text):
            body = m.group("body")
            name = m.group("name")
            sel_m = SELECTOR_RE.search(body)
            if not sel_m:
                continue
            raw = sel_m.group(1).strip()
            line = _line_of(text, m.start())
            for kind, key in parse_selector_fragments(raw):
                entry = SelectorEntry(
                    key=key,
                    kind=kind,
                    component=name,
                    file_path=rel,
                    line=line,
                    raw_selector=raw,
                )
                index.setdefault(key, []).append(entry)
    return index


def _attrs_are_dynamic(attrs: str) -> bool:
    """True when this tag's own attrs carry *ngFor / *ngIf (uncertain children)."""
    return bool(re.search(r"\*(?:ngFor|ngIf)\b", attrs or "", re.I))


def _inside_control_flow_block(template: str, offset: int) -> bool:
    """True when offset sits inside an unclosed `@for` / `@if` `{ ... }` block.

    Looks only backward — later siblings must not taint earlier tags.
    """
    window_start = max(0, offset - 240)
    prefix = template[window_start:offset]
    # Find the last @for/@if before offset; require an opening `{` after it
    # whose brace depth is still > 0 at offset.
    last = None
    for m in re.finditer(r"@(?:for|if)\s*\(", prefix, re.I):
        last = m
    if last is None:
        return False
    after = prefix[last.end():]
    # Find first `{` after the control-flow header
    brace_at = after.find("{")
    if brace_at < 0:
        return False
    depth = 0
    for c in after[brace_at:]:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return False
    return depth > 0


def _parse_template_props(attrs: str) -> list[AngularMountProp]:
    props: list[AngularMountProp] = []
    if not attrs or not attrs.strip():
        return props
    for m in TEMPLATE_INPUT_BIND_RE.finditer(attrs):
        # Skip event bindings (handled as template events on the parent)
        if m.group(0).lstrip().startswith("("):
            continue
        name = m.group("bound") or m.group("attr")
        if not name:
            continue
        # Angular microsyntax / structural leftovers
        if name.startswith("*") or name in ("ngFor", "ngIf", "ngSwitch"):
            continue
        lit = m.group("dstr") if m.group("dstr") is not None else m.group("sstr")
        if m.group("bound"):
            preview = (lit or "")[:80] or None
            if re.search(r"(password|secret|token|api[_-]?key)", name, re.I):
                preview = "[redacted]"
            props.append(AngularMountProp(
                name=name,
                value_kind="expression",
                value_preview=preview,
                assumed=False,
            ))
        else:
            preview = lit
            if preview is not None and re.search(r"(password|secret|token|api[_-]?key)", name, re.I):
                preview = "[redacted]"
            props.append(AngularMountProp(
                name=name,
                value_kind="literal",
                value_preview=preview,
                assumed=False,
            ))
    return props


def _unique_component(entries: list[SelectorEntry]) -> SelectorEntry | None:
    """Return the sole component if all entries agree; else None (ambiguous → skip)."""
    names = {e.component for e in entries}
    if len(names) != 1:
        return None
    return entries[0]


def extract_template_mounts(
    parent_name: str,
    template: str,
    selector_index: dict[str, list[SelectorEntry]],
) -> list[AngularMount]:
    """Emit parent→child mounts only for template tags confirmed by the index.

    Unmatched custom tags are skipped (not invented). Attribute-selector
    matches are marked assumed (usage on arbitrary host elements is weaker
    evidence than an element selector). Dynamic list/if contexts are assumed.
    """
    if not template or not selector_index:
        return []

    mounts: list[AngularMount] = []
    seen: set[tuple[str, str, int]] = set()
    # Stack of (tag, self_dynamic) for ancestor *ngFor/*ngIf inheritance.
    open_stack: list[tuple[str, bool]] = []

    # Also walk closing tags so the stack stays accurate.
    token_re = re.compile(
        r"<\s*(?P<close>/)?(?P<tag>[A-Za-z][\w.-]*)(?P<attrs>(?:\s[^>]*)?)(?P<self>/?)\s*>"
    )

    for m in token_re.finditer(template):
        tag = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        is_close = bool(m.group("close"))
        self_closing = bool(m.group("self")) or tag in {
            "br", "hr", "img", "input", "meta", "link", "source", "track", "wbr", "area", "base", "col", "embed", "param",
        }
        line = _line_of(template, m.start())

        if is_close:
            # Pop until matching open tag (best-effort; malformed HTML → stop)
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i][0] == tag:
                    del open_stack[i:]
                    break
            continue

        ancestor_dynamic = any(d for _, d in open_stack)
        own_dynamic = _attrs_are_dynamic(attrs)
        control_flow = _inside_control_flow_block(template, m.start())
        region_dynamic = ancestor_dynamic or own_dynamic or control_flow

        # --- Element selector path ---
        if tag not in _HTML_BUILTINS and tag not in _ANGULAR_BUILTINS:
            entries = selector_index.get(tag) or []
            el_entries = [e for e in entries if e.kind == "element"] or entries
            hit = _unique_component(el_entries) if el_entries else None
            if hit is not None and hit.component != parent_name:
                assumed = region_dynamic
                notes: list[str] = []
                if assumed:
                    notes.append(
                        "Tag under *ngFor/*ngIf/@for/@if — static subset; cardinality assumed."
                    )
                key = (parent_name, hit.component, line)
                if key not in seen:
                    seen.add(key)
                    mounts.append(AngularMount(
                        parent=parent_name,
                        child=hit.component,
                        selector=hit.raw_selector,
                        line=line,
                        assumed=assumed,
                        note="; ".join(notes) if notes else None,
                        props=_parse_template_props(attrs),
                    ))

        # --- Attribute selector path (weaker evidence → always assumed) ---
        attr_names: set[str] = set()
        for am in re.finditer(r"(?:\[(?P<b>[\w.-]+)\]|(?:^|\s)(?P<a>[\w.-]+)\s*=)", attrs):
            n = (am.group("b") or am.group("a") or "").lower()
            if n and n not in ("class", "id", "style", "src", "href", "type", "name", "value"):
                attr_names.add(n)
        for am in re.finditer(r"(?:^|\s)(?P<a>[A-Za-z][\w.-]*)(?=\s|$|/)", attrs):
            n = am.group("a").lower()
            if n and n not in ("class", "id", "style"):
                attr_names.add(n)

        for aname in sorted(attr_names):
            entries = [e for e in (selector_index.get(aname) or []) if e.kind == "attribute"]
            hit = _unique_component(entries) if entries else None
            if hit is None or hit.component == parent_name:
                continue
            key = (parent_name, hit.component, line)
            if key in seen:
                continue
            seen.add(key)
            notes = [
                "Matched via attribute selector — host element may not be the component root; assumed.",
            ]
            if region_dynamic:
                notes.append("Also under structural/control-flow — cardinality assumed.")
            mounts.append(AngularMount(
                parent=parent_name,
                child=hit.component,
                selector=hit.raw_selector,
                line=line,
                assumed=True,
                note="; ".join(notes),
                props=_parse_template_props(attrs),
            ))

        if not self_closing:
            open_stack.append((tag, own_dynamic or ancestor_dynamic))

    return mounts
