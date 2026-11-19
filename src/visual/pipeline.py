"""Attach visual envelope + stack graphs to a chunk record."""

from __future__ import annotations

import json
from pathlib import Path

from .availability import empty_availability, is_present, set_capability
from .graph_builder import build_go_fiber_route_tree, build_react_component_tree
from .lifecycle_builder import (
    build_go_fiber_lifecycle_flows,
    build_react_lifecycle_flows,
    select_top_lifecycle_flows,
)
from .package_interactive import (
    package_go_fiber_interactive_breakdown,
    package_react_interactive_breakdown,
    write_interactive_artifact,
)
from .security_flags import (
    flag_go_fiber_lifecycle_security,
    flag_go_fiber_tree_security,
    flag_react_lifecycle_security,
    flag_react_tree_security,
)
from .theme import theme_for_stack


PLACEHOLDER_REASON = "extractor_placeholder_or_not_implemented"
ANGULAR_REASON = "angular_empty_valid_or_missing_extractor"
STACK_NOT_SHIPPED_REASON = "stack_visuals_not_shipped_yet"
NO_MOUNTS_REASON = "no_jsx_mounts_extracted"
NO_ROUTES_REASON = "no_fiber_routes_extracted"
NO_FLOWS_REASON = "no_lifecycle_triggers_extracted"
SINGLE_ORPHAN_REASON = "single_node_no_edges"


def attach_visuals(record: dict, stack: str | None = None) -> dict:
    """Mutates and returns record with fidelity + visualAvailability (+ graphs when shipped)."""
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

    if stack == "react":
        return _attach_react_visuals(record)

    if stack == "go":
        return _attach_go_fiber_visuals(record)

    record["visualAvailability"] = empty_availability(STACK_NOT_SHIPPED_REASON)
    record["visualGraph"] = None
    record["lifecycleFlows"] = []
    record["securityFlags"] = []
    return record


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


def _attach_go_fiber_visuals(record: dict) -> dict:
    """Go Fiber route_tree + middleware-ordered lifecycle for this file/package chunk."""
    avail = empty_availability("")
    avail["reasons"] = {}

    graph = build_go_fiber_route_tree(record)
    if graph is None:
        reason = NO_ROUTES_REASON if not (record.get("routes")) else SINGLE_ORPHAN_REASON
        avail = set_capability(avail, "componentTree", "unavailable", reason)
        record["visualGraph"] = None
    else:
        assumed_edges = sum(1 for e in graph["edges"] if e.get("assumed"))
        unresolved = any(
            "incomplete" in ((r.get("notes") or ""))
            for r in (record.get("routes") or [])
        )
        status = "partial" if assumed_edges or unresolved else "available"
        reason = None
        if unresolved:
            reason = "One or more route group prefixes unresolved; paths may be incomplete."
        elif not (record.get("middleware")):
            status = "partial"
            reason = "No middleware registrations extracted; route tree only."
        avail = set_capability(avail, "componentTree", status, reason)
        record["visualGraph"] = graph

    flows = build_go_fiber_lifecycle_flows(record)
    if not flows:
        avail = set_capability(avail, "lifecycleFlow", "unavailable", NO_FLOWS_REASON)
        record["lifecycleFlows"] = []
    else:
        missing_mw = any(not (f.get("meta") or {}).get("hasMiddleware") for f in flows)
        partial = (
            any(f.get("assumed") for f in flows)
            or record.get("fidelity") == "regex"
            or missing_mw
        )
        reason = None
        if missing_mw:
            reason = "Routes without middleware list: lifecycle partial."
        elif record.get("fidelity") == "regex":
            reason = "Middleware/handler steps hedged under regex fidelity."
        avail = set_capability(
            avail, "lifecycleFlow",
            "partial" if partial else "available",
            reason,
        )
        record["lifecycleFlows"] = flows

    if is_present(avail.get("componentTree")):
        status = (
            "partial"
            if avail.get("componentTree") == "partial" or avail.get("lifecycleFlow") == "partial"
            else "available"
        )
        avail = set_capability(avail, "interactiveBreakdown", status)
    else:
        avail = set_capability(
            avail, "interactiveBreakdown", "unavailable",
            avail.get("reasons", {}).get("componentTree", NO_ROUTES_REASON),
        )

    tree_flags = flag_go_fiber_tree_security(record.get("visualGraph"), record)
    life_flags = flag_go_fiber_lifecycle_security(record.get("lifecycleFlows") or [])
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

    if is_present(avail.get("interactiveBreakdown")):
        if stack == "react":
            payload = package_react_interactive_breakdown(record)
        elif stack == "go":
            payload = package_go_fiber_interactive_breakdown(record)
        else:
            payload = None
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
