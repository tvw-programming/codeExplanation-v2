"""Security flag pass over visualGraph / lifecycleFlows. Never put secret values in labels."""

from __future__ import annotations

import re

SECRET_PROP_RE = re.compile(
    r"(password|secret|token|api[_-]?key|private[_-]?key|auth[_-]?header)",
    re.IGNORECASE,
)
HTML_SINK_RE = re.compile(r"dangerouslySetInnerHTML|innerHTML", re.IGNORECASE)
ADMIN_PATH_RE = re.compile(r"/(admin|internal|manage)\b", re.IGNORECASE)


def flag_react_tree_security(graph: dict | None, record: dict | None = None) -> list[dict]:
    flags: list[dict] = []
    if not graph:
        return flags
    record = record or {}
    nodes = {n["id"]: n for n in graph.get("nodes") or []}

    for node in graph.get("nodes") or []:
        meta = node.get("meta") or {}
        for prop in meta.get("props") or []:
            pname = prop.get("name") or ""
            if SECRET_PROP_RE.search(pname):
                flags.append({
                    "id": f"secret-prop:{node['id']}:{pname}",
                    "severity": "high",
                    "ruleId": "secret_like_prop",
                    "message": f"Prop '{pname}' looks secret-like; value redacted from diagram labels.",
                    "nodeIds": [node["id"]],
                    "edgeIds": [],
                    "assumed": True,
                })
            preview = prop.get("valuePreview") or ""
            if HTML_SINK_RE.search(pname) or HTML_SINK_RE.search(preview):
                flags.append({
                    "id": f"html-sink:{node['id']}:{pname}",
                    "severity": "high",
                    "ruleId": "xss_html_sink",
                    "message": "HTML sink detected (dangerouslySetInnerHTML / innerHTML).",
                    "nodeIds": [node["id"]],
                    "edgeIds": [],
                    "assumed": False,
                })

    text_hints = record.get("securityHints") or []
    for hint in text_hints:
        flags.append({
            "id": hint.get("id") or f"hint:{hint.get('ruleId')}",
            "severity": hint.get("severity", "medium"),
            "ruleId": hint.get("ruleId", "hint"),
            "message": hint.get("message", "Security hint"),
            "nodeIds": hint.get("nodeIds") or ([graph["rootId"]] if graph.get("rootId") in nodes else []),
            "edgeIds": [],
            "assumed": bool(hint.get("assumed", True)),
        })

    return flags


def flag_react_lifecycle_security(flows: list[dict]) -> list[dict]:
    flags: list[dict] = []
    for flow in flows:
        for step in flow.get("steps") or []:
            label = step.get("label") or ""
            if step.get("action") == "api_call" and ADMIN_PATH_RE.search(label):
                flags.append({
                    "id": f"admin-api:{flow['id']}:{step['order']}",
                    "severity": "medium",
                    "ruleId": "privileged_client_api",
                    "message": "Mutating/admin-looking client API call without an auth gate in this flow.",
                    "nodeIds": [],
                    "edgeIds": [],
                    "assumed": True,
                })
            if step.get("action") == "navigate" and "location" in label.lower():
                flags.append({
                    "id": f"navigate:{flow['id']}:{step['order']}",
                    "severity": "medium",
                    "ruleId": "open_redirect_risk",
                    "message": "Navigation step may use user-controlled location; verify input.",
                    "nodeIds": [],
                    "edgeIds": [],
                    "assumed": True,
                })
    return flags


def flag_go_fiber_tree_security(graph: dict | None, record: dict | None = None) -> list[dict]:
    """Flag missing auth middleware and wide-open CORS on route trees."""
    flags: list[dict] = []
    if not graph:
        return flags
    record = record or {}
    routes_by_id = {
        n["id"]: n for n in (graph.get("nodes") or []) if n.get("kind") == "route"
    }

    for node in graph.get("nodes") or []:
        if node.get("kind") != "route":
            continue
        meta = node.get("meta") or {}
        if meta.get("role") == "group":
            continue
        # Leaf route nodes carry method/path.
        if not meta.get("method"):
            continue
        if meta.get("protected"):
            continue
        flags.append({
            "id": f"unauthed-route:{node['id']}",
            "severity": "medium",
            "ruleId": "missing_auth_middleware",
            "message": f"Route {node.get('label')} has no auth/jwt middleware in this file's ordered chain.",
            "nodeIds": [node["id"]],
            "edgeIds": [],
            "assumed": True,
        })

    for mw in record.get("middleware") or []:
        if not mw.get("isCors"):
            continue
        mid = None
        for node in graph.get("nodes") or []:
            if node.get("kind") == "middleware" and node.get("label") == mw.get("name"):
                mid = node["id"]
                break
        flags.append({
            "id": f"cors:{mw.get('name')}:{mw.get('order')}",
            "severity": "low",
            "ruleId": "cors_middleware_present",
            "message": "CORS middleware detected; verify origins are not wide open.",
            "nodeIds": [mid] if mid else ([graph["rootId"]] if graph.get("rootId") in routes_by_id or graph.get("rootId") else []),
            "edgeIds": [],
            "assumed": True,
        })

    return flags


def flag_go_fiber_lifecycle_security(flows: list[dict]) -> list[dict]:
    flags: list[dict] = []
    for flow in flows:
        steps = flow.get("steps") or []
        has_auth_mw = any(
            s.get("action") == "middleware" and (s.get("meta") or {}).get("isAuth")
            for s in steps
        )
        # Auth after handler would be wrong; our builder always puts mw first,
        # but flag if a middleware step appears after the handler step.
        handler_order = next((s["order"] for s in steps if s.get("action") == "handler"), None)
        for step in steps:
            if (
                step.get("action") == "middleware"
                and handler_order is not None
                and step.get("order", 0) > handler_order
            ):
                flags.append({
                    "id": f"mw-order:{flow['id']}:{step['order']}",
                    "severity": "high",
                    "ruleId": "middleware_after_handler",
                    "message": "Middleware step appears after the handler in this flow ordering.",
                    "nodeIds": [],
                    "edgeIds": [],
                    "assumed": True,
                })
        if not has_auth_mw and not (flow.get("meta") or {}).get("protected"):
            flags.append({
                "id": f"unauthed-flow:{flow['id']}",
                "severity": "medium",
                "ruleId": "missing_auth_middleware",
                "message": f"Lifecycle for {flow.get('title')} has no auth middleware step in this file.",
                "nodeIds": [],
                "edgeIds": [],
                "assumed": True,
            })
        for step in steps:
            if step.get("action") == "db" and "concat" in (step.get("label") or "").lower():
                flags.append({
                    "id": f"sql:{flow['id']}:{step['order']}",
                    "severity": "high",
                    "ruleId": "sql_string_concat",
                    "message": "Database step label suggests string-concat SQL; verify parameterization.",
                    "nodeIds": [],
                    "edgeIds": [],
                    "assumed": True,
                })
    return flags
