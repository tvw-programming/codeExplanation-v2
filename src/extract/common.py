"""Phase 3 — shared extraction helpers.

Extraction here is regex/heuristic-based static analysis, not a real
AST parser (ts-morph, go/ast). That is a deliberate scope decision for
this phase, not an oversight: a heuristic extractor can still produce
every required field, and every field it cannot determine with
confidence is marked "assumed": true with a note, per the locked
accuracy rule ("restrict every named symbol to the extraction's symbol
table; mark assumed otherwise"). A real parser is the natural upgrade
path and would mostly just raise confidence, not change the schema.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.security.guardrails import redact_secrets

MAX_SNIPPET_LINES = 120

LANGUAGE_BY_EXTENSION = {
    ".tsx": "TypeScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".vue": "Vue",
    ".go": "Go",
    ".py": "Python",
    ".java": "Java",
    ".rs": "Rust",
}


def detect_language(file_path: str) -> str:
    """Dynamic language detection from the file extension — not a fixed
    list, per the locked rule, though common ones are named here first."""
    ext = Path(file_path).suffix
    return LANGUAGE_BY_EXTENSION.get(ext, ext.lstrip(".") or "unknown")


def read_lines(root: Path, file_path: str) -> list[str]:
    full = root / file_path
    try:
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().splitlines()
    except OSError:
        return []


def content_hash(root: Path, file_path: str) -> str:
    """sha256 of the file's raw bytes, used for the Phase 4 reuse rule."""
    full = root / file_path
    try:
        data = full.read_bytes()
    except OSError:
        data = b""
    return hashlib.sha256(data).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CodeSnippet:
    text: str
    truncated: bool
    continuation_note: str | None = None
    secrets_redacted: bool = False


def trim_snippet(lines: list[str], start_line: int, end_line: int,
                  max_lines: int = MAX_SNIPPET_LINES) -> CodeSnippet:
    """Trim a 1-indexed [start_line, end_line] slice of `lines` to at most
    `max_lines`. Per the locked rule, a function/model longer than this
    is NOT cut off silently — it continues in a follow-on snapshot, so
    the caller gets a continuation note rather than losing the tail.

    Every snippet is also run through guardrails.redact_secrets() here
    — the single choke point every function/struct/interface snippet
    passes through on its way into a chunk record — rather than relying
    on callers to remember to scan. A code review found this was
    previously never wired in anywhere, so a hardcoded secret in a
    source file was copied verbatim into the output JSON.
    """
    span = lines[start_line - 1:end_line]
    if len(span) <= max_lines:
        text, redacted = redact_secrets("\n".join(span))
        return CodeSnippet(text=text, truncated=False, secrets_redacted=redacted)

    first_part = span[:max_lines]
    remaining = len(span) - max_lines
    note = (
        f"Snippet trimmed to {max_lines} lines; {remaining} more line(s) "
        f"follow in this definition (source lines {start_line + max_lines}-{end_line}). "
        "Continue in a follow-on snapshot rather than treating this as the whole definition."
    )
    text, redacted = redact_secrets("\n".join(first_part))
    return CodeSnippet(text=text, truncated=True, continuation_note=note, secrets_redacted=redacted)


# What to report when an extractor came away with nothing at all. Low
# rather than high: see confidence_from_flags.
EMPTY_EXTRACTION_CONFIDENCE = 0.3


def confidence_from_flags(total_claims: int, assumed_claims: int, base: float = 0.95) -> float:
    """A simple, documented confidence formula: start from `base` and
    subtract proportionally for every claim this extractor had to mark
    assumed. Not a validated scoring model — a starting point, same as
    the project's own 0.85 threshold.

    Finding nothing scores LOW, not high. It used to return `base`,
    which meant a file the extractor could not read at all — an Angular
    component, whose class methods, @Input()s and HttpClient calls match
    none of the TypeScript patterns — was reported at 0.95 with every
    list empty and no risks flagged. "I have nothing to say about this
    file" is the least confident an extractor can be, not the most, and
    reporting it as high confidence hid the one signal that would have
    revealed the stack was unsupported.
    """
    if total_claims == 0:
        return EMPTY_EXTRACTION_CONFIDENCE
    penalty = 0.5 * (assumed_claims / total_claims)
    return round(max(0.05, base - penalty), 2)


def confidence_level(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"
