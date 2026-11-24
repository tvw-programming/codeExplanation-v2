#!/usr/bin/env python3
"""Re-synthesize tree/breakdown clip narration on staged chunk bundles.

FullVideo needs measured clip beats (speechEndMs) for ComponentTree gating and
VisualBreakdownStill L3 bullets. Older staging runs — or TTS failures during
backend — can leave silent-hold metadata with empty beats while tree.wav is
missing or stale. run-local.sh invokes this after sync_manifest_phase_style.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.narrate.breakdown_script import build_breakdown_beats  # noqa: E402
from src.narrate.tree_script import build_tree_beats  # noqa: E402
from src.render.render_pipeline import (  # noqa: E402
    _clip_narration_from_beats,
    clip_narration_needs_repair,
)
from src.visual.availability import is_present  # noqa: E402

CHUNKS_DIR = REPO_ROOT / "render-app" / "public" / "chunks"


def _chunk_dirs() -> list[Path]:
    if not CHUNKS_DIR.is_dir():
        return []
    found: list[Path] = []
    for bundle_path in CHUNKS_DIR.glob("*/*/bundle.json"):
        found.append(bundle_path.parent)
    legacy = CHUNKS_DIR / "sample-chunk"
    if (legacy / "bundle.json").is_file():
        found.append(legacy)
    # Deduplicate stable order
    seen: set[Path] = set()
    ordered: list[Path] = []
    for d in sorted(found, key=lambda p: str(p)):
        if d in seen:
            continue
        seen.add(d)
        ordered.append(d)
    return ordered


def _stack_for_chunk(chunk_dir: Path, record: dict) -> str:
    if record.get("stack"):
        return str(record["stack"])
    theme = record.get("visualTheme") or {}
    if theme.get("stack"):
        return str(theme["stack"])
    parent = chunk_dir.parent.name
    if parent != "chunks" and (CHUNKS_DIR / parent / "manifest.json").is_file():
        return parent
    graph = record.get("visualGraph") or {}
    if graph.get("kind") == "route_tree":
        return "go"
    return "react"


def repair_chunk(chunk_dir: Path) -> tuple[bool, list[str]]:
    bundle_path = chunk_dir / "bundle.json"
    try:
        record = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, []

    graph = record.get("visualGraph")
    if not graph:
        return False, []

    avail = record.get("visualAvailability") or {}
    stack = _stack_for_chunk(chunk_dir, record)
    notes: list[str] = []
    changed = False
    chunk_meta = {
        "filePath": record.get("filePath"),
        "chunkId": record.get("chunkId") or chunk_dir.name,
    }

    tree = record.get("treeNarration")
    if is_present(avail.get("componentTree")) and clip_narration_needs_repair(tree):
        beats = build_tree_beats(
            graph, stack, avail.get("componentTree") or "available",
        )
        rebuilt = _clip_narration_from_beats(beats, chunk_dir, "tree", min_hold_ms=3000)
        if rebuilt:
            record["treeNarration"] = rebuilt
            for wav in ("tree.wav",):
                if rebuilt.get("audio") and (chunk_dir / str(rebuilt["audio"])).is_file():
                    break
            notes.append("tree")
            changed = True

    breakdown = record.get("breakdownNarration")
    if is_present(avail.get("interactiveBreakdown")) and clip_narration_needs_repair(
        breakdown,
    ):
        beats = build_breakdown_beats(graph, chunk_meta)
        rebuilt = _clip_narration_from_beats(
            beats, chunk_dir, "breakdown", min_hold_ms=3000,
        )
        if rebuilt:
            record["breakdownNarration"] = rebuilt
            notes.append("breakdown")
            changed = True

    if changed:
        bundle_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return changed, notes


def main() -> int:
    dirs = _chunk_dirs()
    if not dirs:
        print("[repair] No staged chunk bundles under render-app/public/chunks/")
        return 0

    touched = 0
    for chunk_dir in dirs:
        changed, parts = repair_chunk(chunk_dir)
        if changed:
            touched += 1
            label = ", ".join(parts)
            print(f"[repair] {chunk_dir.relative_to(REPO_ROOT)} ({label})")

    print(f"[repair] Updated clip narration on {touched} chunk(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())