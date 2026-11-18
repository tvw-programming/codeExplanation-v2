"""Phase 5 — what to actually say about one function.

"The requireAuth function runs next" tells a viewer nothing. This
builds a real explanation instead, out of the facts Phase 3 read off
the source (see src/extract/function_context.py): the author's own doc
comment, the call graph, and what happens inside the function's lines.

Two versions come out of it:

  - a summary, a line or two, for the list beside the code;
  - the spoken narration, which says more and is what the viewer hears
    while that function is highlighted.

The discipline is the same as the rest of the narrator: nothing is
said that isn't grounded in the extraction. Where a fact is missing,
the sentence is left out rather than guessed at, and where the
extraction can only see part of the picture — an exported function
whose callers live in other files — the narration says so instead of
implying the chunk is the whole story. A doc comment is attributed as
documentation rather than asserted as fact, because it is the author's
claim about the code, not something the extractor verified.
"""

from __future__ import annotations

import re

# Pause after a function's narration, so there is time to actually read
# the highlighted code before the next one starts.
MIN_PAUSE_MS = 1000
MAX_PAUSE_MS = 3000
# A function this many lines long earns the full pause.
PAUSE_SATURATION_LINES = 40

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
# Prose that reads fine on screen but is noise when spoken aloud.
_CODE_SPAN_RE = re.compile(r"`([^`]*)`")
_EMPHASIS_RE = re.compile(r"[*_]{1,2}([^*_]+)[*_]{1,2}")

# A doc comment longer than this is trimmed at a sentence boundary:
# past roughly this much, one function stalls the whole video.
MAX_SPOKEN_DOC_CHARS = 450


def pause_after_ms(line_count: int) -> int:
    """Longer functions get a longer pause — there is more to read."""
    span = max(0, min(line_count, PAUSE_SATURATION_LINES))
    scaled = MIN_PAUSE_MS + (MAX_PAUSE_MS - MIN_PAUSE_MS) * (span / PAUSE_SATURATION_LINES)
    return int(round(scaled))


def first_sentence(text: str, limit: int = 180) -> str:
    parts = _SENTENCE_END_RE.split(text.strip())
    sentence = parts[0].strip() if parts else text.strip()
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return sentence


def speakable(text: str, max_chars: int = MAX_SPOKEN_DOC_CHARS) -> str:
    """Doc comments are written to be read, not spoken: backticks,
    emphasis markers and dashes turn into noise in a text-to-speech
    engine, and a very long comment would stall the video on one
    function."""
    text = _CODE_SPAN_RE.sub(r"\1", text)
    text = _EMPHASIS_RE.sub(r"\1", text)
    text = text.replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_chars:
        return text
    # Cut at the last sentence boundary that fits, so it ends cleanly.
    clipped = text[:max_chars]
    sentences = _SENTENCE_END_RE.split(clipped)
    if len(sentences) > 1:
        return " ".join(sentences[:-1]).strip()
    return clipped.rsplit(" ", 1)[0].rstrip(",;:") + "."


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _role_sentences(fn: dict) -> list[str]:
    """Who uses this function — the honest version, including when the
    chunk genuinely cannot see the callers."""
    called_by = fn.get("calledBy") or []
    exported = bool(fn.get("exported"))
    sentences: list[str] = []

    if called_by:
        sentences.append(f"It is called by {_join(called_by)} in this same file.")
        if len(called_by) > 1:
            sentences.append(
                f"Because {len(called_by)} callers share it, that logic lives in one "
                f"place instead of being repeated in each of them."
            )
    if exported:
        sentences.append(
            "It is exported, so other files can use it too. Which ones is not visible "
            "from this chunk alone."
        )
    if not called_by and not exported:
        sentences.append(
            "Nothing else in this chunk calls it and it is not exported, so it is used "
            "only where it is defined."
        )
    return sentences


def _behaviour_sentences(fn: dict) -> list[str]:
    sentences: list[str] = []
    params = fn.get("params") or []
    if params:
        sentences.append(f"It takes {_join(params)}.")

    api_calls = fn.get("apiCalls") or []
    for call in api_calls[:2]:
        method = call.get("method") or ""
        url = call.get("url") or ""
        if method and url:
            sentences.append(f"It sends a {method} request to {url}.")

    calls = fn.get("calls") or []
    if calls:
        sentences.append(f"It calls {_join(calls[:3])} from this same file.")

    side_effects = fn.get("sideEffects") or []
    if side_effects:
        sentences.append(f"It also performs {_join(list(side_effects)[:3])}.")

    hooks = fn.get("reactHooks") or []
    if "useCallback" in hooks or "useMemo" in hooks:
        sentences.append(
            "It is memoised, so it is not rebuilt on every render."
        )

    if fn.get("raisesError"):
        sentences.append(
            "It raises an error rather than carrying on, so a caller fails immediately "
            "instead of continuing in a bad state."
        )
    return sentences


def build_function_summary(fn: dict) -> str:
    """The line shown beside the code while this function is highlighted."""
    name = fn.get("name") or "this function"
    description = fn.get("description")
    if description:
        return f"{name} — {first_sentence(description)}"

    bits: list[str] = []
    if fn.get("exported"):
        bits.append("exported")
    called_by = fn.get("calledBy") or []
    if called_by:
        bits.append(f"called by {_join(called_by[:2])}")
    if fn.get("raisesError"):
        bits.append("raises an error if its check fails")
    api_calls = fn.get("apiCalls") or []
    if api_calls:
        method = api_calls[0].get("method", "")
        bits.append(f"makes a {method} request".strip())
    if not bits:
        line_count = fn.get("lineCount") or 0
        bits.append(f"{line_count} lines, no callers visible in this chunk")
    return f"{name} — {'; '.join(bits)}."


def build_function_narration(fn: dict) -> str:
    """What the viewer hears while this function is highlighted."""
    name = fn.get("name") or "this function"
    line_range = fn.get("lineRange") or []
    sentences: list[str] = []

    if len(line_range) == 2:
        sentences.append(f"Next is {name}, at lines {line_range[0]} to {line_range[1]}.")
    else:
        sentences.append(f"Next is {name}.")

    description = fn.get("description")
    if description:
        # Attributed, not asserted: this is the author's description of
        # the code, which the extractor has not verified against it.
        sentences.append(f"Its own documentation says: {speakable(description)}")

    sentences.extend(_behaviour_sentences(fn))
    sentences.extend(_role_sentences(fn))

    # No "this function is undocumented" line: it would repeat on most
    # functions in most chunks, and the viewer can see there is nothing
    # to show. The derived sentences above already carry what is known.
    return " ".join(s.strip() for s in sentences if s.strip())
