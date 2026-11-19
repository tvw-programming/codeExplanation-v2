"""Build ordered lifecycleFlows from extracted handler / hook / api facts."""

from __future__ import annotations

from pathlib import Path


def select_top_lifecycle_flows(flows: list[dict], n: int = 2) -> list[dict]:
    """Cap video synthesis at n flows per chunk (remaining stay in JSON)."""
    return list(flows[:n])


def build_react_lifecycle_flows(record: dict) -> list[dict]:
    """eventHandlers → hooks / state → apiCalls as ordered steps for this file.

    Titles are code triggers (handler names), never business-epic labels.
    Under fidelity regex, hook attribution steps are marked assumed.
    """
    handlers = record.get("eventHandlers") or []
    api_calls = record.get("apiCalls") or []
    hooks = record.get("hooks") or []
    fidelity = record.get("fidelity") or "regex"
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "component"

    flows: list[dict] = []
    for h in handlers:
        name = h.get("name") or "handler"
        # Skip anonymous inline noise for titles when we have named handlers;
        # still include them if they are the only triggers.
        steps: list[dict] = []
        order = 1
        line = (h.get("lineRange") or [None])[0]
        steps.append({
            "order": order,
            "action": "event",
            "label": name,
            "nodeId": None,
            "lineRange": h.get("lineRange"),
            "assumed": bool(h.get("assumed")),
        })
        order += 1

        # Component-owned state hooks only. useCallback/useMemo are the
        # handlers themselves — do not re-list them as separate steps.
        for hook in hooks:
            kind = hook.get("kind") or hook.get("name") or ""
            if kind in ("useCallback", "useMemo", "useRef"):
                continue
            owner = hook.get("owner")
            if owner and owner not in (stem, name):
                continue
            steps.append({
                "order": order,
                "action": "state_update" if kind in ("useState", "useReducer") else "other",
                "label": hook.get("name") or "hook",
                "nodeId": None,
                "lineRange": [hook["line"], hook["line"]] if hook.get("line") else None,
                "assumed": fidelity == "regex" or bool(hook.get("assumed")),
            })
            order += 1

        # API calls in this chunk — link when handler body likely contains them
        # (line within handler range when known; else assumed association).
        handler_range = h.get("lineRange") or [line, line]
        h_start = handler_range[0] if handler_range else None
        h_end = handler_range[-1] if handler_range else None
        for call in api_calls:
            call_line = call.get("line")
            in_body = (
                call_line is not None
                and h_start is not None
                and h_end is not None
                and h_start <= call_line <= h_end
            )
            # Only attach API calls that fall inside this handler's body
            # range. Do not invent cross-handler associations.
            if not in_body:
                continue
            steps.append({
                "order": order,
                "action": "api_call",
                "label": f"{call.get('method', '')} {call.get('url', '')}".strip(),
                "nodeId": None,
                "lineRange": [call_line, call_line] if call_line else None,
                "assumed": bool(call.get("assumed")),
            })
            order += 1

        steps.append({
            "order": order,
            "action": "render",
            "label": "re-render",
            "nodeId": None,
            "lineRange": None,
            "assumed": True,  # regex fidelity cannot verify render boundary
        })

        # Hard skip: single meaningless step with no handler body facts
        meaningful = [s for s in steps if s["action"] != "render"]
        if len(meaningful) <= 1 and all(s.get("assumed") for s in meaningful):
            # Still allow a named handler with only the event step + assumed render
            # if the handler itself is verified.
            if h.get("assumed") and len(meaningful) <= 1:
                continue

        flow_assumed = any(s.get("assumed") for s in steps)
        flows.append({
            "id": f"flow:{stem}:{name}",
            "title": name,  # code trigger
            "trigger": name,
            "steps": steps,
            "assumed": flow_assumed,
            "confidence": 0.5 if flow_assumed else 0.8,
        })

    # Prefer named handlers first.
    flows.sort(key=lambda f: (1 if str(f["title"]).startswith("inline_") else 0, f["title"]))
    return flows


def build_go_fiber_lifecycle_flows(record: dict) -> list[dict]:
    """Ordered middleware → handler → service/db → response per route in this file.

    Titles are HTTP code triggers (`GET /api/v1/users`), never business epics.
    """
    routes = record.get("routes") or []
    if not routes:
        return []

    functions = {
        (fn.get("name") or ""): fn
        for fn in (record.get("importantFunctions") or [])
    }
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "main"
    fidelity = record.get("fidelity") or "regex"

    flows: list[dict] = []
    for route in routes:
        method = (route.get("method") or "?").upper()
        path = route.get("path") or "/"
        title = f"{method} {path}"
        handler = route.get("handler") or "handler"
        handler_short = handler.split(".")[-1]
        steps: list[dict] = []
        order = 1

        for mw in route.get("middleware") or []:
            steps.append({
                "order": order,
                "action": "middleware",
                "label": mw.get("name") or "middleware",
                "nodeId": None,
                "lineRange": [mw["line"], mw["line"]] if mw.get("line") else None,
                "assumed": bool(mw.get("assumed", True)),
                "meta": {
                    "isAuth": bool(mw.get("isAuth")),
                    "isCors": bool(mw.get("isCors")),
                },
            })
            order += 1

        fn = functions.get(handler_short) or functions.get(handler)
        handler_range = list(fn["lineRange"]) if fn and fn.get("lineRange") else (
            [route["line"], route["line"]] if route.get("line") else None
        )
        steps.append({
            "order": order,
            "action": "handler",
            "label": handler_short,
            "nodeId": None,
            "lineRange": handler_range,
            "assumed": False,
        })
        order += 1

        # Body facts from the handler's own function_context only —
        # never invent cross-handler associations from file-level lists.
        body_effects: list[tuple[str, str]] = []
        if fn:
            for callee in fn.get("calls") or []:
                # calls_made returns bare names (strings).
                name = callee if isinstance(callee, str) else (
                    callee.get("name") or callee.get("callee") or ""
                )
                if name:
                    body_effects.append(("service_call", name))
            for se in fn.get("sideEffects") or []:
                kind = se if isinstance(se, str) else (se.get("type") or se.get("kind") or "other")
                action = "db" if "database" in str(kind) or kind == "db" else "other"
                body_effects.append((action, str(kind)))

        for action, label in body_effects[:4]:
            steps.append({
                "order": order,
                "action": action,
                "label": label,
                "nodeId": None,
                "lineRange": None,
                "assumed": fidelity == "regex",
            })
            order += 1

        steps.append({
            "order": order,
            "action": "response",
            "label": "response write",
            "nodeId": None,
            "lineRange": None,
            "assumed": True,  # regex cannot verify Ctx write sites reliably
        })

        # Hard skip: only assumed response with no handler identity
        if not handler_short or handler_short == "func":
            continue

        flow_assumed = any(s.get("assumed") for s in steps) or bool(route.get("assumed"))
        # Partial when middleware chain empty — still emit flow (handler→response).
        flows.append({
            "id": f"flow:{stem}:{method}:{path}",
            "title": title,
            "trigger": title,
            "steps": steps,
            "assumed": flow_assumed,
            "confidence": 0.45 if flow_assumed else 0.75,
            "meta": {
                "protected": bool(route.get("protected")),
                "hasMiddleware": bool(route.get("middleware")),
            },
        })

    # Prefer routes that have middleware (richer teaching), then path.
    flows.sort(key=lambda f: (
        0 if (f.get("meta") or {}).get("hasMiddleware") else 1,
        f.get("title") or "",
    ))
    return flows
