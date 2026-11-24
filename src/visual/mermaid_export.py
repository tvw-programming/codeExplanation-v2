"""Mermaid export for small graphs (≤ ~40 nodes) and lifecycle sequences.

Same strings feed docs, chat, and Remotion video frames (Mermaid.js → SVG).
Remotion still uses measured-beat TTS (Q4); Q1 order unchanged.
Never invent edges; assumed facts become dashed arrows or Notes.
"""

from __future__ import annotations

MERMAID_NODE_CAP = 40
MERMAID_FLOW_CAP = 4
MERMAID_STEP_CAP = 24


def export_mermaid(graph: dict | None) -> tuple[str | None, str | None]:
    """Structure flowchart TD from visualGraph. Returns (mermaid_text, skip_reason)."""
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


def export_lifecycle_mermaid(
    flows: list[dict] | None,
    *,
    max_flows: int = MERMAID_FLOW_CAP,
) -> tuple[str | None, str | None]:
    """sequenceDiagram from lifecycleFlows. Returns (mermaid_text, skip_reason).

    Participants and messages come only from extracted steps — no invented
    hops. Assumed steps get a Note. Caps keep chat/docs readable.
    """
    if not flows:
        return None, "empty"
    selected = [f for f in flows if (f.get("steps") or [])][:max_flows]
    if not selected:
        return None, "empty"

    lines = ["sequenceDiagram"]
    step_budget = MERMAID_STEP_CAP
    for flow in selected:
        title = (flow.get("title") or flow.get("trigger") or flow.get("id") or "flow")
        title_safe = str(title).replace('"', "'")
        lines.append(f"  %% {title_safe}")
        trigger = flow.get("trigger") or flow.get("title") or "trigger"
        trigger_id = _safe_id(f"trigger_{flow.get('id') or title}")
        lines.append(f'  participant {trigger_id} as {_alias(trigger)}')

        prev = trigger_id
        steps = list(flow.get("steps") or [])
        if len(steps) > step_budget:
            steps = steps[:step_budget]
        step_budget -= len(steps)

        for step in steps:
            label = step.get("label") or step.get("action") or "step"
            sid = _safe_id(f"{flow.get('id') or title}_{step.get('order')}_{label}")
            lines.append(f'  participant {sid} as {_alias(label)}')
            action = (step.get("action") or "step").replace("\n", " ")
            # Mermaid message label — keep short; honesty via Note when assumed
            msg = action.replace(":", ",")
            lines.append(f"  {prev}->>{sid}: {msg}")
            if step.get("assumed") or flow.get("assumed"):
                lines.append(f"  Note over {sid}: assumed")
            prev = sid

        if step_budget <= 0:
            break

    # Must have at least one message (participant-only dumps are useless)
    if not any("->>" in ln for ln in lines):
        return None, "empty"
    return "\n".join(lines), None


def _alias(raw: str) -> str:
    """Mermaid participant alias — quote-safe, truncated."""
    text = str(raw).replace('"', "'").replace("\n", " ").strip() or "step"
    if len(text) > 48:
        text = text[:45] + "..."
    return text


def _safe_id(raw: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in str(raw))
    # Mermaid participant ids must not be empty / leading-digit awkward
    if not cleaned or cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return cleaned
