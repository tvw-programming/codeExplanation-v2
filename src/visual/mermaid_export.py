"""Mermaid fallback for small graphs (≤ ~40 nodes)."""

from __future__ import annotations

MERMAID_NODE_CAP = 40


def export_mermaid(graph: dict | None) -> tuple[str | None, str | None]:
    """Returns (mermaid_text, skip_reason)."""
    if not graph:
        return None, "no_graph"
    nodes = graph.get("nodes") or []
    if len(nodes) > MERMAID_NODE_CAP:
        return None, "too_large"
    if not nodes:
        return None, "empty"

    lines = ["flowchart TD"]
    for node in nodes:
        nid = _safe_id(node["id"])
        label = (node.get("label") or nid).replace('"', "'")
        lines.append(f'  {nid}["{label}"]')
    for edge in graph.get("edges") or []:
        if edge.get("kind") == "passes_prop":
            continue  # keep Mermaid readable; mounts only
        frm = _safe_id(edge["from"])
        to = _safe_id(edge["to"])
        style = "-.->" if edge.get("assumed") else "-->"
        elabel = edge.get("label")
        if elabel:
            lines.append(f'  {frm} {style}|{elabel}| {to}')
        else:
            lines.append(f"  {frm} {style} {to}")
    return "\n".join(lines), None


def _safe_id(raw: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in raw)
