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
from src.narrate.function_narration import speakable
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


def _build_card_narration(overview: dict | None, output_dir: Path) -> dict | None:
    """Speaks the file card: its name, then what the file is for.

    The card's on-screen time is this audio's length (with a floor
    applied in the composition), so the viewer is never reading a
    summary that has already been talked over, and never left staring
    at a card after the narration has finished.
    """
    if not overview:
        return None

    file_name = overview.get("fileName") or ""
    purpose = overview.get("purpose") or ""
    spoken = speakable(f"{file_name}. {purpose}".strip())
    if not spoken:
        return None

    wav_path = output_dir / "card.wav"
    try:
        result = synthesize(spoken, wav_path)
    except TTSError:
        # The card is still worth showing without narration; the
        # composition falls back to its minimum duration.
        return None

    return {
        "audio": "card.wav",
        "durationMs": probe_duration_ms(result.path),
        "spoken": spoken,
        "engine": result.engine,
    }


def _synthesize_clip_beats(
    beats: list[dict],
    output_dir: Path,
    stem: str,
) -> dict | None:
    """Measured-beat TTS for a visual clip (tree / lifecycle / breakdown).

    `beats` are plain dicts with spoken + pause_after_ms (from narrate/*_script).
    Returns narration meta + writes `<stem>.wav`, or None on failure/empty.
    """
    if not beats:
        return None

    parts_dir = output_dir / f"{stem}_beats"
    parts_dir.mkdir(parents=True, exist_ok=True)
    joined: list[Path] = []
    beat_meta: list[dict] = []
    cursor_ms = 0
    engines: set[str] = set()

    try:
        for index, beat in enumerate(beats):
            spoken = speakable(beat.get("spoken") or "")
            if not spoken:
                continue
            raw = parts_dir / f"{index:03d}.wav"
            result = synthesize(spoken, raw)
            speech_ms = probe_duration_ms(raw)
            pause = int(beat.get("pause_after_ms") or 0)
            padded = pad_with_silence(raw, parts_dir / f"{index:03d}-padded.wav", pause)
            total_ms = probe_duration_ms(padded) if padded != raw else speech_ms
            beat_meta.append({
                "id": beat.get("id"),
                "summary": beat.get("summary"),
                "spoken": spoken,
                "startMs": cursor_ms,
                "speechEndMs": cursor_ms + speech_ms,
                "endMs": cursor_ms + total_ms,
                "lineRange": beat.get("lineRange"),
            })
            joined.append(padded)
            engines.add(result.engine)
            cursor_ms += total_ms
    except (TTSError, AudioAssemblyError):
        return None

    if not joined:
        return None

    wav_name = f"{stem}.wav"
    try:
        concat_wavs(joined, output_dir / wav_name)
    except AudioAssemblyError:
        return None

    return {
        "audio": wav_name,
        "durationMs": cursor_ms,
        "ttsEngine": engines.pop() if len(engines) == 1 else "+".join(sorted(engines)),
        "beats": beat_meta,
        "alignmentSource": ALIGNMENT_MEASURED,
    }


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

    card_narration = _build_card_narration(overview, output_dir)

    engines = {p["engine"] for p in placements}
    tts_engine = engines.pop() if len(engines) == 1 else "+".join(sorted(engines))

    visual_fields = _build_visual_clip_fields(record, output_dir)

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
        # Contents of the card shown before this file's walkthrough,
        # and the narration read over it.
        "fileOverview": overview,
        "cardNarration": card_narration,
        "narrationSegments": narration_segments,
        "highlightConfig": highlight_config,
        **visual_fields,
    }
    (output_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle


def _resolve_visual_stack(record: dict) -> str:
    """Prefer explicit stack / theme; never let monorepo frontend eclipse Go routes."""
    if record.get("stack"):
        return record["stack"]
    theme = record.get("visualTheme") or {}
    if theme.get("stack"):
        return theme["stack"]
    graph = record.get("visualGraph") or {}
    if graph.get("kind") == "route_tree":
        backends = ((record.get("projectType") or {}).get("backend") or [])
        if backends:
            return backends[0]
        return "go"
    if record.get("routes") or record.get("usesFiber") or record.get("middleware"):
        backends = ((record.get("projectType") or {}).get("backend") or [])
        if backends:
            return backends[0]
        return "go"
    pt = record.get("projectType") or {}
    if pt.get("frontend"):
        return pt["frontend"]
    backends = pt.get("backend") or []
    if backends:
        return backends[0]
    return "unknown"


def _silent_clip_narration(duration_ms: int) -> dict:
    """Hold a visual still when TTS is unavailable — still show the graph (Q5: only
    skip when visualAvailability says unavailable, not when TTS fails)."""
    return {
        "audio": "",
        "durationMs": max(1, int(duration_ms)),
        "ttsEngine": "none",
        "beats": [],
        "alignmentSource": "silent-hold",
    }


def _build_visual_clip_fields(record: dict, output_dir: Path) -> dict:
    """Tree / lifecycle / breakdown narration + graph payload for FullVideo.

    Q5: omit keys entirely when unavailable (no placeholder sequences).
    Q4: measured-beat TTS via the same synthesize + pad + concat path.
    When availability is present but TTS fails, still embed the graph/flows
    with a silent min-duration hold so Go Fiber (and other) chunks that have
    graphs are not dropped from the video.
    """
    from src.narrate.breakdown_script import script_breakdown_teaser
    from src.narrate.lifecycle_script import build_lifecycle_beats
    from src.narrate.tree_script import build_tree_beats
    from src.visual.availability import is_present
    from src.visual.lifecycle_builder import select_top_lifecycle_flows
    from src.visual.pipeline import build_visual_artifacts
    from src.visual.theme import theme_for_stack

    fields: dict = {}
    avail = record.get("visualAvailability") or {}
    stack = _resolve_visual_stack(record)
    theme = record.get("visualTheme") or theme_for_stack(stack)

    # Stage visuals/<stack>/<chunkId>/ sibling artifacts when possible.
    repo_visuals = Path(__file__).resolve().parents[2] / "visuals"
    try:
        build_visual_artifacts(record, repo_visuals)
    except OSError:
        pass

    if is_present(avail.get("componentTree")) and record.get("visualGraph"):
        fields["visualGraph"] = record["visualGraph"]
        fields["visualTheme"] = theme
        fields["securityFlags"] = record.get("securityFlags") or []
        fields["visualAvailability"] = avail
        tree_beats = build_tree_beats(
            record["visualGraph"], stack, avail.get("componentTree") or "available",
        )
        tree_narration = _synthesize_clip_beats(tree_beats, output_dir, "tree")
        # Min hold matches TREE_MIN_SECONDS in ComponentTreeClip.
        fields["treeNarration"] = tree_narration or _silent_clip_narration(3000)

    if is_present(avail.get("lifecycleFlow")) and record.get("lifecycleFlows"):
        top = select_top_lifecycle_flows(record["lifecycleFlows"], n=2)
        fields["lifecycleFlows"] = top
        if "visualTheme" not in fields:
            fields["visualTheme"] = theme
        life_beats: list[dict] = []
        for flow in top:
            life_beats.extend(build_lifecycle_beats(flow, stack))
        life_narration = _synthesize_clip_beats(life_beats, output_dir, "lifecycle")
        # Min hold matches LIFECYCLE_MIN_SECONDS.
        fields["lifecycleNarration"] = life_narration or _silent_clip_narration(4000)

    if is_present(avail.get("interactiveBreakdown")) and record.get("visualGraph"):
        if "visualGraph" not in fields:
            fields["visualGraph"] = record["visualGraph"]
        if "visualTheme" not in fields:
            fields["visualTheme"] = theme
        if "securityFlags" not in fields:
            fields["securityFlags"] = record.get("securityFlags") or []
        breakdown_beats = script_breakdown_teaser({
            "filePath": record.get("filePath"),
            "chunkId": record.get("chunkId"),
        })
        breakdown_narration = _synthesize_clip_beats(breakdown_beats, output_dir, "breakdown")
        # Prefer measured-beat audio (Q3/Q4); fall back to silent hold so the
        # structure graph still appears when TTS is down.
        fields["breakdownNarration"] = breakdown_narration or _silent_clip_narration(3000)

    # Reuse interactive.json Mermaid strings in Remotion (no invented edges).
    from src.visual.diagram_selection import select_diagram_plan
    from src.visual.mermaid_export import export_lifecycle_mermaid, export_mermaid

    plan = select_diagram_plan(record)
    if plan.get("video", {}).get("mermaid_in_video"):
        fields["mermaidInVideo"] = True
        graph = record.get("visualGraph")
        if graph and is_present(avail.get("componentTree")):
            m_text, _ = export_mermaid(graph)
            if m_text:
                fields["mermaid"] = m_text
        flows = record.get("lifecycleFlows") or []
        if flows and is_present(avail.get("lifecycleFlow")):
            l_text, _ = export_lifecycle_mermaid(flows)
            if l_text:
                fields["mermaidLifecycle"] = l_text

    return fields
