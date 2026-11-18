"""Phase 6 — prepares a narration script for TTS and records where each
VISUAL[HIGHLIGHT:id] cue sits in the resulting spoken-word stream.

The cue tokens from Phase 5 must never reach the TTS engine as literal
text (it would say the words "VISUAL HIGHLIGHT bracket..." out loud).
This strips them out, and for each one records how many real spoken
words came before it, so that once the actual audio is transcribed
(Phase 6's alignment step), that word index can be looked up in the
real transcript to find the cue's real timestamp.
"""

from __future__ import annotations

import re

VISUAL_TOKEN_RE = re.compile(r"VISUAL\[HIGHLIGHT:([\w-]+)\]")


def concat_beats(purpose: str, connections: str, flow: list[str], recap: str) -> str:
    return " ".join([purpose, connections, *flow, recap])


def strip_visual_tokens(text: str) -> tuple[str, dict[str, int]]:
    """Returns (clean_text, cue_word_index) where cue_word_index[cue_id]
    is the number of real spoken words that precede that cue in
    clean_text (0 if the cue is the very first thing in the text)."""
    cue_word_index: dict[str, int] = {}
    cursor = 0
    clean_words: list[str] = []

    for match in VISUAL_TOKEN_RE.finditer(text):
        before = text[cursor:match.start()]
        clean_words.extend(w for w in before.split() if w)
        cue_id = match.group(1)
        cue_word_index[cue_id] = max(len(clean_words) - 1, 0)
        cursor = match.end()

    tail = text[cursor:]
    clean_words.extend(w for w in tail.split() if w)

    clean_text = " ".join(clean_words)
    return clean_text, cue_word_index
