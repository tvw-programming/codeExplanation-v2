"""Mermaid structure + lifecycle exporters and docs packaging."""

from __future__ import annotations

from pathlib import Path

from src.visual.architecture_docs import write_architecture_markdown
from src.visual.diagram_selection import select_diagram_plan, VIDEO_CHAPTER_ORDER
from src.visual.mermaid_export import export_lifecycle_mermaid, export_mermaid
from src.visual.package_interactive import package_interactive_breakdown
from src.visual.pipeline import attach_visuals, build_visual_artifacts


def test_export_mermaid_assumed_dashes_and_skip_passes_prop():
    graph = {
        "nodes": [
            {"id": "a", "label": "Parent"},
            {"id": "b", "label": "Child"},
            {"id": "c", "label": "AssumedChild"},
        ],
        "edges": [
            {"from": "a", "to": "b", "kind": "mounts", "assumed": False},
            {"from": "a", "to": "c", "kind": "mounts", "assumed": True},
            {"from": "a", "to": "b", "kind": "passes_prop", "assumed": False},
        ],
    }
    text, reason = export_mermaid(graph)
    assert reason is None
    assert text is not None
    assert "flowchart TD" in text
    assert "a --> b" in text
    assert "a -.-> c" in text
    assert "passes_prop" not in text


def test_export_mermaid_skip_reasons():
    assert export_mermaid(None) == (None, "no_graph")
    assert export_mermaid({"nodes": [], "edges": []})[1] == "empty"
    big = {"nodes": [{"id": str(i), "label": str(i)} for i in range(41)], "edges": []}
    assert export_mermaid(big)[1] == "too_large"


def test_export_lifecycle_mermaid_sequence_and_assumed_notes():
    flows = [
        {
            "id": "flow:1",
            "title": "GET /api/v1/alumni",
            "trigger": "GET /api/v1/alumni",
            "assumed": True,
            "steps": [
                {"order": 1, "action": "middleware", "label": "cors.New", "assumed": True},
                {"order": 2, "action": "handler", "label": "List", "assumed": False},
            ],
        }
    ]
    text, reason = export_lifecycle_mermaid(flows)
    assert reason is None
    assert text is not None
    assert text.startswith("sequenceDiagram")
    assert "->>" in text
    assert "Note over" in text
    assert "assumed" in text
    assert export_lifecycle_mermaid([])[1] == "empty"
    assert export_lifecycle_mermaid(None)[1] == "empty"


def test_build_visual_clip_fields_embeds_mermaid_strings(tmp_path):
    from src.render.render_pipeline import _build_visual_clip_fields

    record = {
        "chunkId": "demo",
        "filePath": "src/Demo.tsx",
        "stack": "react",
        "visualAvailability": {
            "componentTree": "available",
            "lifecycleFlow": "unavailable",
            "interactiveBreakdown": "available",
        },
        "visualGraph": {
            "nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
            "edges": [{"from": "n1", "to": "n2", "kind": "mounts"}],
        },
        "lifecycleFlows": [],
    }
    fields = _build_visual_clip_fields(record, tmp_path)
    assert fields.get("mermaidInVideo") is True
    assert fields.get("mermaid") and "flowchart TD" in fields["mermaid"]
    assert "visualGraph" in fields


def test_select_diagram_plan_preserves_q1_order_and_skips():
    record = {
        "visualAvailability": {
            "componentTree": "available",
            "lifecycleFlow": "unavailable",
            "interactiveBreakdown": "available",
            "reasons": {"lifecycleFlow": "no_handlers"},
        },
        "visualGraph": {
            "nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
            "edges": [{"from": "n1", "to": "n2", "kind": "mounts"}],
        },
        "lifecycleFlows": [],
    }
    plan = select_diagram_plan(record)
    assert plan["videoChapterOrder"] == list(VIDEO_CHAPTER_ORDER)
    assert plan["video"]["mermaid_in_video"] is True
    assert plan["preferRemotionForVideo"] is True
    assert "flowchart_td" in plan["docsDiagrams"]
    assert "sequence" not in plan["docsDiagrams"]
    assert plan["lifecycle"]["include"] is False


def test_architecture_md_and_interactive_lifecycle_fields(tmp_path: Path):
    record = attach_visuals({
        "chunkId": "demo",
        "filePath": "src/Demo.tsx",
        "stack": "react",
        "fidelity": "regex",
        "jsxMounts": [
            {"parent": "Demo", "child": "Button", "line": 10, "assumed": False, "props": []},
        ],
        "eventHandlers": [
            {"name": "onSave", "lineRange": [20, 40], "assumed": False},
        ],
        "hooks": [{"kind": "useState", "name": "useState", "line": 5, "owner": "Demo"}],
        "apiCalls": [{"method": "POST", "url": "/api/x", "line": 25, "assumed": False}],
        "projectType": {"frontend": "react", "backend": []},
        "confidence": 0.8,
    }, stack="react")

    payload = package_interactive_breakdown(record)
    assert payload is not None
    assert payload.get("mermaid")
    assert "flowchart TD" in payload["mermaid"]
    # Lifecycle may or may not export depending on extracted flows
    if record.get("lifecycleFlows"):
        assert "mermaidLifecycle" in payload
        if payload["mermaidLifecycle"]:
            assert payload["mermaidLifecycle"].startswith("sequenceDiagram")

    summary = build_visual_artifacts(record, tmp_path / "visuals")
    arch = tmp_path / "visuals" / "react" / "demo" / "architecture.md"
    assert arch.is_file(), summary
    body = arch.read_text(encoding="utf-8")
    assert "```mermaid" in body
    assert "Structure" in body or "Lifecycle" in body
    assert "## Honesty" in body
    assert "Fidelity note" in body
    assert "Source of truth" in body
    assert "visualGraph" in body
    assert "-.->" in body
    payload = package_interactive_breakdown(record)
    assert payload is not None
    assert payload.get("mermaidHonesty", {}).get("assumedEdges") == "-.->"
    assert payload["mermaidHonesty"].get("fidelity") == "regex"
    assert payload["mermaidHonesty"].get("sourceOfTruth") == [
        "visualGraph", "lifecycleFlows",
    ]
    assert payload["mermaidHonesty"].get("neverInvent") is True

    # Unavailable → no architecture.md
    empty = attach_visuals({
        "chunkId": "empty",
        "filePath": "Empty.tsx",
        "stack": "react",
        "jsxMounts": [],
        "eventHandlers": [],
        "hooks": [],
        "apiCalls": [],
        "projectType": {"frontend": "react", "backend": []},
        "confidence": 0.2,
    }, stack="react")
    assert write_architecture_markdown(empty, tmp_path / "empty-dest") is None
