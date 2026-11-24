"""End-card structure graph beats — file-scoped, not business-journey language."""

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


def build_breakdown_beats(visual_graph: dict | None, chunk_meta: dict) -> list[dict]:
    """Measured beats for VisualBreakdownStill — richer than the one-line teaser."""
    beats = list(script_breakdown_teaser(chunk_meta))
    if not visual_graph or visual_graph.get("kind") != "component_tree":
        return beats

    nodes = {n["id"]: n for n in visual_graph.get("nodes") or []}
    root_id = visual_graph.get("rootId")
    root = nodes.get(root_id) or {}
    root_label = root.get("label") or "this component"
    mounts = [
        e for e in visual_graph.get("edges") or []
        if e.get("kind") == "mounts" and e.get("from") == root_id
    ]

    child_labels: list[str] = []
    for e in mounts:
        child = nodes.get(e.get("to") or "", {})
        label = child.get("label")
        if label and label not in child_labels:
            child_labels.append(label)

    if mounts:
        spoken = (
            f"{root_label} has {len(mounts)} mount edges to child components in this graph."
        )
        clean, _ = strip_visual_tokens(spoken)
        beats.append({
            "id": "breakdown-mount-count",
            "summary": "Mount edges",
            "spoken": clean,
            "pause_after_ms": 380,
        })

    if child_labels:
        listed = ", ".join(child_labels[:8])
        spoken = f"Mounted children include {listed}."
        clean, _ = strip_visual_tokens(spoken)
        beats.append({
            "id": "breakdown-children",
            "summary": "Mounted children",
            "spoken": clean,
            "pause_after_ms": 420,
        })

    by_target: dict[str, list[str]] = {}
    for e in mounts:
        to_id = e.get("to")
        if not to_id:
            continue
        by_target.setdefault(to_id, []).append(e.get("id") or "")

    for to_id, edge_ids in by_target.items():
        if len(edge_ids) < 2:
            continue
        child_label = nodes.get(to_id, {}).get("label") or "a child"
        spoken = (
            f"The breakdown diagram hides one duplicate mount line to {child_label} "
            "for clarity."
        )
        clean, _ = strip_visual_tokens(spoken)
        beats.append({
            "id": "breakdown-dedupe-edge",
            "summary": "Diagram clarity",
            "spoken": clean,
            "pause_after_ms": 360,
        })
        break

    if any(n.get("label") == "SchemaFormWrapper" for n in nodes.values()):
        spoken = "SchemaFormWrapper is a direct mount from the page root in this tree."
        clean, _ = strip_visual_tokens(spoken)
        beats.append({
            "id": "breakdown-schemaform",
            "summary": "SchemaFormWrapper",
            "spoken": clean,
            "pause_after_ms": 320,
        })

    return beats[:6]


def script_react_breakdown_teaser(meta: dict) -> list[dict]:
    return script_breakdown_teaser(meta)


def script_go_fiber_breakdown_teaser(meta: dict) -> list[dict]:
    return script_breakdown_teaser(meta)