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


def _finish(kind: str, root_id: str, nodes: dict, edges: list) -> dict | None:
    if not edges:
        return None
    return {
        "schemaVersion": 1,
        "kind": kind,
        "rootId": root_id,
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges, key=lambda e: e["id"]),
    }


def build_generic_route_tree(record: dict, stack: str = "express") -> dict | None:
    """Shared route_tree for Express / Python / Rust route lists."""
    routes = record.get("routes") or []
    if not routes:
        return None
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else (record.get("chunkId") or "routes")
    root_id = _node_id("module", stem)
    nodes = {
        root_id: {
            "id": root_id, "kind": "module", "label": stem, "filePath": file_path,
            "line": (record.get("lineRange") or [1])[0], "assumed": False,
            "meta": {"role": "root", "stack": stack},
        }
    }
    edges: list[dict] = []
    for i, route in enumerate(routes):
        method = (route.get("method") or "?").upper()
        path = route.get("path") or "/"
        rid = _node_id("route", f"{method}:{path}")
        nodes[rid] = {
            "id": rid, "kind": "route", "label": f"{method} {path}",
            "filePath": file_path, "line": route.get("line"),
            "assumed": bool(route.get("assumed")),
            "meta": {"method": method, "path": path, "protected": bool(route.get("protected"))},
        }
        edges.append({
            "id": f"routes_to:{root_id}->{rid}:{i}", "kind": "routes_to",
            "from": root_id, "to": rid, "assumed": bool(route.get("assumed")),
            "label": None, "meta": {},
        })
        handler = route.get("handler")
        if handler and handler not in ("handler", "func"):
            hid = _node_id("handler", handler)
            nodes[hid] = {
                "id": hid, "kind": "handler", "label": handler.split(".")[-1],
                "filePath": file_path, "line": route.get("line"), "assumed": False, "meta": {},
            }
            edges.append({
                "id": f"routes_to:{rid}->{hid}:{i}", "kind": "routes_to",
                "from": rid, "to": hid, "assumed": False, "label": None, "meta": {},
            })
        for j, dep in enumerate(route.get("depends") or []):
            did = _node_id("provider", dep)
            nodes[did] = {
                "id": did, "kind": "provider", "label": dep, "filePath": file_path,
                "line": None, "assumed": True, "meta": {"depends": True},
            }
            edges.append({
                "id": f"depends_on:{rid}->{did}:{j}", "kind": "depends_on",
                "from": rid, "to": did, "assumed": True, "label": None, "meta": {},
            })
        for j, mw in enumerate(route.get("middleware") or []):
            mid = _node_id("middleware", f"{mw.get('name')}:{mw.get('order', j)}")
            nodes[mid] = {
                "id": mid, "kind": "middleware", "label": mw.get("name") or "mw",
                "filePath": file_path, "line": mw.get("line"),
                "assumed": bool(mw.get("assumed", True)),
                "meta": {"isAuth": bool(mw.get("isAuth"))},
            }
            edges.append({
                "id": f"middleware_before:{mid}->{rid}:{i}:{j}", "kind": "middleware_before",
                "from": mid, "to": rid, "assumed": True, "label": None, "meta": {},
            })
    return _finish("route_tree", root_id, nodes, edges)


def build_python_structure_tree(record: dict) -> dict | None:
    routes = record.get("routes") or []
    imports = record.get("imports") or []
    if routes:
        return build_generic_route_tree(record, stack="python")
    if not imports:
        return None
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "module"
    root_id = _node_id("module", stem)
    nodes = {
        root_id: {
            "id": root_id, "kind": "module", "label": stem, "filePath": file_path,
            "line": 1, "assumed": False, "meta": {"role": "root"},
        }
    }
    edges: list[dict] = []
    for i, imp in enumerate(imports[:40]):
        mod = imp.get("module") or ""
        if not mod:
            continue
        mid = _node_id("module", mod)
        nodes[mid] = {
            "id": mid, "kind": "module", "label": mod, "filePath": file_path,
            "line": imp.get("line"), "assumed": False, "meta": {},
        }
        edges.append({
            "id": f"imports:{root_id}->{mid}:{i}", "kind": "imports",
            "from": root_id, "to": mid, "assumed": False, "label": None, "meta": {},
        })
    return _finish("module_graph", root_id, nodes, edges)


def build_spring_di_tree(record: dict) -> dict | None:
    types = record.get("springTypes") or []
    if not types:
        # Fall back to routes only
        return build_generic_route_tree(record, stack="spring_boot")
    file_path = record.get("filePath") or ""
    # Prefer a controller as root when present
    root_type = next((t for t in types if t.get("stereotype") in ("RestController", "Controller")), types[0])
    root_id = _node_id("controller", root_type["name"])
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for t in types:
        kind = {
            "RestController": "controller", "Controller": "controller",
            "Service": "service", "Repository": "repository",
        }.get(t.get("stereotype") or "", "component")
        tid = _node_id(kind, t["name"])
        nodes[tid] = {
            "id": tid, "kind": kind, "label": t["name"], "filePath": file_path,
            "line": t.get("line"), "assumed": False,
            "meta": {"stereotype": t.get("stereotype"), "classPath": t.get("classPath")},
        }
        for i, inj in enumerate(t.get("injectees") or []):
            typ = inj.get("type") or "Unknown"
            iid = _node_id("service", typ)  # interface/type boundary
            if iid not in nodes:
                nodes[iid] = {
                    "id": iid, "kind": "service", "label": typ, "filePath": file_path,
                    "line": None, "assumed": True,
                    "meta": {"interfaceOnly": True, "note": "Impl selected at runtime if not in this file"},
                }
            edges.append({
                "id": f"injects:{tid}->{iid}:{i}", "kind": "injects",
                "from": tid, "to": iid, "assumed": bool(inj.get("assumed", False)),
                "label": inj.get("field"), "meta": {"via": inj.get("via")},
            })
    # Also attach routes as children of controller
    for i, route in enumerate(record.get("routes") or []):
        method = (route.get("method") or "?").upper()
        path = route.get("path") or "/"
        rid = _node_id("route", f"{method}:{path}")
        parent = _node_id("controller", route.get("controller") or root_type["name"])
        if parent not in nodes:
            parent = root_id
        nodes[rid] = {
            "id": rid, "kind": "route", "label": f"{method} {path}",
            "filePath": file_path, "line": route.get("line"),
            "assumed": bool(route.get("assumed")),
            "meta": {"method": method, "path": path, "protected": bool(route.get("protected"))},
        }
        edges.append({
            "id": f"routes_to:{parent}->{rid}:{i}", "kind": "routes_to",
            "from": parent, "to": rid, "assumed": False, "label": None, "meta": {},
        })
    if root_id not in nodes and nodes:
        root_id = next(iter(nodes))
    return _finish("di_graph", root_id, nodes, edges)


def build_angular_selector_tree(record: dict) -> dict | None:
    """Angular component_tree: selector provides, I/O binds, injects, template mounts.

    Mount edges come only from record jsxMounts produced by the selector
    index — unmatched template tags are never invented here.
    """
    comp = record.get("angularComponent")
    if not comp:
        return None
    file_path = record.get("filePath") or ""
    name = comp.get("name") or "Component"
    root_id = _node_id("component", name)
    nodes = {
        root_id: {
            "id": root_id, "kind": "component", "label": name, "filePath": file_path,
            "line": comp.get("line"), "assumed": bool(comp.get("assumed")),
            "meta": {"selector": comp.get("selector"), "templateUrl": comp.get("templateUrl")},
        }
    }
    edges: list[dict] = []
    if comp.get("selector"):
        sid = _node_id("directive", comp["selector"])
        nodes[sid] = {
            "id": sid, "kind": "directive", "label": comp["selector"],
            "filePath": file_path, "line": comp.get("line"), "assumed": False, "meta": {"role": "selector"},
        }
        edges.append({
            "id": f"provides:{root_id}->{sid}", "kind": "provides",
            "from": root_id, "to": sid, "assumed": False, "label": "selector", "meta": {},
        })
    for i, inp in enumerate(record.get("inputs") or []):
        n = inp.get("name") if isinstance(inp, dict) else str(inp)
        iid = _node_id("hook", f"input:{n}")
        nodes[iid] = {
            "id": iid, "kind": "hook", "label": f"@Input {n}", "filePath": file_path,
            "line": None, "assumed": False, "meta": {"binding": "input"},
        }
        edges.append({
            "id": f"input_bind:{iid}->{root_id}:{i}", "kind": "input_bind",
            "from": iid, "to": root_id, "assumed": False, "label": n, "meta": {},
        })
    for i, out in enumerate(record.get("outputs") or []):
        n = out.get("name") if isinstance(out, dict) else str(out)
        oid = _node_id("hook", f"output:{n}")
        nodes[oid] = {
            "id": oid, "kind": "hook", "label": f"@Output {n}", "filePath": file_path,
            "line": None, "assumed": False, "meta": {"binding": "output"},
        }
        edges.append({
            "id": f"output_bind:{root_id}->{oid}:{i}", "kind": "output_bind",
            "from": root_id, "to": oid, "assumed": False, "label": n, "meta": {},
        })
    for i, tok in enumerate(record.get("injectTokens") or []):
        tid = _node_id("provider", tok)
        nodes[tid] = {
            "id": tid, "kind": "provider", "label": tok, "filePath": file_path,
            "line": None, "assumed": True, "meta": {},
        }
        edges.append({
            "id": f"injects:{root_id}->{tid}:{i}", "kind": "injects",
            "from": root_id, "to": tid, "assumed": True, "label": None, "meta": {},
        })

    # Confirmed selector→usage mounts (from extract_template_mounts).
    for i, mount in enumerate(record.get("jsxMounts") or []):
        child = mount.get("child")
        if not child:
            continue
        parent = mount.get("parent") or name
        parent_id = _node_id("component", parent)
        child_id = _node_id("component", child)
        if parent_id not in nodes:
            nodes[parent_id] = {
                "id": parent_id, "kind": "component", "label": parent,
                "filePath": file_path, "line": mount.get("line"),
                "assumed": False, "meta": {},
            }
        if child_id not in nodes:
            nodes[child_id] = {
                "id": child_id, "kind": "component", "label": child,
                "filePath": file_path, "line": mount.get("line"),
                "assumed": bool(mount.get("assumed")),
                "meta": {
                    "selector": mount.get("selector"),
                    "props": mount.get("props") or [],
                },
            }
        edges.append({
            "id": f"mounts:{parent_id}->{child_id}:{i}",
            "kind": "mounts",
            "from": parent_id,
            "to": child_id,
            "assumed": bool(mount.get("assumed")),
            "label": mount.get("selector"),
            "meta": {
                "selector": mount.get("selector"),
                "props": mount.get("props") or [],
                "note": mount.get("note"),
            },
        })
        for prop in mount.get("props") or []:
            pname = prop.get("name") if isinstance(prop, dict) else None
            if not pname:
                continue
            edges.append({
                "id": f"prop:{parent_id}->{child_id}:{pname}:{i}",
                "kind": "passes_prop",
                "from": parent_id,
                "to": child_id,
                "assumed": bool(prop.get("assumed")) if isinstance(prop, dict) else False,
                "label": pname,
                "meta": {
                    "valueKind": prop.get("valueKind") if isinstance(prop, dict) else None,
                    "valuePreview": prop.get("valuePreview") if isinstance(prop, dict) else None,
                },
            })

    return _finish("component_tree", root_id, nodes, edges)


def build_js_module_tree(record: dict) -> dict | None:
    imports = record.get("moduleImports") or []
    exports = record.get("moduleExports") or []
    dom_mounts = record.get("domMounts") or []
    if not imports and not exports and not dom_mounts:
        return None
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "module"
    root_id = _node_id("module", stem)
    nodes = {
        root_id: {
            "id": root_id, "kind": "module", "label": stem, "filePath": file_path,
            "line": 1, "assumed": False, "meta": {"role": "root"},
        }
    }
    edges: list[dict] = []
    for i, imp in enumerate(imports):
        path = imp.get("path") or ""
        mid = _node_id("module", path)
        nodes[mid] = {
            "id": mid, "kind": "module", "label": path, "filePath": file_path,
            "line": imp.get("line"), "assumed": bool(imp.get("assumed")), "meta": {},
        }
        edges.append({
            "id": f"imports:{root_id}->{mid}:{i}", "kind": "imports",
            "from": root_id, "to": mid, "assumed": bool(imp.get("assumed")),
            "label": None, "meta": {},
        })
    for i, exp in enumerate(exports):
        eid = _node_id("handler", exp.get("name") or f"export{i}")
        nodes[eid] = {
            "id": eid, "kind": "handler", "label": exp.get("name"), "filePath": file_path,
            "line": exp.get("line"), "assumed": bool(exp.get("assumed")), "meta": {
                "export": True, "exportKind": exp.get("kind"),
            },
        }
        edges.append({
            "id": f"provides:{root_id}->{eid}:{i}", "kind": "provides",
            "from": root_id, "to": eid, "assumed": bool(exp.get("assumed")),
            "label": None, "meta": {},
        })
    # Literal DOM selector mounts only — never invent from non-literal queries.
    for i, mount in enumerate(dom_mounts):
        sel = mount.get("selector") or ""
        if not sel:
            continue
        mid = _node_id("dom", f"{mount.get('kind')}:{sel}:{mount.get('line', i)}")
        assumed = bool(mount.get("assumed"))
        nodes[mid] = {
            "id": mid, "kind": "dom", "label": sel, "filePath": file_path,
            "line": mount.get("line"), "assumed": assumed,
            "meta": {"domMount": mount.get("kind")},
        }
        edges.append({
            "id": f"mounts:{root_id}->{mid}:{i}", "kind": "mounts",
            "from": root_id, "to": mid, "assumed": assumed,
            "label": mount.get("kind"), "meta": {},
        })
    return _finish("module_graph", root_id, nodes, edges)


def build_rust_crate_or_route_tree(record: dict) -> dict | None:
    if record.get("routes"):
        return build_generic_route_tree(record, stack="rust")
    modules = record.get("rustModules") or []
    uses = record.get("rustUses") or []
    if not modules and not uses:
        return None
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "crate"
    root_id = _node_id("crate", stem)
    nodes = {
        root_id: {
            "id": root_id, "kind": "crate", "label": stem, "filePath": file_path,
            "line": 1, "assumed": False, "meta": {"role": "root"},
        }
    }
    edges: list[dict] = []
    for i, mod in enumerate(modules):
        mid = _node_id("module", mod["name"])
        nodes[mid] = {
            "id": mid, "kind": "module", "label": mod["name"], "filePath": file_path,
            "line": mod.get("line"), "assumed": False, "meta": {},
        }
        edges.append({
            "id": f"owns:{root_id}->{mid}:{i}", "kind": "depends_on",
            "from": root_id, "to": mid, "assumed": False, "label": "mod", "meta": {},
        })
    for i, use in enumerate(uses[:30]):
        uid = _node_id("module", use["path"].replace("::", "."))
        nodes[uid] = {
            "id": uid, "kind": "module", "label": use["path"], "filePath": file_path,
            "line": use.get("line"), "assumed": False, "meta": {},
        }
        edges.append({
            "id": f"imports:{root_id}->{uid}:{i}", "kind": "imports",
            "from": root_id, "to": uid, "assumed": False, "label": None, "meta": {},
        })
    return _finish("crate_graph", root_id, nodes, edges)


def build_qwik_component_tree(record: dict) -> dict | None:
    graph = build_react_component_tree(record)
    if graph is None and not (record.get("qwikBoundaries") or []):
        return None
    if graph is None:
        file_path = record.get("filePath") or ""
        stem = Path(file_path).stem if file_path else "Component"
        root_id = _node_id("component", stem)
        nodes = {
            root_id: {
                "id": root_id, "kind": "component", "label": stem, "filePath": file_path,
                "line": 1, "assumed": False, "meta": {},
            }
        }
        edges: list[dict] = []
    else:
        nodes = {n["id"]: n for n in graph["nodes"]}
        edges = list(graph["edges"])
        root_id = graph["rootId"]
    for i, b in enumerate(record.get("qwikBoundaries") or []):
        bid = _node_id("hook", f"boundary:{b.get('kind')}:{b.get('line', i)}")
        nodes[bid] = {
            "id": bid, "kind": "hook", "label": b.get("name") or b.get("kind"),
            "filePath": record.get("filePath"), "line": b.get("line"),
            "assumed": bool(b.get("assumed")), "meta": {"qwik": True},
        }
        edges.append({
            "id": f"resumable_boundary:{root_id}->{bid}:{i}", "kind": "resumable_boundary",
            "from": root_id, "to": bid, "assumed": bool(b.get("assumed")),
            "label": None, "meta": {"accent": "qwik"},
        })
    return _finish("component_tree", root_id, nodes, edges)


def build_solid_component_tree(record: dict) -> dict | None:
    graph = build_react_component_tree(record)
    file_path = record.get("filePath") or ""
    stem = Path(file_path).stem if file_path else "Component"
    if graph is None:
        if not (record.get("signals") or record.get("effects")):
            return None
        root_id = _node_id("component", stem)
        nodes = {
            root_id: {
                "id": root_id, "kind": "component", "label": stem, "filePath": file_path,
                "line": 1, "assumed": False, "meta": {},
            }
        }
        edges: list[dict] = []
    else:
        nodes = {n["id"]: n for n in graph["nodes"]}
        edges = list(graph["edges"])
        root_id = graph["rootId"]
    for i, sig in enumerate(record.get("signals") or []):
        sid = _node_id("signal", f"{sig.get('kind')}:{sig.get('line', i)}")
        assumed = bool(sig.get("assumed", True))
        owner = sig.get("owner") or stem
        owner_id = _node_id("component", owner)
        if owner_id not in nodes:
            nodes[owner_id] = {
                "id": owner_id, "kind": "component", "label": owner, "filePath": file_path,
                "line": sig.get("line"), "assumed": assumed, "meta": {"solid": True},
            }
        nodes[sid] = {
            "id": sid, "kind": "signal", "label": sig.get("kind"), "filePath": file_path,
            "line": sig.get("line"), "assumed": assumed, "meta": {"solid": True},
        }
        edges.append({
            "id": f"owns_state:{owner_id}->{sid}:{i}", "kind": "owns_state",
            "from": owner_id, "to": sid, "assumed": assumed, "label": None, "meta": {"accent": "solid"},
        })
    return _finish("component_tree", root_id, nodes, edges)
