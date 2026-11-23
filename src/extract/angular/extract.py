"""Dedicated Angular extractor — does NOT reuse React TS regexes.

Extracts @Component metadata, @Input/@Output and signal input()/output(),
class methods, and basic template event bindings when the template is
inline or a sibling file is provided.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
