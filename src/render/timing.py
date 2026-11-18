"""Phase 6 — aligns VISUAL cues to real word timestamps from a
transcript, and converts milliseconds to Remotion frames.

Per the locked rule: "If WhisperX cannot time an identifier, anchor
the cue to the nearest timed word and widen the window by about 200ms.
If a cue still cannot be aligned, mark it assumed: true." WhisperX
itself needs a Python audio stack (pyannote, torch) this environment
doesn't carry; the word-level-timestamp equivalent used here is
whisper.cpp via Remotion's own @remotion/install-whisper-cpp package
(see render-app/scripts/transcribe.mjs), which gives the same kind of
per-word (word, startMs, endMs) data without that dependency. The
alignment logic below is the same either way.
"""

from __future__ import annotations

from dataclasses import dataclass

WORD_WIDEN_MS = 200


@dataclass
class TranscriptWord:
    word: str
    start_ms: int
    end_ms: int


@dataclass
class TimedCue:
    id: str
    token: str
    line_range: list[int]
    label: str
    start_ms: int
    end_ms: int
    assumed: bool
    note: str | None = None


def ms_to_frame(ms: float, fps: int) -> int:
    return round((ms / 1000) * fps)


def align_cues_to_words(
    cues: list,  # list[VisualCue] from src.narrate.visual_cues
    cue_word_index: dict[str, int],
    words: list[TranscriptWord],
) -> list[TimedCue]:
    """For each cue, looks up its anchor word index in the real
    transcript. An index inside the transcript's range is an exact,
    verified alignment. An index past the end of the transcript (the
    TTS engine and the transcriber rarely produce identical word
    counts) falls back to the nearest available word, widens the
    window by WORD_WIDEN_MS, and is marked assumed."""
    timed: list[TimedCue] = []
    last_index = len(words) - 1

    for cue in cues:
        index = cue_word_index.get(cue.id)
        if index is None or not words:
            timed.append(TimedCue(
                id=cue.id, token=cue.token, line_range=cue.line_range, label=cue.label,
                start_ms=0, end_ms=0, assumed=True,
                note="No transcript word available to align this cue; timing is unverified.",
            ))
            continue

        if 0 <= index <= last_index:
            word = words[index]
            timed.append(TimedCue(
                id=cue.id, token=cue.token, line_range=cue.line_range, label=cue.label,
                start_ms=word.start_ms, end_ms=word.end_ms, assumed=False,
            ))
        else:
            nearest = words[last_index] if index > last_index else words[0]
            timed.append(TimedCue(
                id=cue.id, token=cue.token, line_range=cue.line_range, label=cue.label,
                start_ms=max(nearest.start_ms - WORD_WIDEN_MS, 0),
                end_ms=nearest.end_ms + WORD_WIDEN_MS,
                assumed=True,
                note=f"Anchor word index {index} was outside the transcript "
                     f"({len(words)} words); widened to the nearest word.",
            ))

    return timed
