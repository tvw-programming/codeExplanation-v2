"""Phase 6 — text-to-speech synthesis.

Uses espeak-ng (installed locally, run offline, no network or API key)
rather than a cloud TTS vendor. This is a real, functioning TTS engine
and the generated audio is genuinely spoken and genuinely timeable —
it is not faked — but its voice is the basic robotic espeak-ng voice,
not a production-quality one. Swapping in a commercial TTS API (for a
more natural voice) is a drop-in replacement at this one function;
everything downstream (transcription, alignment, highlight frames)
works the same regardless of which engine produced the audio.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_VOICE = "en-us"
DEFAULT_WORDS_PER_MINUTE = 160  # espeak-ng's own rate, independent of the
                                # 130wpm narration-length budget in script_builder.py


class TTSError(RuntimeError):
    pass


def synthesize(text: str, out_path: Path, voice: str = DEFAULT_VOICE,
               words_per_minute: int = DEFAULT_WORDS_PER_MINUTE) -> Path:
    """Synthesizes `text` to a WAV file at out_path using espeak-ng.
    Raises TTSError if espeak-ng is not installed or fails."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
