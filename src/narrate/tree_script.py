"""1–3 short orientation beats from a visualGraph (component_tree or route_tree)."""

from __future__ import annotations

from src.render.script_text import strip_visual_tokens


def build_tree_beats(visual_graph: dict, stack: str, availability: str) -> list[dict]:
    """Returns [{id, spoken, pause_after_ms, summary}]."""
    if availability not in ("available", "partial") or not visual_graph:
        return []

    kind = visual_graph.get("kind") or "component_tree"
    if kind == "route_tree" or stack in ("go", "go_fiber", "gofiber"):
        return _route_tree_beats(visual_graph, availability)
    return _component_tree_beats(visual_graph, availability)


def _component_tree_beats(visual_graph: dict, availability: str) -> list[dict]:
    nodes = {n["id"]: n for n in visual_graph.get("nodes") or []}
    root_id = visual_graph.get("rootId")
    root = nodes.get(root_id) or {}
    root_label = root.get("label") or "this component"
    mounts = [e for e in visual_graph.get("edges") or [] if e.get("kind") == "mounts"]
    assumed = [e for e in mounts if e.get("assumed")]
    verified = [e for e in mounts if not e.get("assumed")]

    child_labels = []
    for e in mounts[:6]:
        child = nodes.get(e["to"], {})
        label = child.get("label")
        if label and label not in child_labels:
            child_labels.append(label)

    beats: list[dict] = []
    if child_labels:
        listed = ", ".join(child_labels[:4])
        spoken = f"{root_label} mounts {listed}."
        if len(child_labels) > 4:
            spoken = f"{root_label} mounts {listed}, and more."
        beats.append({
            "id": "tree-orientation",
            "summary": f"{root_label} structure",
            "spoken": spoken,
            "pause_after_ms": 400,
        })
    else:
        beats.append({
            "id": "tree-orientation",
            "summary": f"{root_label} structure",
            "spoken": f"Here is the component tree for {root_label}.",
            "pause_after_ms": 400,
        })

    if verified:
        first = nodes.get(verified[0]["to"], {}).get("label") or "a child"
        beats.append({
            "id": "tree-verified",
            "summary": "Verified mounts",
            "spoken": f"Verified mounts include {first}.",
            "pause_after_ms": 350,
        })

    if assumed:
        beats.append({
            "id": "tree-assumed",
            "summary": "Assumed mounts",
            "spoken": "It looks like some children are mounted dynamically.",
            "pause_after_ms": 300,
        })
    elif availability == "partial" and not assumed:
        beats.append({
            "id": "tree-partial",
            "summary": "Partial tree",
            "spoken": "It looks like the prop layer is incomplete for this file.",
            "pause_after_ms": 300,
        })

    return _cap_beats(beats)


def _route_tree_beats(visual_graph: dict, availability: str) -> list[dict]:
    nodes = {n["id"]: n for n in visual_graph.get("nodes") or []}
    root = nodes.get(visual_graph.get("rootId")) or {}
    root_label = root.get("label") or "this file"
    route_edges = [e for e in visual_graph.get("edges") or [] if e.get("kind") == "routes_to"]
    mw_edges = [e for e in visual_graph.get("edges") or [] if e.get("kind") == "middleware_before"]
    route_nodes = [
        n for n in nodes.values()
        if n.get("kind") == "route" and (n.get("meta") or {}).get("method")
    ]
    assumed = [e for e in route_edges if e.get("assumed")]

    beats: list[dict] = []
    if route_nodes:
        labels = [n.get("label") for n in route_nodes[:4] if n.get("label")]
        listed = ", ".join(labels)
        spoken = f"{root_label} registers {listed}."
        if len(route_nodes) > 4:
            spoken = f"{root_label} registers {listed}, and more."
        beats.append({
            "id": "tree-orientation",
            "summary": f"{root_label} routes",
            "spoken": spoken,
            "pause_after_ms": 400,
        })
    else:
        beats.append({
            "id": "tree-orientation",
            "summary": f"{root_label} routes",
            "spoken": f"Here is the route tree for {root_label}.",
            "pause_after_ms": 400,
        })

    if mw_edges:
        beats.append({
            "id": "tree-middleware",
            "summary": "Middleware",
            "spoken": "Middleware attaches before handlers on these routers.",
            "pause_after_ms": 350,
        })

    if assumed:
        beats.append({
            "id": "tree-assumed",
            "summary": "Assumed paths",
            "spoken": "It looks like some route prefixes are unresolved in this file.",
            "pause_after_ms": 300,
        })
    elif availability == "partial" and not mw_edges:
        beats.append({
            "id": "tree-partial",
            "summary": "Partial route tree",
            "spoken": "It looks like the middleware chain is incomplete for this file.",
            "pause_after_ms": 300,
        })

    return _cap_beats(beats)


def _cap_beats(beats: list[dict]) -> list[dict]:
    out = []
    for beat in beats[:3]:
        clean, _ = strip_visual_tokens(beat["spoken"])
        beat["spoken"] = clean
        out.append(beat)
    return out


def script_react_component_tree(graph: dict, availability: str = "available") -> list[dict]:
    return build_tree_beats(graph, "react", availability)


def script_go_fiber_route_tree(graph: dict, availability: str = "available") -> list[dict]:
    return build_tree_beats(graph, "go", availability)
