"""FullVideo visual-clip staging: available graphs must not vanish when TTS fails."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.render.render_pipeline import _build_visual_clip_fields, _resolve_visual_stack
from src.visual.availability import is_present


def _go_record() -> dict:
    return {
        "chunkId": "server-test",
        "filePath": "api/cmd/server/main.go",
        "stack": "go",
        "usesFiber": True,
        "projectType": {"frontend": "react", "backend": ["go"]},
        "visualAvailability": {
            "componentTree": "partial",
            "lifecycleFlow": "partial",
            "interactiveBreakdown": "partial",
            "reasons": {},
        },
        "visualGraph": {
            "schemaVersion": 1,
            "kind": "route_tree",
            "rootId": "module:main",
            "nodes": [
                {"id": "module:main", "kind": "module", "label": "main"},
                {"id": "route:a", "kind": "route", "label": "GET /health"},
            ],
            "edges": [
                {"id": "e1", "kind": "routes_to", "from": "module:main", "to": "route:a"},
            ],
        },
        "lifecycleFlows": [
            {
                "id": "flow1",
                "title": "GET /health",
                "steps": [
                    {"order": 1, "action": "handler", "label": "Health"},
                    {"order": 2, "action": "response", "label": "response"},
                ],
                "meta": {"hasMiddleware": False},
            }
        ],
        "securityFlags": [],
        "visualTheme": {
            "stack": "go",
            "primary": "#00ADD8",
            "secondary": "#00C853",
            "onDark": "#00ADD8",
            "logoAssetId": "go-fiber-logo-ondark",
        },
    }


def test_resolve_stack_prefers_explicit_go_in_monorepo():
    assert _resolve_visual_stack(_go_record()) == "go"


def test_resolve_stack_route_tree_without_stack_field():
    rec = _go_record()
    del rec["stack"]
    # frontend is react in projectType — must still pick go from theme / route_tree
    assert _resolve_visual_stack(rec) == "go"


def test_visual_clips_survive_tts_failure(tmp_path: Path):
    """Regression: Go Fiber graphs existed under visuals/go/ but FullVideo skipped
    tree/lifecycle/breakdown when clip TTS returned None."""
    record = _go_record()

    with patch("src.render.render_pipeline._synthesize_clip_beats", return_value=None), patch(
        "src.visual.pipeline.build_visual_artifacts",
        return_value={"written": [], "skipped": []},
    ):
        fields = _build_visual_clip_fields(record, tmp_path)

    assert fields.get("visualGraph", {}).get("kind") == "route_tree"
    assert fields.get("treeNarration")
    assert fields["treeNarration"]["alignmentSource"] in ("estimated-beats", "silent-hold")
    assert fields["treeNarration"]["durationMs"] >= 1000
    if fields["treeNarration"]["alignmentSource"] == "estimated-beats":
        assert fields["treeNarration"]["beats"][0].get("speechEndMs", 0) > 0
    assert fields.get("lifecycleNarration")
    assert fields.get("breakdownNarration")
    assert fields.get("lifecycleFlows")
    assert is_present(fields["visualAvailability"]["componentTree"])


def test_unavailable_still_skips(tmp_path: Path):
    record = {
        "chunkId": "empty",
        "filePath": "x.go",
        "stack": "go",
        "visualAvailability": {
            "componentTree": "unavailable",
            "lifecycleFlow": "unavailable",
            "interactiveBreakdown": "unavailable",
            "reasons": {"componentTree": "no_fiber_routes_extracted"},
        },
        "visualGraph": None,
        "lifecycleFlows": [],
    }
    with patch(
        "src.visual.pipeline.build_visual_artifacts",
        return_value={"written": [], "skipped": []},
    ):
        fields = _build_visual_clip_fields(record, tmp_path)
    assert fields == {}
