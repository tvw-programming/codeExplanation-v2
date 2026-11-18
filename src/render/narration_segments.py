"""Phase 6 — splits a chunk's spoken narration into labelled segments
(A, B, C, ...) with a frame window each, so the video can show the
narration as a list and brighten whichever line is being spoken right
now instead of showing one undifferentiated wall of text.

Timing comes from the same word stream the highlight cues are aligned
against (a real whisper.cpp transcript when available, the evenly
spaced estimate otherwise), so a segment's window is exactly as
trustworthy as the chunk's alignmentSource says it is — this module
invents no timing of its own.

Word indices are matched positionally against that stream. When the
transcript has a different word count than the clean text it was
transcribed from (real transcription rarely matches the TTS input word
for word), indices are clamped to the available range rather than
dropped, and the segment is marked assumed so the mismatch is visible
rather than silently smoothed over.
"""

from __future__ import annotations

import re

from .timing import TranscriptWord, ms_to_frame

# Split after sentence-ending punctuation followed by whitespace. The
# narration is template-generated (see src/narrate/script_builder.py),
# so it carries no abbreviations or decimals this would mis-split on.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def segment_label(index: int) -> str:
    """A, B, ... Z, AA, AB, ... for however many segments there are."""
    if index < len(_ALPHABET):
        return _ALPHABET[index]
    first, second = divmod(index, len(_ALPHABET))
    return f"{_ALPHABET[first - 1]}{_ALPHABET[second]}"


def split_sentences(clean_text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(clean_text.strip()) if s.strip()]


def build_narration_segments(
    clean_text: str,
    words: list[TranscriptWord],
    fps: int,
    duration_ms: int | None = None,
) -> list[dict]:
    """One entry per spoken sentence: its label, text, and the frame
    window it is being spoken in. Consecutive segments are butted up
    against each other so exactly one is active at any frame."""
    sentences = split_sentences(clean_text)
    if not sentences:
        return []

    total_frames = (
        max(1, ms_to_frame(duration_ms, fps)) if duration_ms else None
    )

    if not words:
        # No word stream at all: fall back to even spacing across the
        # measured duration, marked assumed.
        if total_frames is None:
            return []
        per = total_frames / len(sentences)
        return [
            {
                "label": segment_label(i),
                "text": sentence,
                "fromFrame": round(i * per),
                "toFrame": round((i + 1) * per),
                "assumed": True,
                "note": "No word timings were available; this segment's window is "
                        "an even split of the measured audio duration.",
            }
            for i, sentence in enumerate(sentences)
        ]

    last_word = len(words) - 1
    segments: list[dict] = []
    cursor = 0

    for i, sentence in enumerate(sentences):
        word_count = len([w for w in sentence.split() if w])
        start_index = cursor
        end_index = cursor + word_count - 1
        cursor += word_count

        clamped = start_index > last_word or end_index > last_word
        start_word = words[min(start_index, last_word)]
        end_word = words[min(end_index, last_word)]

        segments.append({
            "label": segment_label(i),
            "text": sentence,
            "fromFrame": ms_to_frame(start_word.start_ms, fps),
            "toFrame": ms_to_frame(end_word.end_ms, fps),
            "assumed": clamped,
            "note": (
                f"Sentence word range [{start_index}, {end_index}] ran past the "
                f"{len(words)}-word transcript; window clamped to the last word."
                if clamped else None
            ),
        })

    # Butt consecutive windows together so there is never a gap with no
    # active segment, and let the last one run to the end of the audio.
    for i in range(len(segments) - 1):
        segments[i]["toFrame"] = max(segments[i]["toFrame"], segments[i + 1]["fromFrame"])
    segments[0]["fromFrame"] = 0
    if total_frames is not None:
        segments[-1]["toFrame"] = max(segments[-1]["toFrame"], total_frames)

    return segments
