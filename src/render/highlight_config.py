"""Phase 6 — turns timed cues into the frame-based highlight config a
Remotion component drives Shiki decorations with, per the locked rule:
"Convert seconds to frames with frame = seconds x fps. Drive highlights
with useCurrentFrame() and interpolate() in Remotion. Apply highlight
lines with Shiki decorations or notation transformers."

This module only produces the JSON config; the actual Shiki call and
React rendering happen in the Remotion project (JS/TS side), not here.

Display vs. anchor timing
-------------------------
A cue's aligned anchor (fromFrame/toFrame) is the span of the single
spoken word it was matched to — typically 0.3-0.5s. Showing a
highlight for only that long makes it a flash the viewer cannot read,
and leaves the code unhighlighted for most of the chunk.

So each cue also carries a *display* window:

  - it starts at its anchor, pushed later only as far as needed to
    guarantee the previous cue its MIN_HIGHLIGHT_SECONDS on screen, and
  - it holds until the next cue's display window begins (the last cue
    holds to the end of the chunk).

That gives a highlight that is always on screen from the first cue
onward, and readable rather than a flicker. The anchor fields are left
untouched so the bundle stays honest about what was actually aligned
to the audio; displayShifted marks any cue whose display start had to
move off its anchor.
"""

from __future__ import annotations

import math

from .timing import TimedCue, ms_to_frame

MIN_HIGHLIGHT_SECONDS = 2.0


def build_highlight_config(
    timed_cues: list[TimedCue],
    fps: int,
    duration_ms: int | None = None,
) -> list[dict]:
    if not timed_cues:
        return []

    min_frames = max(1, round(MIN_HIGHLIGHT_SECONDS * fps))
    total_frames = (
        max(1, math.ceil((duration_ms / 1000) * fps)) if duration_ms else None
    )

    ordered = sorted(timed_cues, key=lambda c: (c.start_ms, c.id))
    count = len(ordered)

    # If the chunk is too short to give every cue the full minimum, share
    # the time out evenly instead of letting the later cues fall off the
    # end of the chunk entirely.
    effective_min = min_frames
    if total_frames is not None:
        effective_min = max(1, min(min_frames, total_frames // count))

    display_starts: list[int] = []
    previous: int | None = None
    for index, cue in enumerate(ordered):
        anchor = ms_to_frame(cue.start_ms, fps)
        start = anchor if previous is None else max(anchor, previous + effective_min)
        if total_frames is not None:
            # Leave room for this cue and every cue still to come.
            latest = total_frames - (count - index) * effective_min
            start = min(start, max(0, latest))
            if previous is not None:
                start = max(start, previous + 1)
        start = max(0, start)
        if index == 0:
            # Hold the first cue from the very start of the chunk. The
            # opening beats ("this section covers X, built with Y") are
            # about the chunk as a whole, so leaving the code with no
            # highlight at all until the first named item would mean
            # seconds of dead, unmarked code on screen.
            start = 0
        display_starts.append(start)
        previous = start

    config = []
    for index, cue in enumerate(ordered):
        display_from = display_starts[index]
        if index + 1 < count:
            display_to = display_starts[index + 1]
        elif total_frames is not None:
            display_to = max(total_frames, display_from + effective_min)
        else:
            display_to = display_from + effective_min

        config.append({
            "id": cue.id,
            "lineRange": cue.line_range,
            # The real aligned anchor, unchanged.
            "fromFrame": ms_to_frame(cue.start_ms, fps),
            "toFrame": ms_to_frame(cue.end_ms, fps),
            # The window the highlight is actually shown for.
            "displayFromFrame": display_from,
            "displayToFrame": display_to,
            "displayShifted": display_from != ms_to_frame(cue.start_ms, fps),
            "assumed": cue.assumed,
            "note": cue.note,
        })
    return config
