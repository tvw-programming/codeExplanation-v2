"""End-card teaser beats — file-scoped, not business-journey language."""

from __future__ import annotations

from pathlib import Path

from src.render.script_text import strip_visual_tokens


def script_breakdown_teaser(chunk_meta: dict) -> list[dict]:
    file_path = chunk_meta.get("filePath") or ""
    name = Path(file_path).name if file_path else (chunk_meta.get("chunkId") or "this file")
    spoken = f"Here is the structure graph for {name}."
    clean, _ = strip_visual_tokens(spoken)
    return [{
        "id": "breakdown-teaser",
        "summary": f"Graph for {name}",
        "spoken": clean,
        # Extra pause so Remotion's +2s still hold reads as intentional dwell.
        "pause_after_ms": 400,
    }]


def script_react_breakdown_teaser(meta: dict) -> list[dict]:
    return script_breakdown_teaser(meta)


def script_go_fiber_breakdown_teaser(meta: dict) -> list[dict]:
    return script_breakdown_teaser(meta)
