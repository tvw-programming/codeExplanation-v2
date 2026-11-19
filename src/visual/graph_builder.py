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
