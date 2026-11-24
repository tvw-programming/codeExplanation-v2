"""Clip narration repair + estimated beat fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.narrate.breakdown_script import build_breakdown_beats
from src.narrate.tree_script import build_tree_beats
from src.render.render_pipeline import (
    ALIGNMENT_ESTIMATED,
    _clip_narration_from_beats,
    clip_narration_needs_repair,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_GRAPH = ROOT / "visuals" / "react" / "alumni-06f407dc" / "visualGraph.json"


@pytest.fixture
def profile_graph() -> dict:
    return json.loads(PROFILE_GRAPH.read_text(encoding="utf-8"))


def test_clip_narration_needs_repair_detects_silent_hold():
    assert clip_narration_needs_repair({"alignmentSource": "silent-hold", "beats": []})
    assert not clip_narration_needs_repair({
        "alignmentSource": "measured-beats",
        "beats": [{"speechEndMs": 1200, "startMs": 0, "endMs": 1500}],
    })


def test_estimated_tree_beats_when_tts_unavailable(profile_graph, tmp_path: Path):
    beats = build_tree_beats(profile_graph, "react", "available")
    with patch("src.render.render_pipeline._synthesize_clip_beats", return_value=None):
        narr = _clip_narration_from_beats(beats, tmp_path, "tree")
    assert narr is not None
    assert narr["alignmentSource"] == ALIGNMENT_ESTIMATED
    assert narr["beats"]
    assert narr["beats"][0]["speechEndMs"] > 0
    if narr.get("audio"):
        assert (tmp_path / narr["audio"]).is_file()


def test_estimated_breakdown_beats_for_profile(profile_graph, tmp_path: Path):
    beats = build_breakdown_beats(
        profile_graph,
        {"filePath": "src/features/alumni/ProfilePage.tsx", "chunkId": "alumni-06f407dc"},
    )
    assert len(beats) >= 3
    with patch("src.render.render_pipeline._synthesize_clip_beats", return_value=None):
        narr = _clip_narration_from_beats(beats, tmp_path, "breakdown")
    assert narr is not None
    assert len(narr["beats"]) >= 3
    assert narr["beats"][0]["speechEndMs"] > 0