"""Honesty matrix: every multi-stack-plan technology is wired through attach_visuals."""

from __future__ import annotations

from src.visual.pipeline import SHIPPED_STACKS, attach_visuals, _infer_stack
from src.visual.theme import theme_for_stack


# Plan order from docs/visual-diagrams-multi-stack-plan.md
PLAN_STACKS = [
    "react",
    "angular",
    "vue",
    "solid",
    "qwik",
    "javascript",
    "python",
    "go",  # Go Fiber
    "spring_boot",
    "express",
    "rust",
]


def test_all_plan_stacks_are_shipped():
    for stack in PLAN_STACKS:
        assert stack in SHIPPED_STACKS, f"{stack} missing from SHIPPED_STACKS"


def test_each_stack_has_theme_and_honest_empty_attach():
    for stack in PLAN_STACKS:
        theme = theme_for_stack(stack)
        assert theme.get("primary"), f"theme missing primary for {stack}"
        assert theme.get("logoAssetId"), f"theme missing logo for {stack}"
        # Empty record: never invent edges. Envelope must exist.
        record = attach_visuals(
            {
                "chunkId": f"{stack}-empty",
                "filePath": f"empty.{stack}",
                "stack": stack,
                "projectType": {"frontend": None, "backend": []},
                "confidence": 1,
                "notes": None,
            },
            stack=stack,
        )
        avail = record["visualAvailability"]
        assert "componentTree" in avail
        assert "lifecycleFlow" in avail
        assert "interactiveBreakdown" in avail
        assert "reasons" in avail
        graph = record.get("visualGraph")
        if graph is None:
            assert avail["componentTree"] == "unavailable"
        else:
            # If a builder returned a graph, it must have structural edges.
            assert graph.get("edges"), f"{stack} returned edge-less graph"


def test_infer_stack_monorepo_go_routes():
    stack = _infer_stack({
        "projectType": {"frontend": "react", "backend": ["go"]},
        "routes": [{"method": "GET", "path": "/x"}],
        "usesFiber": True,
    })
    assert stack == "go"
