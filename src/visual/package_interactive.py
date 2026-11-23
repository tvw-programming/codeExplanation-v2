"""Package interactive breakdown payloads for Cursor canvas / Mermaid."""

from __future__ import annotations

import json
from pathlib import Path

from .availability import is_present
from .mermaid_export import export_lifecycle_mermaid, export_mermaid
from .theme import theme_for_stack


def package_interactive_breakdown(record: dict) -> dict | None:
    """Embed this unit's graph + flows. Refuse when interactiveBreakdown unavailable."""
    return _package_interactive_breakdown(record)


def package_react_interactive_breakdown(record: dict) -> dict | None:
    return package_interactive_breakdown(record)


def package_go_fiber_interactive_breakdown(record: dict) -> dict | None:
    return package_interactive_breakdown(record)


def _package_interactive_breakdown(record: dict) -> dict | None:
    avail = (record.get("visualAvailability") or {}).get("interactiveBreakdown")
    if not is_present(avail):
        return None
    graph = record.get("visualGraph")
    if not graph or not graph.get("edges"):
        return None

    stack = _stack_of(record)
    payload = {
        "chunkId": record.get("chunkId"),
        "filePath": record.get("filePath"),
        "stack": stack,
        "visualAvailability": record.get("visualAvailability"),
        "fidelity": record.get("fidelity"),
        "visualGraph": graph,
        "lifecycleFlows": record.get("lifecycleFlows") or [],
        "securityFlags": record.get("securityFlags") or [],
        "visualTheme": record.get("visualTheme") or theme_for_stack(stack),
    }
    mermaid, mermaid_reason = export_mermaid(graph)
    payload["mermaid"] = mermaid
    if mermaid_reason:
        payload["mermaidSkipReason"] = mermaid_reason

    flows = payload["lifecycleFlows"]
    life_mermaid, life_reason = export_lifecycle_mermaid(flows)
    payload["mermaidLifecycle"] = life_mermaid
    if life_reason:
        payload["mermaidLifecycleSkipReason"] = life_reason

    # Docs/chat honesty chrome — grounded in existing export rules only.
    payload["mermaidHonesty"] = {
        "assumedEdges": "-.->",
        "assumedLifecycle": "Note … assumed",
        "skipWhen": ["unavailable", "empty", "too_large", "no_graph"],
        "fidelity": record.get("fidelity"),
        "nodeCap": 40,
    }
    return payload


_CHILD_EDGE_KINDS = ("mounts", "routes_to", "middleware_before", "provides")


def canvas_react_node_detail(node: dict, graph: dict, flows: list[dict] | None = None) -> dict:
    """Developer-facing detail panel fields for one React node."""
    return _canvas_node_detail(node, graph, flows, child_kinds=("mounts",))


def canvas_go_fiber_node_detail(node: dict, graph: dict, flows: list[dict] | None = None) -> dict:
    """Click route → middleware stack + handler cues for this chunk."""
    detail = _canvas_node_detail(
        node, graph, flows, child_kinds=("routes_to", "middleware_before"),
    )
    node_id = node.get("id")
    middleware = [
        e["from"] for e in (graph.get("edges") or [])
        if e.get("to") == node_id and e.get("kind") == "middleware_before"
    ]
    detail["middleware"] = middleware
    detail["middlewareCount"] = len(middleware)
    return detail


def _canvas_node_detail(
    node: dict,
    graph: dict,
    flows: list[dict] | None,
    child_kinds: tuple[str, ...] = _CHILD_EDGE_KINDS,
) -> dict:
    node_id = node.get("id")
    children = [
        e["to"] for e in (graph.get("edges") or [])
        if e.get("from") == node_id and e.get("kind") in child_kinds
    ]
    related = []
    for flow in flows or []:
        for step in flow.get("steps") or []:
            if step.get("nodeId") == node_id:
                related.append({"flowId": flow.get("id"), "title": flow.get("title"), "step": step})
            # Also link flows whose title matches this route label.
            elif node.get("kind") == "route" and flow.get("title") == node.get("label"):
                related.append({"flowId": flow.get("id"), "title": flow.get("title"), "step": step})
                break
    meta = node.get("meta") or {}
    line = node.get("line")
    file_path = node.get("filePath") or ""
    return {
        "kind": node.get("kind"),
        "label": node.get("label"),
        "filePath": file_path,
        "line": line,
        "location": f"{file_path}:{line}" if file_path and line else file_path or None,
        "props": meta.get("props") or [],
        "childCount": len(children),
        "children": children,
        "relatedLifecycleSteps": related,
        "meta": {k: v for k, v in meta.items() if k != "props"},
    }


def write_interactive_artifact(payload: dict, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "interactive.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _stack_of(record: dict) -> str:
    if record.get("stack"):
        return record["stack"]
    pt = record.get("projectType") or {}
    if pt.get("frontend"):
        return pt["frontend"]
    backends = pt.get("backend") or []
    if isinstance(backends, list) and backends:
        return backends[0]
    return "unknown"
