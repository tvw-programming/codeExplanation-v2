"""Phase 6 — orchestrates one chunk's narration record + NarrationScript
into a render bundle: audio, word-aligned captions, and a frame-based
highlight config, ready for the Remotion project (render-app/) to
render.

Alignment source is always recorded honestly: "whisper-cpp" when the
real tools/transcribe.mjs run succeeded, or "estimated" when it could
not run (see estimated_alignment.py for why) — and every cue built
from an estimated alignment is forced to assumed=True, never presented
as verified timing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.narrate.script_builder import NarrationScript
from .script_text import concat_beats, strip_visual_tokens
from .tts import synthesize, TTSError
from .timing import TranscriptWord, TimedCue, align_cues_to_words
from .estimated_alignment import build_estimated_words
from .highlight_config import build_highlight_config

RENDER_APP_DIR = Path(__file__).resolve().parents[2] / "render-app"
TRANSCRIBE_SCRIPT = RENDER_APP_DIR / "scripts" / "transcribe.mjs"


def _probe_duration_ms(wav_path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    try:
        return round(float(result.stdout.strip()) * 1000)
    except (ValueError, AttributeError):
        return 0


def _try_real_transcription(wav_path: Path, out_json: Path) -> list[TranscriptWord] | None:
    if not TRANSCRIBE_SCRIPT.is_file():
        return None
    result = subprocess.run(
        ["node", str(TRANSCRIBE_SCRIPT), str(wav_path), str(out_json)],
        capture_output=True, text=True, timeout=600, check=False, cwd=str(RENDER_APP_DIR),
    )
    if result.returncode != 0 or not out_json.is_file():
        return None
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return [TranscriptWord(word=w["word"], start_ms=w["startMs"], end_ms=w["endMs"])
            for w in data.get("words", [])]


def build_render_bundle(script: NarrationScript, output_dir: Path, fps: int = 30) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    full_text = concat_beats(script.purpose, script.connections, script.flow, script.recap)
    clean_text, cue_word_index = strip_visual_tokens(full_text)

    wav_path = output_dir / "narration.wav"
    try:
        synthesize(clean_text, wav_path)
    except TTSError as exc:
        return {"chunkId": script.chunk_id, "error": f"TTS failed: {exc}"}

    duration_ms = _probe_duration_ms(wav_path)

    transcript_json = output_dir / "transcript.json"
    words = _try_real_transcription(wav_path, transcript_json)
    if words is not None:
        alignment_source = "whisper-cpp"
    else:
        words = build_estimated_words(clean_text, duration_ms)
        alignment_source = "estimated"

    timed_cues: list[TimedCue] = align_cues_to_words(script.visual_cues, cue_word_index, words)
    if alignment_source == "estimated":
        # The underlying word timings themselves are not verified, so no
        # cue built from them can be presented as verified either,
        # regardless of whether its word index happened to be in range.
        for cue in timed_cues:
            cue.assumed = True
            cue.note = (cue.note or "") + " Word timing is estimated (even spacing across " \
                                            "measured audio duration), not from real transcription."

    highlight_config = build_highlight_config(timed_cues, fps)

    bundle = {
        "chunkId": script.chunk_id,
        "durationMs": duration_ms,
        "alignmentSource": alignment_source,
        "narrationAudio": str(wav_path),
        "cleanText": clean_text,
        "highlightConfig": highlight_config,
    }
    (output_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle
