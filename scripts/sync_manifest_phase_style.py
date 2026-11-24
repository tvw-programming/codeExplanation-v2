#!/usr/bin/env python3
"""Embed video.phaseStyle from pipeline.config.yaml into staged Remotion manifests.

FullVideo / StackVideo read phaseStyle from chunks/manifest.json at render time
(calculateMetadata). A render-only rerun keeps old chunk bundles on disk, so
manifests still carry the phaseStyle from the last staging run. Call this before
Remotion render so pipeline.config.yaml changes apply without re-staging chunks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.load_config import ConfigError, load_config  # noqa: E402

CHUNKS_DIR = REPO_ROOT / "render-app" / "public" / "chunks"
CLIP_PHASE_KEYS = (
    "fileCard",
    "componentTree",
    "lifecycle",
    "chunkView",
    "visualBreakdown",
)


def _patch_manifest(path: Path, phase_style: dict[str, str]) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if "chunkIds" not in data and "stack" not in data:
        return False
    data["phaseStyle"] = dict(phase_style)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def sync_manifests(config_path: Path | None = None) -> tuple[int, dict[str, str]]:
    config_path = config_path or (REPO_ROOT / "pipeline.config.yaml")
    config = load_config(config_path)
    phase_style = config.phase_style

    if not CHUNKS_DIR.is_dir():
        return 0, phase_style

    updated = 0
    combined = CHUNKS_DIR / "manifest.json"
    if combined.is_file() and _patch_manifest(combined, phase_style):
        updated += 1

    for path in sorted(CHUNKS_DIR.glob("*/manifest.json")):
        if path == combined:
            continue
        if _patch_manifest(path, phase_style):
            updated += 1

    return updated, phase_style


def main() -> int:
    config_path = REPO_ROOT / "pipeline.config.yaml"
    if not config_path.is_file():
        print(
            "[sync] No pipeline.config.yaml — cannot sync phaseStyle into manifests.",
            file=sys.stderr,
        )
        return 1

    try:
        updated, phase_style = sync_manifests(config_path)
    except ConfigError as exc:
        print(f"[sync] Config error: {exc}", file=sys.stderr)
        return 1

    clip_modes = ", ".join(f"{k}={phase_style[k]}" for k in CLIP_PHASE_KEYS)
    print(f"[sync] phaseStyle from config → manifests ({clip_modes})")

    if all(phase_style[k] == "classic" for k in CLIP_PHASE_KEYS):
        print(
            "[sync] All five clip phases are classic — L1–L4 motion stays off.",
            flush=True,
        )
        print(
            "[sync] Set video.phaseStyle.* to fancy in pipeline.config.yaml "
            "(see pipeline.config.example.yaml), then re-run render.",
            flush=True,
        )
    elif updated == 0:
        print(
            "[sync] No staged manifests under render-app/public/chunks/ — "
            "run the backend staging step first.",
            file=sys.stderr,
        )
        return 1

    print(f"[sync] Updated {updated} manifest(s) under render-app/public/chunks/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())