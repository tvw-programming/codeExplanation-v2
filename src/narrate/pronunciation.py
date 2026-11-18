"""Phase 5 — identifier pronunciation lookup.

Per the locked rule: map each identifier (camelCase, snake_case, route
segments) to its spoken form. This module builds that mapping
mechanically from the identifier's own shape; it does not call a TTS
engine or validate against a real voice. The rules doc is explicit
that the table must still be "tested per voice before rendering" —
that step belongs to Phase 6 (video rendering), where an actual voice
is in the loop.
"""

from __future__ import annotations

import re

# Acronyms that are pronounceable as a word rather than spelled out
# letter by letter. This list is a judgment call, not a sourced rule —
# flagged here so it's easy to find and correct.
PRONOUNCEABLE_ACRONYMS = {
    "JSON": "Jason",
    "SQL": "sequel",
    "URL": "U R L",
    "API": "A P I",
    "ID": "I D",
    "DB": "D B",
    "HTTP": "H T T P",
    "HTML": "H T M L",
    "CSS": "C S S",
    "JWT": "J W T",
    "UUID": "U U I D",
}

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM_RE = re.compile(r"[_\-/.:${}]+")


def split_identifier(identifier: str) -> list[str]:
    """Splits a camelCase, PascalCase, snake_case, kebab-case, or
    route-segment identifier into its component words, dropping
    punctuation (dynamic-route braces, path separators) rather than
    speaking it."""
    if not identifier:
        return []
    # First split on non-alphanumeric separators (snake_case, kebab-case,
    # path segments, template braces like ${id}).
    parts = [p for p in _NON_ALNUM_RE.split(identifier) if p]
    words: list[str] = []
    for part in parts:
        # Then split camelCase/PascalCase boundaries within each part.
        sub = _CAMEL_BOUNDARY_RE.split(part)
        words.extend(w for w in sub if w)
    return words


def spoken_form(identifier: str) -> str:
    """Returns a TTS-friendly spoken rendering of one identifier."""
    words = split_identifier(identifier)
    if not words:
        return ""
    rendered = []
    for word in words:
        upper = word.upper()
        if upper in PRONOUNCEABLE_ACRONYMS and word.isupper():
            rendered.append(PRONOUNCEABLE_ACRONYMS[upper])
        else:
            rendered.append(word)
    return " ".join(rendered)


def build_pronunciation_table(identifiers: list[str]) -> dict[str, str]:
    """Builds the lookup table for a set of identifiers, deduplicated
    and skipping anything that produced no words (e.g. pure punctuation)."""
    table: dict[str, str] = {}
    for identifier in identifiers:
        if identifier in table:
            continue
        form = spoken_form(identifier)
        if form:
            table[identifier] = form
    return table
