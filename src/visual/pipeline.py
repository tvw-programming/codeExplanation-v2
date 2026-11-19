"""Attach visual envelope + stack graphs to a chunk record."""

from __future__ import annotations

import json
from pathlib import Path

from .availability import empty_availability, is_present, set_capability
from .graph_builder import (
    build_angular_selector_tree,
    build_go_fiber_route_tree,
    build_js_module_tree,
    build_python_structure_tree,
    build_qwik_component_tree,
    build_react_component_tree,
    build_rust_crate_or_route_tree,
    build_solid_component_tree,
    build_spring_di_tree,
    build_generic_route_tree,
)
from .lifecycle_builder import (
    build_angular_lifecycle_flows,
    build_express_lifecycle_flows,
    build_go_fiber_lifecycle_flows,
    build_js_lifecycle_flows,
    build_python_lifecycle_flows,
    build_qwik_lifecycle_flows,
    build_react_lifecycle_flows,
    build_rust_lifecycle_flows,
    build_solid_lifecycle_flows,
    build_spring_lifecycle_flows,
    build_vue_lifecycle_flows,
    select_top_lifecycle_flows,
)
from .package_interactive import (
    package_interactive_breakdown,
    write_interactive_artifact,
)
from .security_flags import (
    flag_go_fiber_lifecycle_security,
    flag_go_fiber_tree_security,
    flag_react_lifecycle_security,
    flag_react_tree_security,
    flag_generic_route_security,
)
from .theme import theme_for_stack


PLACEHOLDER_REASON = "extractor_placeholder_or_not_implemented"
NO_MOUNTS_REASON = "no_structure_edges_extracted"
NO_FLOWS_REASON = "no_lifecycle_triggers_extracted"
SINGLE_ORPHAN_REASON = "single_node_no_edges"

SHIPPED_STACKS = {
    "react", "go", "angular", "vue", "solid", "qwik",
    "javascript", "python", "spring_boot", "java", "express", "rust",
}


def attach_visuals(record: dict, stack: str | None = None) -> dict:
    stack = stack or _infer_stack(record)
    record["fidelity"] = record.get("fidelity") or _default_fidelity(stack)
    record["visualTheme"] = theme_for_stack(stack)

    notes = (record.get("notes") or "")
    if record.get("confidence") == 0 and "not yet implemented" in notes:
        record["visualAvailability"] = empty_availability(PLACEHOLDER_REASON)
        record["visualGraph"] = None
        record["lifecycleFlows"] = []
        record["securityFlags"] = []
        return record

    builders = {
        "react": _attach_react_visuals,
        "go": _attach_go_fiber_visuals,
        "angular": _attach_angular_visuals,
        "vue": lambda r: _attach_mount_stack(r, "vue", build_react_component_tree, build_vue_lifecycle_flows),
        "solid": lambda r: _attach_mount_stack(r, "solid", build_solid_component_tree, build_solid_lifecycle_flows),
        "qwik": lambda r: _attach_mount_stack(r, "qwik", build_qwik_component_tree, build_qwik_lifecycle_flows),
        "javascript": _attach_javascript_visuals,
        "python": _attach_python_visuals,
        "express": _attach_express_visuals,
        "spring_boot": _attach_spring_visuals,
        "java": _attach_spring_visuals,
        "rust": _attach_rust_visuals,
    }
    fn = builders.get(stack)
    if fn:
        return fn(record)

    record["visualAvailability"] = empty_availability("stack_visuals_not_shipped_yet")
    record["visualGraph"] = None
    record["lifecycleFlows"] = []
    record["securityFlags"] = []
    return record


def _set_tree(avail, record, graph, empty_reason: str, partial_reason: str | None = None):
    if graph is None:
        avail = set_capability(avail, "componentTree", "unavailable", empty_reason)
        record["visualGraph"] = None
    else:
        assumed = sum(1 for e in graph["edges"] if e.get("assumed"))
        status = "partial" if assumed or partial_reason else "available"
        avail = set_capability(avail, "componentTree", status, partial_reason if status == "partial" else None)
        record["visualGraph"] = graph
    return avail


def _set_flows(avail, record, flows, hedge: str | None = None):
    if not flows:
        avail = set_capability(avail, "lifecycleFlow", "unavailable", NO_FLOWS_REASON)
        record["lifecycleFlows"] = []
    else:
        partial = any(f.get("assumed") for f in flows) or record.get("fidelity") == "regex" or bool(hedge)
        avail = set_capability(
            avail, "lifecycleFlow",
            "partial" if partial else "available",
            hedge if partial else None,
        )
        record["lifecycleFlows"] = flows
    return avail


def _set_interactive(avail):
    if is_present(avail.get("componentTree")):
        status = (
            "partial"
            if avail.get("componentTree") == "partial" or avail.get("lifecycleFlow") == "partial"
            else "available"
        )
        return set_capability(avail, "interactiveBreakdown", status)
    return set_capability(
        avail, "interactiveBreakdown", "unavailable",
        avail.get("reasons", {}).get("componentTree", NO_MOUNTS_REASON),
    )


def _attach_react_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_react_component_tree(record)
    reason = NO_MOUNTS_REASON if not (record.get("jsxMounts")) else SINGLE_ORPHAN_REASON
    partial = None
    if graph and not record.get("inputs"):
        partial = "No XProps interface found; prop layer incomplete."
    avail = _set_tree(avail, record, graph, reason, partial)
    flows = build_react_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows, "Hook/render steps hedged under regex fidelity.")
    avail = _set_interactive(avail)
    record["securityFlags"] = (
        flag_react_tree_security(record.get("visualGraph"), record)
        + flag_react_lifecycle_security(record.get("lifecycleFlows") or [])
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_go_fiber_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_go_fiber_route_tree(record)
    reason = "no_fiber_routes_extracted" if not record.get("routes") else SINGLE_ORPHAN_REASON
    partial = None
    if graph and not record.get("middleware"):
        partial = "No middleware registrations extracted; route tree only."
    avail = _set_tree(avail, record, graph, reason, partial)
    flows = build_go_fiber_lifecycle_flows(record)
    missing_mw = any(not (f.get("meta") or {}).get("hasMiddleware") for f in flows)
    hedge = "Routes without middleware list: lifecycle partial." if missing_mw else "Hedged under regex fidelity."
    avail = _set_flows(avail, record, flows, hedge)
    avail = _set_interactive(avail)
    record["securityFlags"] = (
        flag_go_fiber_tree_security(record.get("visualGraph"), record)
        + flag_go_fiber_lifecycle_security(record.get("lifecycleFlows") or [])
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_angular_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_angular_selector_tree(record)
    if graph is None:
        # Honest: empty-valid Angular must not draw blank trees
        avail = empty_availability("angular_empty_valid_or_missing_extractor")
        if record.get("angularComponent"):
            avail = set_capability(avail, "componentTree", "unavailable", "Angular component has no diagram edges.")
        record["visualGraph"] = None
        record["lifecycleFlows"] = []
        record["securityFlags"] = []
        record["visualAvailability"] = avail
        return record
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON, "Selector index is file-local (regex).")
    flows = build_angular_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows, "Angular lifecycle hedged under regex fidelity.")
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(record.get("visualGraph"), record.get("lifecycleFlows") or [], record)
    record["visualAvailability"] = avail
    return record


def _attach_mount_stack(record, stack, tree_fn, life_fn):
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = tree_fn(record)
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON, f"{stack} edges hedged under regex fidelity.")
    flows = life_fn(record)
    avail = _set_flows(avail, record, flows, f"{stack} lifecycle hedged under regex fidelity.")
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_javascript_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_js_module_tree(record)
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON)
    flows = build_js_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows)
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_python_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_python_structure_tree(record)
    partial = None
    if graph and graph.get("kind") == "module_graph" and not record.get("routes"):
        partial = "No web framework routes; module import graph only."
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON, partial)
    flows = build_python_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows, "Python route lifecycle; unresolved prefixes assumed.")
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_express_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_generic_route_tree(record, stack="express")
    avail = _set_tree(avail, record, graph, "no_express_routes_extracted", "Cross-file mounts may be assumed.")
    flows = build_express_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows, "Express middleware order file-local only.")
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_spring_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_spring_di_tree(record)
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON, "Interface-only injectees marked assumed.")
    flows = build_spring_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows)
    avail = _set_interactive(avail)
    record["securityFlags"] = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def _attach_rust_visuals(record: dict) -> dict:
    avail = empty_availability("")
    avail["reasons"] = {}
    graph = build_rust_crate_or_route_tree(record)
    avail = _set_tree(avail, record, graph, NO_MOUNTS_REASON, "Macro routes may be missing (partial).")
    flows = build_rust_lifecycle_flows(record)
    avail = _set_flows(avail, record, flows)
    avail = _set_interactive(avail)
    flags = flag_generic_route_security(
        record.get("visualGraph"), record.get("lifecycleFlows") or [], record,
    )
    for ub in record.get("unsafeBlocks") or []:
        flags.append({
            "id": f"unsafe:{ub.get('line')}",
            "severity": "high",
            "ruleId": "unsafe_on_path",
            "message": f"unsafe block at line {ub.get('line')}.",
            "nodeIds": [record["visualGraph"]["rootId"]] if record.get("visualGraph") else [],
            "edgeIds": [],
            "assumed": False,
        })
    record["securityFlags"] = flags
    record["visualAvailability"] = avail
    if "visualGraph" not in record:
        record["visualGraph"] = None
    return record


def build_visual_artifacts(record: dict, visuals_root: Path | None = None) -> dict:
    stack = _infer_stack(record)
    avail = record.get("visualAvailability") or {}
    summary: dict = {"chunkId": record.get("chunkId"), "written": [], "skipped": []}
    if visuals_root is None:
        return summary
    dest = visuals_root / stack / (record.get("chunkId") or "unknown")
    if is_present(avail.get("componentTree")) and record.get("visualGraph"):
        dest.mkdir(parents=True, exist_ok=True)
        graph_path = dest / "visualGraph.json"
        graph_path.write_text(json.dumps(record["visualGraph"], indent=2, ensure_ascii=False), encoding="utf-8")
        summary["written"].append(str(graph_path))
        if record.get("lifecycleFlows"):
            flows_path = dest / "lifecycleFlows.json"
            flows_path.write_text(json.dumps(record["lifecycleFlows"], indent=2, ensure_ascii=False), encoding="utf-8")
            summary["written"].append(str(flows_path))
    else:
        summary["skipped"].append("componentTree")

    if is_present(avail.get("interactiveBreakdown")):
        payload = package_interactive_breakdown(record)
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
    """Resolve stack for artifact paths / attach dispatch.

    Prefer explicit `stack` and theme. In monorepos, do not let
    `projectType.frontend` eclipse a backend chunk that has routes /
    Fiber middleware (that bug skipped Go Fiber FullVideo segments while
    leaving stale visuals/go artifacts on disk).
    """
    if record.get("stack"):
        return record["stack"]
    theme = record.get("visualTheme") or {}
    if theme.get("stack"):
        return theme["stack"]
    graph = record.get("visualGraph") or {}
    pt = record.get("projectType") or {}
    backends = pt.get("backend") or []
    if graph.get("kind") == "route_tree" or record.get("routes") or record.get("usesFiber") or record.get("middleware"):
        if backends:
            return backends[0]
        return "go"
    if pt.get("frontend"):
        return pt["frontend"]
    if backends:
        return backends[0]
    return "unknown"


def _default_fidelity(stack: str) -> str:
    if stack == "python":
        return "syntax"
    return "regex"
