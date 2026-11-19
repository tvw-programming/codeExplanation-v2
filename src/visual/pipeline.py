"""Attach visual envelope + React graphs to a chunk record."""

from __future__ import annotations

import json
from pathlib import Path

from .availability import empty_availability, is_present, set_capability
from .graph_builder import build_react_component_tree
from .lifecycle_builder import build_react_lifecycle_flows, select_top_lifecycle_flows
from .package_interactive import package_react_interactive_breakdown, write_interactive_artifact
from .security_flags import flag_react_lifecycle_security, flag_react_tree_security
from .theme import theme_for_stack


PLACEHOLDER_REASON = "extractor_placeholder_or_not_implemented"
ANGULAR_REASON = "angular_empty_valid_or_missing_extractor"
NON_REACT_REASON = "stack_visuals_not_in_react_slice"
NO_MOUNTS_REASON = "no_jsx_mounts_extracted"
NO_FLOWS_REASON = "no_lifecycle_triggers_extracted"
SINGLE_ORPHAN_REASON = "single_node_no_edges"


def attach_visuals(record: dict, stack: str | None = None) -> dict:
    """Mutates and returns record with fidelity + visualAvailability (+ graphs for React)."""
    stack = stack or _infer_stack(record)
    record["fidelity"] = record.get("fidelity") or _default_fidelity(stack)
    record["visualTheme"] = theme_for_stack(stack)

    # Placeholders (confidence 0 + not implemented note)
    notes = (record.get("notes") or "")
    if record.get("confidence") == 0 and "not yet implemented" in notes:
        record["visualAvailability"] = empty_availability(PLACEHOLDER_REASON)
        record["visualGraph"] = None
        record["lifecycleFlows"] = []
        record["securityFlags"] = []
        return record

    if stack == "angular":
        record["visualAvailability"] = empty_availability(ANGULAR_REASON)
        record["visualGraph"] = None
        record["lifecycleFlows"] = []
        record["securityFlags"] = []
        return record

    if stack != "react":
        record["visualAvailability"] = empty_availability(NON_REACT_REASON)
        record["visualGraph"] = None
        record["lifecycleFlows"] = []
        record["securityFlags"] = []
        return record

    return _attach_react_visuals(record)


def _attach_react_visuals(record: dict) -> dict:
    avail = empty_availability("")  # will replace reasons per key
    avail["reasons"] = {}

    graph = build_react_component_tree(record)
    if graph is None:
        reason = NO_MOUNTS_REASON if not (record.get("jsxMounts")) else SINGLE_ORPHAN_REASON
        avail = set_capability(avail, "componentTree", "unavailable", reason)
    else:
        assumed_edges = sum(1 for e in graph["edges"] if e.get("assumed"))
        status = "partial" if assumed_edges else "available"
        if not (record.get("inputs")):
            status = "partial"
            avail = set_capability(
                avail, "componentTree", status,
                "No XProps interface found; prop layer incomplete.",
            )
        else:
            avail = set_capability(avail, "componentTree", status)
        record["visualGraph"] = graph

    flows = build_react_lifecycle_flows(record)
    if not flows:
        avail = set_capability(avail, "lifecycleFlow", "unavailable", NO_FLOWS_REASON)
        record["lifecycleFlows"] = []
    else:
        partial = any(f.get("assumed") for f in flows) or record.get("fidelity") == "regex"
        avail = set_capability(
            avail, "lifecycleFlow",
            "partial" if partial else "available",
            "Hook/render steps hedged under regex fidelity." if partial else None,
        )
        record["lifecycleFlows"] = flows

    # Interactive follows tree (and soft-partial if lifecycle partial).
    if is_present(avail.get("componentTree")):
        status = "partial" if avail.get("componentTree") == "partial" or avail.get("lifecycleFlow") == "partial" else "available"
        avail = set_capability(avail, "interactiveBreakdown", status)
    else:
        avail = set_capability(
            avail, "interactiveBreakdown", "unavailable",
            avail.get("reasons", {}).get("componentTree", NO_MOUNTS_REASON),
        )

    tree_flags = flag_react_tree_security(record.get("visualGraph"), record)
    life_flags = flag_react_lifecycle_security(record.get("lifecycleFlows") or [])
    record["securityFlags"] = tree_flags + life_flags
    record["visualAvailability"] = avail

    if "visualGraph" not in record:
        record["visualGraph"] = None

    return record


def build_visual_artifacts(
    record: dict,
    visuals_root: Path | None = None,
) -> dict:
    """Stage optional visuals/<stack>/<chunkId>/ artifacts (graph JSON + interactive).

    Returns a summary dict for callers (paths written, skipped reasons).
    Does not synthesize TTS — that lives in render_pipeline.
    """
    stack = _infer_stack(record)
    avail = record.get("visualAvailability") or {}
    summary: dict = {"chunkId": record.get("chunkId"), "written": [], "skipped": []}

    if visuals_root is None:
        return summary

    dest = visuals_root / stack / (record.get("chunkId") or "unknown")
    if is_present(avail.get("componentTree")) and record.get("visualGraph"):
        dest.mkdir(parents=True, exist_ok=True)
        graph_path = dest / "visualGraph.json"
        graph_path.write_text(
            json.dumps(record["visualGraph"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        summary["written"].append(str(graph_path))
        if record.get("lifecycleFlows"):
            flows_path = dest / "lifecycleFlows.json"
            flows_path.write_text(
                json.dumps(record["lifecycleFlows"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            summary["written"].append(str(flows_path))
    else:
        summary["skipped"].append("componentTree")

    if stack == "react" and is_present(avail.get("interactiveBreakdown")):
        payload = package_react_interactive_breakdown(record)
        if payload:
            path = write_interactive_artifact(payload, dest)
            summary["written"].append(str(path))
        else:
            summary["skipped"].append("interactiveBreakdown")
    else:
        summary["skipped"].append("interactiveBreakdown")

    return summary


def video_flows_for_record(record: dict, n: int = 2) -> list[dict]:
    return select_top_lifecycle_flows(record.get("lifecycleFlows") or [], n=n)


def _infer_stack(record: dict) -> str:
    if record.get("stack"):
        return record["stack"]
    pt = record.get("projectType") or {}
    if pt.get("frontend"):
        return pt["frontend"]
    backends = pt.get("backend") or []
    if backends:
        return backends[0]
    return "unknown"


def _default_fidelity(stack: str) -> str:
    # All current extractors are regex-based.
    return "regex"
