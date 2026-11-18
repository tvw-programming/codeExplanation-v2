"""Phase 6 — orchestrates one chunk's narration beats into a render
bundle: audio, per-beat narration segments, and a frame-based
highlight config, ready for the Remotion project (render-app/) to
render.

Each beat is synthesised on its own and padded with the pause it asks
for, then the parts are joined into one narration track (see
audio_assembly.py). That is what makes the pauses real — the video is
one continuous soundtrack per chunk, so "give the viewer two seconds to
read this function" can only mean two seconds of actual samples.

It also makes the timing exact. Every beat's start and end are
measured from the rendered audio, so the highlight for a function is
up for precisely as long as that function is being talked about, and
the narration list highlights precisely the line being spoken. The
earlier approach could not do this: it synthesised the whole chunk in
one pass and then had to guess where each sentence fell, either by
spreading words evenly across the total duration or by matching word
indices against a transcript. alignmentSource records which of these
produced the timing, and is "measured-beats" on this path.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.narrate.script_builder import NarrationScript
from .audio_assembly import (
    AudioAssemblyError,
    concat_wavs,
    pad_with_silence,
    probe_duration_ms,
)
from .highlight_config import build_highlight_config
from .narration_segments import segment_label
from .timing import TimedCue, ms_to_frame
from .tts import TTSError, synthesize

RENDER_APP_DIR = Path(__file__).resolve().parents[2] / "render-app"

ALIGNMENT_MEASURED = "measured-beats"


def _synthesize_beats(script: NarrationScript, output_dir: Path) -> tuple[list[dict], Path]:
    """Renders every beat to audio, pads each with its pause, joins them,
    and reports where each one landed in the finished track."""
    parts_dir = output_dir / "beats"
    parts_dir.mkdir(parents=True, exist_ok=True)

    joined_parts: list[Path] = []
    placements: list[dict] = []
    cursor_ms = 0

    for index, beat in enumerate(script.beats):
        raw = parts_dir / f"{index:03d}.wav"
        result = synthesize(beat.spoken, raw)
        speech_ms = probe_duration_ms(raw)

        padded = pad_with_silence(raw, parts_dir / f"{index:03d}-padded.wav",
                                  beat.pause_after_ms)
        total_ms = probe_duration_ms(padded) if padded != raw else speech_ms

        placements.append({
            "beat": beat,
            "startMs": cursor_ms,
            "speechEndMs": cursor_ms + speech_ms,
            "endMs": cursor_ms + total_ms,
            "engine": result.engine,
        })
        joined_parts.append(padded)
        cursor_ms += total_ms

    narration_path = concat_wavs(joined_parts, output_dir / "narration.wav")
    return placements, narration_path


def _cues_from_placements(script: NarrationScript, placements: list[dict]) -> list[TimedCue]:
    """A cue is anchored to the beat that talks about it, so its window
    is measured rather than inferred."""
    cues_by_id = {cue.id: cue for cue in script.visual_cues}
    timed: list[TimedCue] = []
    for placement in placements:
        beat = placement["beat"]
        if not beat.cue_id:
            continue
        cue = cues_by_id.get(beat.cue_id)
        if cue is None:
            continue
        timed.append(TimedCue(
            id=cue.id,
            token=cue.token,
            line_range=cue.line_range,
            label=cue.label,
            start_ms=placement["startMs"],
            end_ms=placement["endMs"],
            # The window is the measured span of the audio that
            # describes these lines — nothing is being guessed at.
            assumed=False,
        ))
    return timed


def _segments_from_placements(placements: list[dict], fps: int) -> list[dict]:
    segments: list[dict] = []
    for index, placement in enumerate(placements):
        beat = placement["beat"]
        segments.append({
            "label": segment_label(index),
            "kind": beat.kind,
            # What the panel shows; the spoken text is longer.
            "text": beat.summary,
            "spoken": beat.spoken,
            "fromFrame": ms_to_frame(placement["startMs"], fps),
            "toFrame": ms_to_frame(placement["endMs"], fps),
            "assumed": False,
            "note": None,
        })
    # Butt consecutive windows together so exactly one segment is active
    # at any frame, with no flicker between them.
    for current, nxt in zip(segments, segments[1:]):
        current["toFrame"] = nxt["fromFrame"]
    if segments:
        segments[0]["fromFrame"] = 0
    return segments


def build_render_bundle(
    script: NarrationScript,
    output_dir: Path,
    fps: int = 30,
    record: dict | None = None,
    overview: dict | None = None,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    record = record or {}

    if not script.beats:
        return {"chunkId": script.chunk_id, "error": "Narration script has no beats."}

    try:
        placements, wav_path = _synthesize_beats(script, output_dir)
    except TTSError as exc:
        return {"chunkId": script.chunk_id, "error": f"TTS failed: {exc}"}
    except AudioAssemblyError as exc:
        return {"chunkId": script.chunk_id, "error": f"Audio assembly failed: {exc}"}

    duration_ms = probe_duration_ms(wav_path)
    if duration_ms <= 0:
        # Fall back to the sum of the measured parts rather than
        # reporting a zero-length chunk.
        duration_ms = placements[-1]["endMs"] if placements else 0

    timed_cues = _cues_from_placements(script, placements)
    highlight_config = build_highlight_config(timed_cues, fps, duration_ms)
    narration_segments = _segments_from_placements(placements, fps)

    engines = {p["engine"] for p in placements}
    tts_engine = engines.pop() if len(engines) == 1 else "+".join(sorted(engines))

    bundle = {
        "chunkId": script.chunk_id,
        # Carried through so the video can title each section with the
        # file it is actually explaining, rather than the chunk id.
        "filePath": record.get("filePath"),
        "featureName": record.get("featureName"),
        "durationMs": duration_ms,
        "alignmentSource": ALIGNMENT_MEASURED,
        "ttsEngine": tts_engine,
        "narrationAudio": str(wav_path),
        "cleanText": " ".join(p["beat"].spoken for p in placements),
        # Contents of the card shown before this file's walkthrough.
        "fileOverview": overview,
        "narrationSegments": narration_segments,
        "highlightConfig": highlight_config,
    }
    (output_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle
