"""Phase 6 — fallback word timing when real transcription isn't
available.

The real alignment path (tools/transcribe.mjs, whisper.cpp) needs to
download a model file from huggingface.co, which this sandbox's
network allowlist blocks (verified: the whisper.cpp binary itself
compiles and runs locally; only the model download is blocked — see
the Phase 6 plan writeup). Rather than block the whole phase on that
one external host, this module provides an honestly-labeled fallback:
it distributes each word evenly across the real, ffprobe-measured
audio duration. This is NOT a transcription and must never be
presented as verified timing — the render pipeline that calls this
always marks every cue built from it as assumed=True, regardless of
whether the word index happened to be in range.
"""

from __future__ import annotations

from .timing import TranscriptWord


def build_estimated_words(text: str, duration_ms: int) -> list[TranscriptWord]:
    """Splits `text` into words and spreads them evenly across
    duration_ms. Proportional to word length would be marginally more
    realistic, but even spacing keeps the estimate's nature obvious
    rather than dressing it up as more precise than it is."""
    words = [w for w in text.split() if w]
    if not words:
        return []

    slot_ms = duration_ms / len(words)
    timed = []
    for i, word in enumerate(words):
        start = round(i * slot_ms)
        end = round((i + 1) * slot_ms)
        timed.append(TranscriptWord(word=word, start_ms=start, end_ms=end))
    return timed
