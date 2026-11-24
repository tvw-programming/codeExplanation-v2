"""breakdown_narration_needs_repair catches pre-#41 one-beat teaser bundles."""

from __future__ import annotations

import json
from pathlib import Path

from src.render.render_pipeline import breakdown_narration_needs_repair

ROOT = Path(__file__).resolve().parents[1]
PROFILE_GRAPH = ROOT / "visuals" / "react" / "alumni-06f407dc" / "visualGraph.json"
META = {
    "filePath": "src/features/alumni/ProfilePage.tsx",
    "chunkId": "alumni-06f407dc",
}


def test_one_beat_teaser_still_needs_repair():
    graph = json.loads(PROFILE_GRAPH.read_text(encoding="utf-8"))
    teaser = {
        "audio": "breakdown.wav",
        "alignmentSource": "measured-beats",
        "beats": [{"speechEndMs": 2200, "startMs": 0, "endMs": 2600}],
        "durationMs": 2600,
    }
    assert breakdown_narration_needs_repair(graph, META, teaser)


def test_rich_breakdown_does_not_need_repair():
    graph = json.loads(PROFILE_GRAPH.read_text(encoding="utf-8"))
    rich = {
        "audio": "breakdown.wav",
        "alignmentSource": "measured-beats",
        "beats": [{"speechEndMs": 1000 + i * 500, "startMs": i * 500, "endMs": 1200 + i * 500} for i in range(5)],
        "durationMs": 8000,
    }
    assert not breakdown_narration_needs_repair(graph, META, rich)