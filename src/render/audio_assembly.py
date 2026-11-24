"""Phase 6 — turns a list of narration beats into one narration track,
with real silence between them.

The pause after a beat has to exist in the audio itself: the video is
one continuous soundtrack per chunk, so "wait two seconds here" can
only mean two seconds of actual samples. Synthesising each beat on its
own and padding it is also what makes the timing exact — each beat's
start and end are measured from the rendered audio rather than guessed
at by spreading words evenly over a total duration, which is what the
highlight and the narration list are then driven from.

ffmpeg does the padding and the joining. It is already a hard
dependency of this phase (duration probing uses ffprobe), so this adds
no new requirement.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class AudioAssemblyError(RuntimeError):
    pass


@dataclass
class AssembledPart:
    """One beat's place in the finished track."""
    index: int
    start_ms: int
    end_ms: int          # including the pause that follows it
    speech_end_ms: int   # where the speech itself stops
    engine: str


def probe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    try:
        return round(float(json.loads(result.stdout)["format"]["duration"]) * 1000)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return 0


def pad_with_silence(source: Path, destination: Path, pause_ms: int) -> Path:
    """Append `pause_ms` of silence. apad matches the input's own sample
    rate and channel layout, so the padded parts stay concatenable
    without resampling."""
    if pause_ms <= 0:
        return source
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
         "-af", f"apad=pad_dur={pause_ms / 1000:.3f}",
         "-c:a", "pcm_s16le", str(destination)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode != 0 or not destination.is_file():
        raise AudioAssemblyError(
            f"ffmpeg could not pad {source.name} with {pause_ms}ms of silence: "
            f"{result.stderr.strip()[:300]}"
        )
    return destination


def silence_wav(duration_ms: int, destination: Path, sample_rate: int = 22050) -> Path:
    """Write a silent PCM WAV of the given length (clip TTS estimate fallback)."""
    if duration_ms <= 0:
        raise AudioAssemblyError("silence_wav: duration_ms must be positive")
    seconds = f"{duration_ms / 1000:.3f}"
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", seconds,
            "-c:a", "pcm_s16le", str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0 or not destination.is_file():
        raise AudioAssemblyError(
            f"ffmpeg could not write {duration_ms}ms of silence: "
            f"{result.stderr.strip()[:300]}"
        )
    return destination


def concat_wavs(parts: list[Path], destination: Path) -> Path:
    if not parts:
        raise AudioAssemblyError("No audio parts to join.")
    if len(parts) == 1:
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(parts[0]),
             "-c:a", "pcm_s16le", str(destination)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode != 0:
            raise AudioAssemblyError(f"ffmpeg could not write {destination.name}: "
                                     f"{result.stderr.strip()[:300]}")
        return destination

    list_file = destination.with_suffix(".concat.txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in parts) + "\n", encoding="utf-8",
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c:a", "pcm_s16le", str(destination)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    list_file.unlink(missing_ok=True)
    if result.returncode != 0 or not destination.is_file():
        raise AudioAssemblyError(
            f"ffmpeg could not join {len(parts)} narration parts: "
            f"{result.stderr.strip()[:300]}"
        )
    return destination
