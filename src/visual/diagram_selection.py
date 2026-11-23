"""Diagram selection / sequencing for video vs docs surfaces.

Encodes mermaid-sequence-decision.md: Remotion owns FullVideo (Q1);
Mermaid owns docs/chat exports. Never invents edges; skips unavailable.
"""

from __future__ import annotations

from .availability import is_present
from .mermaid_export import MERMAID_NODE_CAP

# Locked FullVideo chapter order (preferences Q1 A). Mermaid must not reorder.
VIDEO_CHAPTER_ORDER = ("card", "tree", "lifecycle", "code", "breakdown")

# Docs section order mirrors video beats so prose + diagrams stay aligned.
DOCS_SECTION_ORDER = (
    "meta",        # FileCard analogue
    "structure",   # ComponentTreeClip analogue
    "lifecycle",   # LifecycleFlowClip analogue
    "evidence",    # ChunkView analogue (prose / line refs)
    "interactive", # VisualBreakdownStill analogue
)


def select_diagram_plan(record: dict) -> dict:
    """Return which diagrams/sections to emit for docs and which video clips apply.

    Accuracy / visual / detail rules (summary):
    - Video: Remotion when narration + graph/flows present (timed teaching).
    - Docs: Mermaid flowchart for structure; sequenceDiagram for lifecycle.
    - Skip empty / too_large / unavailable — never placeholder diagrams.
    """
    avail = record.get("visualAvailability") or {}
    graph = record.get("visualGraph")
    flows = record.get("lifecycleFlows") or []
    nodes = (graph or {}).get("nodes") or []
    edges = (graph or {}).get("edges") or []

    structure_ok = (
        is_present(avail.get("componentTree"))
        and bool(graph)
        and bool(nodes)
        and bool(edges)
        and len(nodes) <= MERMAID_NODE_CAP
    )
    structure_skip = None
    if not is_present(avail.get("componentTree")) or not graph:
        structure_skip = (avail.get("reasons") or {}).get("componentTree") or "unavailable"
    elif not nodes:
        structure_skip = "empty"
    elif not edges:
        structure_skip = "no_edges"
    elif len(nodes) > MERMAID_NODE_CAP:
        structure_skip = "too_large"

    lifecycle_ok = is_present(avail.get("lifecycleFlow")) and bool(flows)
    lifecycle_skip = None
    if not is_present(avail.get("lifecycleFlow")):
        lifecycle_skip = (avail.get("reasons") or {}).get("lifecycleFlow") or "unavailable"
    elif not flows:
        lifecycle_skip = "empty"

    interactive_ok = is_present(avail.get("interactiveBreakdown")) and structure_ok

    docs_sections: list[str] = ["meta"]
    docs_diagrams: list[str] = []
    if structure_ok:
        docs_sections.append("structure")
        docs_diagrams.append("flowchart_td")
    if lifecycle_ok:
        docs_sections.append("lifecycle")
        docs_diagrams.append("sequence")
    docs_sections.append("evidence")
    if interactive_ok or structure_ok:
        docs_sections.append("interactive")

    # Video: Remotion always; Mermaid never inserts slots.
    video_segments = {
        "card": True,  # gated later by fileOverview / narration in render path
        "tree": structure_ok,  # also needs treeNarration at render time
        "lifecycle": lifecycle_ok,
        "code": True,
        "breakdown": interactive_ok or structure_ok,
        "mermaid_in_video": False,
    }

    return {
        "videoChapterOrder": list(VIDEO_CHAPTER_ORDER),
        "docsSectionOrder": [s for s in DOCS_SECTION_ORDER if s in docs_sections],
        "docsDiagrams": docs_diagrams,
        "structure": {"include": structure_ok, "skipReason": None if structure_ok else structure_skip},
        "lifecycle": {"include": lifecycle_ok, "skipReason": None if lifecycle_ok else lifecycle_skip},
        "interactive": {"include": interactive_ok, "skipReason": None if interactive_ok else "unavailable"},
        "video": video_segments,
        "preferRemotionForVideo": True,
        "preferMermaidForDocs": True,
    }
