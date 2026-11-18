"""Phase 3 — the extra per-function facts the narrator needs in order to
say something useful about a function instead of "the X function runs
next".

Everything here is read off the source, never inferred about intent:

  - the function's own leading doc comment, which is the author's
    description in their own words and by far the best thing available
    to say about what a function is for;
  - whether it is exported, which is what "called from outside this
    file" rests on;
  - which other functions in the same chunk call it, and which it
    calls, giving a real answer to "who uses this";
  - what happens inside its own lines — errors raised, React hooks,
    API calls, side effects — which is what "why it matters" rests on.

Anything not found is simply absent. The narrator hedges or stays
quiet rather than inventing a purpose for a function, which is the
same stance the rest of the extraction takes.

Doc comments go through the same redact_secrets() choke point as code
snippets: a comment can carry a credential just as a line of code can,
and here it would be spoken aloud in the narration as well as written
to the record.
"""

from __future__ import annotations

import re

from src.security.guardrails import redact_secrets

# Comment text that documents the file or a license rather than the
# function below it; narrating these adds nothing.
_BOILERPLATE_RE = re.compile(
    r"^(copyright|license|licensed|spdx|eslint|ts-ignore|@ts-|prettier|istanbul|c8 )",
    re.IGNORECASE,
)

_REACT_HOOK_RE = re.compile(r"\buse(State|Effect|Callback|Memo|Ref|Context|Reducer)\s*\(")
_THROW_RE = re.compile(r"\bthrow\s+new\b|\berrors\.New\(|\bfmt\.Errorf\(")
_AWAIT_RE = re.compile(r"\bawait\b")


def _strip_comment_markers(raw_lines: list[str]) -> str:
    cleaned: list[str] = []
    for line in raw_lines:
        text = line.strip()
        text = re.sub(r"^/\*\*?", "", text)
        text = re.sub(r"\*/$", "", text)
        text = re.sub(r"^\*+", "", text)
        text = re.sub(r"^//+", "", text)
        text = text.strip()
        if not text:
            # Paragraph break inside a doc comment.
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if text.startswith("@"):
            # JSDoc tags (@param, @returns) are structure, not prose.
            continue
        cleaned.append(text)

    paragraph = " ".join(part for part in cleaned if part).strip()
    paragraph = re.sub(r"\s+", " ", paragraph)
    return paragraph


def leading_doc_comment(lines: list[str], start_line: int) -> str | None:
    """The comment block directly above a definition, as plain prose.

    A blank line between the comment and the definition means the
    comment belongs to whatever came before, not to this function, so
    nothing is returned.
    """
    index = start_line - 2  # 0-based line directly above the definition
    if index < 0 or index >= len(lines):
        return None

    above = lines[index].strip()
    if not above:
        return None

    block: list[str] = []

    if above.endswith("*/"):
        cursor = index
        while cursor >= 0 and "/*" not in lines[cursor]:
            cursor -= 1
        if cursor < 0:
            return None
        block = lines[cursor:index + 1]
    elif above.startswith("//"):
        cursor = index
        while cursor >= 0 and lines[cursor].strip().startswith("//"):
            cursor -= 1
        block = lines[cursor + 1:index + 1]
    else:
        return None

    prose = _strip_comment_markers(block)
    if not prose or _BOILERPLATE_RE.match(prose):
        return None
    # A bare restatement of the name ("requireAuth") says nothing.
    if len(prose.split()) < 3:
        return None

    prose, _ = redact_secrets(prose)
    return prose


def _body(lines: list[str], line_range) -> str:
    start, end = line_range
    return "\n".join(lines[max(0, start - 1):end])


def is_exported(signature: str, name: str, language: str) -> bool:
    if language == "go":
        # Go's export rule is literally the leading capital.
        return bool(name) and name[0].isupper()
    return signature.lstrip().startswith("export")


def callers_of(name: str, this_range, all_functions: list, lines: list[str]) -> list[str]:
    """Names of other functions in this chunk whose body calls `name`."""
    call_re = re.compile(rf"\b{re.escape(name)}\s*\(")
    callers: list[str] = []
    for other in all_functions:
        other_name = other["name"]
        other_range = other["lineRange"]
        if other_name == name or list(other_range) == list(this_range):
            continue
        if call_re.search(_body(lines, other_range)):
            callers.append(other_name)
    return callers


def calls_made(name: str, this_range, all_functions: list, lines: list[str]) -> list[str]:
    """Names of other functions in this chunk that this one calls."""
    body = _body(lines, this_range)
    called: list[str] = []
    for other in all_functions:
        other_name = other["name"]
        if other_name == name or list(other["lineRange"]) == list(this_range):
            continue
        if re.search(rf"\b{re.escape(other_name)}\s*\(", body):
            called.append(other_name)
    return called


def _params_from_signature(signature: str) -> list[str]:
    match = re.search(r"\(([^)]*)\)", signature)
    if not match:
        return []
    raw = match.group(1).strip()
    if not raw:
        return []
    names: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # "ctx context.Context" (go) / "raw: string" (ts) / "{ a, b }"
        token = part.split(":")[0].strip().split(" ")[0].strip()
        token = token.strip("{}[] ")
        if token and re.match(r"^\w+$", token):
            names.append(token)
    return names


def build_function_context(
    name: str,
    signature: str,
    line_range,
    lines: list[str],
    all_functions: list,
    language: str,
    api_calls: list | None = None,
    side_effects: list | None = None,
) -> dict:
    """The per-function facts, all read off the source. Keys whose
    evidence wasn't found are present but empty/false, so the narrator
    can tell "no callers in this chunk" from "not looked at"."""
    body = _body(lines, line_range)
    start, end = line_range

    def in_range(line: int) -> bool:
        return start <= line <= end

    # The TS extractor returns ExtractedSideEffect objects and the Go one
    # returns (kind, line) tuples. Normalise rather than make either
    # extractor change shape for this.
    normalised_effects: list[tuple[str, int]] = []
    for effect in side_effects or []:
        if isinstance(effect, tuple):
            normalised_effects.append((effect[0], effect[1]))
        else:
            normalised_effects.append((effect.kind, effect.line))

    return {
        "description": leading_doc_comment(lines, start),
        "descriptionSource": "doc-comment" if leading_doc_comment(lines, start) else None,
        "exported": is_exported(signature, name, language),
        "calledBy": callers_of(name, line_range, all_functions, lines),
        "calls": calls_made(name, line_range, all_functions, lines),
        "params": _params_from_signature(signature),
        "raisesError": bool(_THROW_RE.search(body)),
        "isAsync": bool(_AWAIT_RE.search(body)) or "async" in signature,
        "reactHooks": sorted({f"use{m.group(1)}" for m in _REACT_HOOK_RE.finditer(body)}),
        "apiCalls": [
            {"method": c.method, "url": c.url}
            for c in (api_calls or []) if in_range(c.line)
        ],
        "sideEffects": sorted({kind for kind, line in normalised_effects if in_range(line)}),
        "lineCount": max(1, end - start + 1),
    }
