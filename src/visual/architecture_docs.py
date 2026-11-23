"""Write per-chunk architecture.md — Mermaid fences + honesty chrome for docs."""

from __future__ import annotations

from pathlib import Path

from .diagram_selection import select_diagram_plan
from .mermaid_export import export_lifecycle_mermaid, export_mermaid


def write_architecture_markdown(record: dict, dest_dir: Path) -> Path | None:
    """Emit architecture.md beside interactive.json. Skip when nothing to show."""
    plan = select_diagram_plan(record)
    graph = record.get("visualGraph")
    flows = record.get("lifecycleFlows") or []

    structure_text, structure_skip = export_mermaid(graph) if graph else (None, "no_graph")
    lifecycle_text, lifecycle_skip = export_lifecycle_mermaid(flows)

    if not structure_text and not lifecycle_text:
        return None

    stack = record.get("stack") or "unknown"
    chunk_id = record.get("chunkId") or "unknown"
    file_path = record.get("filePath") or ""
    fidelity = record.get("fidelity") or "unknown"
    avail = record.get("visualAvailability") or {}

    lines: list[str] = [
        f"# Architecture — `{file_path or chunk_id}`",
        "",
        f"**Stack:** `{stack}` · **Chunk:** `{chunk_id}` · **Fidelity:** `{fidelity}`",
        "",
        "> Simplified Mermaid export of the same `visualGraph` / `lifecycleFlows` "
        "shown in Remotion. Layout is not pixel-identical to video.",
        "",
        "## Availability",
        "",
        f"- componentTree: `{avail.get('componentTree', 'unknown')}`",
        f"- lifecycleFlow: `{avail.get('lifecycleFlow', 'unknown')}`",
        f"- interactiveBreakdown: `{avail.get('interactiveBreakdown', 'unknown')}`",
        "",
    ]

    reasons = avail.get("reasons") or {}
    if reasons:
        lines.append("### Skip / honesty reasons")
        lines.append("")
        for cap, reason in reasons.items():
            lines.append(f"- `{cap}`: {reason}")
        lines.append("")

    if "structure" in plan["docsSectionOrder"] and structure_text:
        lines.extend([
            "## Structure",
            "",
            "Mount / route / DI / module edges for this chunk (developer-scoped).",
            "",
            "```mermaid",
            structure_text,
            "```",
            "",
        ])
    elif structure_skip:
        lines.extend([
            "## Structure",
            "",
            f"_No structure diagram (`{structure_skip}`)._",
            "",
        ])

    if "lifecycle" in plan["docsSectionOrder"] and lifecycle_text:
        lines.extend([
            "## Lifecycle",
            "",
            "Ordered in-chunk control flow (handlers, middleware, API steps).",
            "",
            "```mermaid",
            lifecycle_text,
            "```",
            "",
        ])
    elif lifecycle_skip and plan["lifecycle"].get("skipReason"):
        lines.extend([
            "## Lifecycle",
            "",
            f"_No lifecycle diagram (`{lifecycle_skip}`)._",
            "",
        ])

    # Evidence section — line refs from graph nodes / flow steps
    evidence = _evidence_lines(graph, flows)
    lines.extend(["## Evidence", ""])
    if evidence:
        lines.extend(evidence)
        lines.append("")
    else:
        lines.extend(["_No `filePath:line` evidence on nodes/steps._", ""])

    lines.extend([
        "## Interactive",
        "",
        "Primary exploration is the Cursor canvas over `interactive.json`. "
        "Mermaid above is the chat/docs fallback (≤40 nodes).",
        "",
        f"Docs diagram plan: `{', '.join(plan['docsDiagrams']) or 'none'}`.",
        "",
    ])

    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "architecture.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _evidence_lines(graph: dict | None, flows: list[dict]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for node in (graph or {}).get("nodes") or []:
        fp = node.get("filePath")
        line = node.get("line")
        label = node.get("label") or node.get("id")
        if fp and line:
            key = f"{fp}:{line}"
            if key not in seen:
                seen.add(key)
                rows.append(f"- `{label}` — `{key}`")
    for flow in flows:
        for step in flow.get("steps") or []:
            lr = step.get("lineRange") or []
            if not lr:
                continue
            label = step.get("label") or step.get("action")
            line = lr[0]
            key = f"step:{label}:{line}"
            if key not in seen:
                seen.add(key)
                rows.append(f"- `{label}` — lines `{lr[0]}–{lr[-1]}`")
    return rows[:40]
