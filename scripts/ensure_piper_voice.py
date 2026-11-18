"""Helper for run-local.sh (backend step): makes sure the Piper
Indian-English narration voice (see src/render/tts.py) is downloaded
and cached locally, so synthesis can prefer it over the espeak-ng
fallback.

One-time ~64MB download from Hugging Face
(navgurukul-ai-labs/text-to-speech-en-IN-piper, LJSpeech-based, so a
female voice), cached under .cache/piper-voices/en_IN/ — the same
shape as `npm install` or `npx remotion browser ensure` already are
elsewhere in this project: a setup-time fetch, never a per-render
network call.

Deliberately non-fatal: if Hugging Face can't be reached (this
project's own sandboxed dev environment blocks it; some users'
networks might too) or the download fails partway, this prints a
warning and exits 0 — src/render/tts.py's synthesize() already falls
back to espeak-ng whenever these files aren't present, so narration
still works either way.

Usage:
    python scripts/ensure_piper_voice.py
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.render.tts import PIPER_CONFIG_PATH, PIPER_MODEL_PATH, PIPER_VOICE_DIR  # noqa: E402

HF_BASE = (
    "https://huggingface.co/navgurukul-ai-labs/text-to-speech-en-IN-piper/resolve/main/"
    "en_IN-dataset=spicor-english-base=ljspeech-epochs=1089.onnx"
)
FILES = {
    PIPER_MODEL_PATH: HF_BASE,
    PIPER_CONFIG_PATH: HF_BASE + ".json",
}


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(tmp, "wb") as f:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)


def main() -> int:
    if PIPER_MODEL_PATH.is_file() and PIPER_CONFIG_PATH.is_file():
        print(f"[piper-voice] Already downloaded -> {PIPER_VOICE_DIR}")
        return 0

    PIPER_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    print("[piper-voice] Downloading the Indian-English narration voice "
          "(one-time, ~64MB) ...")
    try:
        for dest, url in FILES.items():
            if dest.is_file():
                continue
            print(f"[piper-voice]   {url}")
            _download(url, dest)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"[piper-voice] Could not download the Indian-English voice ({exc}). "
              "Narration will use the espeak-ng fallback voice instead — this is "
              "not fatal. Re-run run-local.sh later (e.g. once this network is "
              "reachable) to pick it up.", file=sys.stderr)
        # Don't leave a half-downloaded pair of files around.
        for dest in FILES:
            dest.unlink(missing_ok=True)
        return 0

    print(f"[piper-voice] Downloaded -> {PIPER_VOICE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
