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
