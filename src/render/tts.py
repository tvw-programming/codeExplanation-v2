"""Phase 6 — text-to-speech synthesis.

Two engines, both local/offline (no network call at render time, no API
key), tried in order:

1. Piper (https://github.com/OHF-voice/piper1-gpl), using the Indian
   English voice from navgurukul-ai-labs/text-to-speech-en-IN-piper on
   Hugging Face (LJSpeech-based, so a female voice) — used whenever its
   model files are present. run-local.sh downloads them once via
   scripts/ensure_piper_voice.py (a one-time ~64MB fetch, cached
   locally after that, the same shape as `npx remotion browser ensure`
   or `npm install` already are) into PIPER_VOICE_DIR below. This is
   the default narration voice.
2. espeak-ng (a system binary, always available once installed) — the
   always-on fallback when the Piper model isn't present or Piper
   itself fails, so narration still works even before/without that
   one-time download (e.g. this project's own sandboxed dev
   environment, which cannot reach Hugging Face to fetch it).

Licensing note: the Piper engine (piper-tts) is GPL-3.0-or-later, and
the Indian-English voice model is tagged AGPL-3.0 by its publisher.
Both are invoked here only as external subprocesses (never imported as
a library) producing a local WAV file — the same arm's-length
relationship this project already has with espeak-ng and ffmpeg — but
that doesn't erase the licensing terms, so it's called out here
explicitly rather than left implicit.

Either way the generated audio is genuinely spoken and genuinely
timeable — it is not faked. Which engine actually produced a given
chunk's narration is recorded honestly in its render bundle
(see render_pipeline.py's "ttsEngine" field), the same way
alignmentSource records whether word timing came from real
transcription or an estimate.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPER_VOICE_DIR = REPO_ROOT / ".cache" / "piper-voices" / "en_IN"
PIPER_MODEL_PATH = PIPER_VOICE_DIR / "en_IN-ljspeech.onnx"
PIPER_CONFIG_PATH = PIPER_VOICE_DIR / "en_IN-ljspeech.onnx.json"
PIPER_ENGINE_ID = "piper:en_IN-ljspeech"

ESPEAK_DEFAULT_VOICE = "en-us"
ESPEAK_DEFAULT_WORDS_PER_MINUTE = 160  # espeak-ng's own rate, independent of the
                                       # 130wpm narration-length budget in script_builder.py
ESPEAK_ENGINE_ID = f"espeak-ng:{ESPEAK_DEFAULT_VOICE}"


class TTSError(RuntimeError):
    pass


@dataclass
class SynthesisResult:
    path: Path
    engine: str   # e.g. "piper:en_IN-ljspeech" or "espeak-ng:en-us" — see
                  # render_pipeline.py's bundle["ttsEngine"]


def piper_voice_available() -> bool:
    return PIPER_MODEL_PATH.is_file() and PIPER_CONFIG_PATH.is_file()


def _synthesize_piper(text: str, out_path: Path) -> Path:
    try:
        result = subprocess.run(
            ["piper", "-m", str(PIPER_MODEL_PATH), "-c", str(PIPER_CONFIG_PATH),
             "-f", str(out_path)],
            input=text, capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TTSError(f"piper is not available or timed out: {exc}") from exc

    if result.returncode != 0:
        raise TTSError(f"piper failed (exit {result.returncode}): {result.stderr}")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise TTSError("piper reported success but produced no audio file.")
    return out_path


def _synthesize_espeak(text: str, out_path: Path, voice: str = ESPEAK_DEFAULT_VOICE,
                        words_per_minute: int = ESPEAK_DEFAULT_WORDS_PER_MINUTE) -> Path:
    try:
        result = subprocess.run(
            ["espeak-ng", "-v", voice, "-s", str(words_per_minute), "-w", str(out_path), text],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TTSError(f"espeak-ng is not available or timed out: {exc}") from exc

    if result.returncode != 0:
        raise TTSError(f"espeak-ng failed (exit {result.returncode}): {result.stderr}")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise TTSError("espeak-ng reported success but produced no audio file.")
    return out_path


def synthesize(text: str, out_path: Path) -> SynthesisResult:
    """Synthesizes `text` to a WAV file at out_path, preferring the
    Piper Indian-English voice when its model has been downloaded and
    falling back to espeak-ng otherwise. Raises TTSError only if
    *both* fail (or neither is available)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if piper_voice_available():
        try:
            return SynthesisResult(_synthesize_piper(text, out_path), PIPER_ENGINE_ID)
        except TTSError:
            pass  # fall through to espeak-ng below

    path = _synthesize_espeak(text, out_path)
    return SynthesisResult(path, ESPEAK_ENGINE_ID)
