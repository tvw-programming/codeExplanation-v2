"""Pure graph builders: chunk record → visualGraph (no re-parse to invent edges)."""

from __future__ import annotations

from pathlib import Path


def _node_id(kind: str, name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    return f"{kind}:{safe}"


def build_react_component_tree(record: dict) -> dict | None:
    """Build a component_tree from jsxMounts on the record.

    Returns None when there is nothing honest to draw (no mounts, or
    only a single orphan root with zero edges).
    """
    mounts = record.get("jsxMounts") or []
    if not mounts:
        return None

    file_path = record.get("filePath") or ""
    root_name = Path(file_path).stem if file_path else (record.get("chunkId") or "Component")
    root_id = _node_id("component", root_name)

    nodes: dict[str, dict] = {
        root_id: {
            "id": root_id,
            "kind": "component",
            "label": root_name,
            "filePath": file_path,
            "line": (record.get("lineRange") or [1])[0],
            "assumed": False,
            "meta": {"role": "root"},
        }
    }
    edges: list[dict] = []

    for i, mount in enumerate(mounts):
        parent = mount.get("parent") or root_name
        child = mount.get("child")
        if not child:
            continue
        parent_id = _node_id("component", parent)
        child_id = _node_id("component", child)
        if parent_id not in nodes:
            nodes[parent_id] = {
                "id": parent_id,
                "kind": "component",
                "label": parent,
                "filePath": file_path,
                "line": mount.get("line"),
                "assumed": False,
                "meta": {},
            }
        if child_id not in nodes:
            nodes[child_id] = {
                "id": child_id,
                "kind": "component",
                "label": child,
                "filePath": file_path,
                "line": mount.get("line"),
                "assumed": bool(mount.get("assumed")),
                "meta": {"props": mount.get("props") or []},
            }
        edge_id = f"mounts:{parent_id}->{child_id}:{i}"
        edges.append({
            "id": edge_id,
            "kind": "mounts",
            "from": parent_id,
            "to": child_id,
            "assumed": bool(mount.get("assumed")),
            "label": None,
            "meta": {"props": mount.get("props") or []},
        })
        for prop in mount.get("props") or []:
            pname = prop.get("name")
            if not pname:
                continue
            edges.append({
                "id": f"prop:{parent_id}->{child_id}:{pname}:{i}",
                "kind": "passes_prop",
                "from": parent_id,
                "to": child_id,
                "assumed": bool(prop.get("assumed")),
                "label": pname,
                "meta": {
                    "valueKind": prop.get("valueKind"),
                    "valuePreview": prop.get("valuePreview"),
                },
            })

    # Providers (dashed containers) from jsxProviders if present.
    for i, prov in enumerate(record.get("jsxProviders") or []):
        name = prov.get("name")
        if not name:
            continue
        pid = _node_id("provider", name)
        nodes[pid] = {
            "id": pid,
            "kind": "provider",
            "label": name,
            "filePath": file_path,
            "line": prov.get("line"),
            "assumed": bool(prov.get("assumed")),
            "meta": {"container": True},
        }
        edges.append({
            "id": f"provides:{pid}->{root_id}:{i}",
            "kind": "provides",
            "from": pid,
            "to": root_id,
            "assumed": True,
            "label": None,
            "meta": {},
        })

    if not edges:
        return None

    return {
        "schemaVersion": 1,
        "kind": "component_tree",
        "rootId": root_id,
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: e["id"]),
    }


def build_go_fiber_route_tree(record: dict) -> dict | None:
    """Build a route_tree from Fiber routes + ordered middleware in this file.

    Nodes are app/group/route/handler/middleware for the chunk unit only.
    Returns None when there are no routes or no structural edges.
    """
    routes = record.get("routes") or []
    if not routes:
        return None

    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else (record.get("chunkId") or "main")
    root_id = _node_id("module", stem)
    nodes: dict[str, dict] = {
        root_id: {
            "id": root_id,
            "kind": "module",
            "label": stem,
            "filePath": file_path,
            "line": (record.get("lineRange") or [1])[0],
            "assumed": False,
            "meta": {"role": "root", "usesFiber": bool(record.get("usesFiber"))},
        }
    }
    edges: list[dict] = []

    # Group nodes from routeGroups when present.
    group_parents = {
        g["var"]: (g.get("parent"), g.get("prefix") or "")
        for g in (record.get("routeGroups") or [])
        if g.get("var")
    }
    group_full: dict[str, str] = {}
    for var, (parent, prefix) in group_parents.items():
        segments: list[str] = [prefix.rstrip("/")]
        cur = parent
        seen: set[str] = set()
        while cur in group_parents and cur not in seen:
            seen.add(cur)
            p_parent, p_prefix = group_parents[cur]
            segments.append((p_prefix or "").rstrip("/"))
            cur = p_parent
        group_full[var] = "".join(reversed(segments))

    for var, full_prefix in sorted(group_full.items(), key=lambda kv: kv[1]):
        gid = _node_id("route", f"group:{var}")
        parent_var = group_parents[var][0]
        parent_id = (
            _node_id("route", f"group:{parent_var}")
            if parent_var in group_parents
            else root_id
        )
        if parent_id not in nodes and parent_id != root_id:
            nodes[parent_id] = {
                "id": parent_id,
                "kind": "route",
                "label": parent_var,
                "filePath": file_path,
                "line": None,
                "assumed": True,
                "meta": {"routerVar": parent_var, "role": "group"},
            }
        nodes[gid] = {
            "id": gid,
            "kind": "route",
            "label": full_prefix or f"/{var}",
            "filePath": file_path,
            "line": None,
            "assumed": False,
            "meta": {"routerVar": var, "role": "group", "prefix": full_prefix},
        }
        edges.append({
            "id": f"routes_to:{parent_id}->{gid}",
            "kind": "routes_to",
            "from": parent_id,
            "to": gid,
            "assumed": False,
            "label": None,
            "meta": {},
        })

    # File-level middleware nodes (unique by name+routerVar).
    seen_mw: set[str] = set()
    for i, mw in enumerate(record.get("middleware") or []):
        name = mw.get("name") or "middleware"
        rvar = mw.get("routerVar") or "app"
        mid = _node_id("middleware", f"{rvar}:{name}:{mw.get('order', i)}")
        if mid in seen_mw:
            continue
        seen_mw.add(mid)
        nodes[mid] = {
            "id": mid,
            "kind": "middleware",
            "label": name,
            "filePath": file_path,
            "line": mw.get("line"),
            "assumed": bool(mw.get("assumed", True)),
            "meta": {
                "isAuth": bool(mw.get("isAuth")),
                "isCors": bool(mw.get("isCors")),
                "order": mw.get("order", i),
                "routerVar": rvar,
                "source": mw.get("source"),
            },
        }
        attach_id = (
            _node_id("route", f"group:{rvar}")
            if rvar in group_parents
            else root_id
        )
        if attach_id not in nodes:
            attach_id = root_id
        edges.append({
            "id": f"middleware_before:{mid}->{attach_id}:{i}",
            "kind": "middleware_before",
            "from": mid,
            "to": attach_id,
            "assumed": bool(mw.get("assumed", True)),
            "label": None,
            "meta": {"fiberAccent": True},
        })

    for i, route in enumerate(routes):
        method = (route.get("method") or "?").upper()
        path = route.get("path") or "/"
        label = f"{method} {path}"
        rid = _node_id("route", f"{method}:{path}")
        rvar = route.get("routerVar") or ""
        parent_id = (
            _node_id("route", f"group:{rvar}")
            if rvar in group_parents
            else root_id
        )
        if parent_id not in nodes:
            parent_id = root_id
        nodes[rid] = {
            "id": rid,
            "kind": "route",
            "label": label,
            "filePath": file_path,
            "line": route.get("line"),
            "assumed": bool(route.get("assumed")),
            "meta": {
                "method": method,
                "path": path,
                "protected": bool(route.get("protected")),
                "routerVar": rvar,
                "type": route.get("type"),
            },
        }
        edges.append({
            "id": f"routes_to:{parent_id}->{rid}:{i}",
            "kind": "routes_to",
            "from": parent_id,
            "to": rid,
            "assumed": bool(route.get("assumed")),
            "label": None,
            "meta": {},
        })

        handler = route.get("handler") or ""
        if handler and handler != "func":
            # Prefer last path segment for package.Handler display.
            display = handler.split(".")[-1]
            hid = _node_id("handler", handler)
            nodes[hid] = {
                "id": hid,
                "kind": "handler",
                "label": display,
                "filePath": file_path,
                "line": route.get("line"),
                "assumed": False,
                "meta": {"qualified": handler},
            }
            edges.append({
                "id": f"routes_to:{rid}->{hid}:{i}",
                "kind": "routes_to",
                "from": rid,
                "to": hid,
                "assumed": False,
                "label": None,
                "meta": {},
            })

        # Per-route middleware_before edges (ordered chain → this route).
        for j, mw in enumerate(route.get("middleware") or []):
            name = mw.get("name") or "middleware"
            rvar_mw = mw.get("routerVar") or rvar
            mid = _node_id("middleware", f"{rvar_mw}:{name}:{mw.get('order', j)}")
            if mid not in nodes:
                nodes[mid] = {
                    "id": mid,
                    "kind": "middleware",
                    "label": name,
                    "filePath": file_path,
                    "line": mw.get("line"),
                    "assumed": bool(mw.get("assumed", True)),
                    "meta": {
                        "isAuth": bool(mw.get("isAuth")),
                        "isCors": bool(mw.get("isCors")),
                        "order": mw.get("order", j),
                        "routerVar": rvar_mw,
                    },
                }
            edges.append({
                "id": f"middleware_before:{mid}->{rid}:{i}:{j}",
                "kind": "middleware_before",
                "from": mid,
                "to": rid,
                "assumed": bool(mw.get("assumed", True)),
                "label": None,
                "meta": {"fiberAccent": True, "order": mw.get("order", j)},
            })

    if not edges:
        return None

    return {
        "schemaVersion": 1,
        "kind": "route_tree",
        "rootId": root_id,
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: e["id"]),
    }
