"""Phase 6 — turns timed cues into the frame-based highlight config a
Remotion component drives Shiki decorations with, per the locked rule:
"Convert seconds to frames with frame = seconds x fps. Drive highlights
with useCurrentFrame() and interpolate() in Remotion. Apply highlight
lines with Shiki decorations or notation transformers."

This module only produces the JSON config; the actual Shiki call and
React rendering happen in the Remotion project (JS/TS side), not here.
"""

from __future__ import annotations

from .timing import TimedCue, ms_to_frame


def build_highlight_config(timed_cues: list[TimedCue], fps: int) -> list[dict]:
    config = []
    for cue in timed_cues:
        config.append({
            "id": cue.id,
            "lineRange": cue.line_range,
            "fromFrame": ms_to_frame(cue.start_ms, fps),
            "toFrame": ms_to_frame(cue.end_ms, fps),
            "assumed": cue.assumed,
            "note": cue.note,
        })
    return config
