"""Breakdown structure beats for component_tree graphs."""

from __future__ import annotations

import json
from pathlib import Path

from src.narrate.breakdown_script import build_breakdown_beats, script_breakdown_teaser

ROOT = Path(__file__).resolve().parents[1]
PROFILE_GRAPH = ROOT / "visuals" / "react" / "alumni-06f407dc" / "visualGraph.json"


def test_teaser_copy_file_scoped():
    beats = script_breakdown_teaser({"filePath": "src/features/alumni/ProfilePage.tsx"})
    assert "ProfilePage.tsx" in beats[0]["spoken"]
    assert "checkout" not in beats[0]["spoken"].lower()


def test_profile_breakdown_beats_grounded():
    graph = json.loads(PROFILE_GRAPH.read_text(encoding="utf-8"))
    beats = build_breakdown_beats(
        graph,
        {"filePath": "src/features/alumni/ProfilePage.tsx", "chunkId": "alumni-06f407dc"},
    )
    assert len(beats) >= 3
    spoken_joined = " ".join(b["spoken"] for b in beats)
    assert "8 mount edges" in spoken_joined
    assert "SchemaFormWrapper" in spoken_joined
    assert "duplicate mount line" in spoken_joined
    assert "Typography" in spoken_joined
    for child in ("Alert", "Card", "Snackbar", "Stack"):
        assert child in spoken_joined