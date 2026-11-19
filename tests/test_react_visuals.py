"""React visual Slice A — mounts, graphs, lifecycle, honesty gates."""

from __future__ import annotations

import json
from pathlib import Path

from src.extract import ts_extractor as ts
from src.extract.json_builder import build_frontend_chunk_record
from src.chunk.chunk_splitter import ChunkPlan
from src.storage.mirror_store import EXTRACTOR_VERSION, needs_reanalysis, write_stored
from src.visual.availability import is_present
from src.visual.graph_builder import build_react_component_tree
from src.visual.lifecycle_builder import build_react_lifecycle_flows, select_top_lifecycle_flows
from src.visual.pipeline import attach_visuals
from src.visual.package_interactive import (
    canvas_react_node_detail,
    package_react_interactive_breakdown,
)
from src.narrate.tree_script import build_tree_beats
from src.narrate.lifecycle_script import build_lifecycle_beats
from src.narrate.breakdown_script import script_breakdown_teaser

FIXTURE = Path(__file__).parent / "fixtures" / "react" / "UserMenu.tsx"


def _user_menu_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_jsx_mounts_from_user_menu_fixture():
    text = _user_menu_text()
    functions = ts.extract_functions(text)
    mounts, _providers = ts.extract_jsx_mounts(text, functions, "UserMenu")
    children = {(m.parent, m.child, m.assumed) for m in mounts}
    assert ("UserMenu", "Avatar", False) in children
    assert ("UserMenu", "Button", False) in children
    assert ("UserMenu", "MenuItem", True) in children  # inside items.map
    avatar = next(m for m in mounts if m.child == "Avatar")
    prop_names = {p.name for p in avatar.props}
    assert "name" in prop_names
    assert "src" in prop_names


def test_extract_hooks_and_callback_outputs():
    text = _user_menu_text()
    functions = ts.extract_functions(text)
    hooks = ts.extract_hooks(text, functions, "UserMenu")
    hook_names = {h.name for h in hooks}
    assert "useState" in hook_names
    assert "useCallback" in hook_names
    mounts, _ = ts.extract_jsx_mounts(text, functions, "UserMenu")
    outputs = ts.callback_outputs_from_mounts(mounts)
    assert any(o["name"] == "onClick" for o in outputs)


def test_react_mount_golden_sorted_edges():
    text = _user_menu_text()
    functions = ts.extract_functions(text)
    mounts, providers = ts.extract_jsx_mounts(text, functions, "UserMenu")
    record = {
        "filePath": "src/features/widgets/UserMenu.tsx",
        "chunkId": "UserMenu",
        "lineRange": [1, 50],
        "jsxMounts": [
            {
                "parent": m.parent,
                "child": m.child,
                "line": m.line,
                "assumed": m.assumed,
                "props": [
                    {
                        "name": p.name,
                        "valueKind": p.value_kind,
                        "valuePreview": p.value_preview,
                        "assumed": p.assumed,
                    }
                    for p in m.props
                ],
            }
            for m in mounts
        ],
        "jsxProviders": [{"name": p.name, "line": p.line, "assumed": p.assumed} for p in providers],
        "inputs": [{"name": "userName"}],
    }
    graph = build_react_component_tree(record)
    assert graph is not None
    assert graph["kind"] == "component_tree"
    edge_ids = [e["id"] for e in graph["edges"]]
    assert edge_ids == sorted(edge_ids)
    mount_edges = [e for e in graph["edges"] if e["kind"] == "mounts"]
    assert any(e["assumed"] for e in mount_edges)
    assert any(not e["assumed"] for e in mount_edges)


def test_react_handler_flow_golden():
    text = _user_menu_text()
    functions = ts.extract_functions(text)
    handlers = ts.extract_event_handlers(text, functions)
    api_calls = ts.extract_api_calls(text)
    hooks = ts.extract_hooks(text, functions, "UserMenu")
    handler_bodies = {fn.name: list(fn.line_range) for fn in functions if fn.is_event_handler}
    event_handlers = []
    for h in handlers:
        lr = handler_bodies.get(h.name, [h.line, h.line])
        event_handlers.append({
            "name": h.name,
            "lineRange": lr,
            "assumed": h.assumed,
        })
    record = {
        "filePath": "src/features/widgets/UserMenu.tsx",
        "eventHandlers": event_handlers,
        "apiCalls": [
            {
                "method": c.method,
                "url": c.url,
                "assumed": c.url_is_template,
                "line": c.line,
            }
            for c in api_calls
        ],
        "hooks": [
            {"name": h.name, "kind": h.kind, "line": h.line, "owner": h.owner, "assumed": h.assumed}
            for h in hooks
        ],
        "fidelity": "regex",
    }
    flows = build_react_lifecycle_flows(record)
    assert flows
    logout = next(f for f in flows if f["title"] == "handleLogout")
    actions = [s["action"] for s in logout["steps"]]
    assert actions[0] == "event"
    assert "api_call" in actions
    assert logout["title"] == "handleLogout"  # code trigger, not business epic
    assert select_top_lifecycle_flows(flows, n=2) <= flows or len(select_top_lifecycle_flows(flows, n=2)) <= 2


def test_tree_script_hedges_assumed():
    graph = {
        "rootId": "component:UserMenu",
        "nodes": [
            {"id": "component:UserMenu", "label": "UserMenu"},
            {"id": "component:MenuItem", "label": "MenuItem"},
        ],
        "edges": [
            {
                "id": "m1",
                "kind": "mounts",
                "from": "component:UserMenu",
                "to": "component:MenuItem",
                "assumed": True,
            }
        ],
    }
    beats = build_tree_beats(graph, "react", "partial")
    spoken = " ".join(b["spoken"] for b in beats)
    assert "It looks like" in spoken


def test_assumed_step_hedge():
    flow = {
        "id": "flow:x",
        "title": "handleClick",
        "steps": [
            {"order": 1, "action": "event", "label": "handleClick", "assumed": False},
            {"order": 2, "action": "api_call", "label": "POST /x", "assumed": True},
        ],
    }
    beats = build_lifecycle_beats(flow)
    assert any("It looks like" in b["spoken"] for b in beats)


def test_teaser_copy_file_scoped():
    beats = script_breakdown_teaser({"filePath": "src/features/widgets/UserMenu.tsx"})
    assert "UserMenu.tsx" in beats[0]["spoken"]
    assert "checkout" not in beats[0]["spoken"].lower()


def test_availability_placeholder_unavailable():
    record = attach_visuals({
        "chunkId": "py1",
        "filePath": "app.py",
        "stack": "python",
        "notes": "Extraction for stack 'python' is not yet implemented in Phase 3.",
        "confidence": 0,
        "confidenceLevel": "low",
        "projectType": {"frontend": None, "backend": ["python"]},
    }, stack="python")
    avail = record["visualAvailability"]
    assert avail["componentTree"] == "unavailable"
    assert avail["lifecycleFlow"] == "unavailable"
    assert avail["interactiveBreakdown"] == "unavailable"
    assert record.get("visualGraph") is None


def test_angular_empty_valid_no_tree():
    record = attach_visuals({
        "chunkId": "ng1",
        "filePath": "foo.component.ts",
        "stack": "angular",
        "jsxMounts": [],
        "eventHandlers": [],
        "projectType": {"frontend": "angular", "backend": []},
        "confidence": 0.3,
    }, stack="angular")
    assert record["visualAvailability"]["componentTree"] == "unavailable"
    assert build_react_component_tree(record) is None


def test_full_frontend_record_from_fixture(tmp_path):
    """End-to-end: write UserMenu into a tiny React repo and build the record."""
    root = tmp_path
    (root / "package.json").write_text(json.dumps({
        "dependencies": {"react": "^19.0.0", "axios": "^1.9.0"},
    }))
    dest = root / "src" / "features" / "widgets" / "UserMenu.tsx"
    dest.parent.mkdir(parents=True)
    dest.write_text(_user_menu_text())
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "api" / "client.ts").write_text(
        "import axios from 'axios';\nexport const api = axios.create({ baseURL: '/api/v1' });\n"
    )

    chunk = ChunkPlan(
        chunk_id="UserMenu",
        feature_name="Widgets",
        stack="react",
        file_path="src/features/widgets/UserMenu.tsx",
        total_lines=50,
        size_class="small",
    )
    record = build_frontend_chunk_record(
        root, chunk, {"frontend": "react", "backend": []}, "", None,
    )
    assert record["extractorVersion"] == EXTRACTOR_VERSION == 7
    assert record["fidelity"] == "regex"
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "component_tree"
    assert is_present(record["visualAvailability"]["lifecycleFlow"])
    assert record["lifecycleFlows"]
    assert is_present(record["visualAvailability"]["interactiveBreakdown"])
    payload = package_react_interactive_breakdown(record)
    assert payload is not None
    assert "http://" not in json.dumps(payload)
    root_node = next(n for n in payload["visualGraph"]["nodes"] if n["id"] == payload["visualGraph"]["rootId"])
    detail = canvas_react_node_detail(root_node, payload["visualGraph"], payload["lifecycleFlows"])
    assert "UserMenu" in (detail["label"] or "")
    assert detail["filePath"]


def test_refuse_empty_canvas_payload():
    record = attach_visuals({
        "chunkId": "empty",
        "filePath": "Empty.tsx",
        "stack": "react",
        "jsxMounts": [],
        "projectType": {"frontend": "react", "backend": []},
        "confidence": 0.3,
    }, stack="react")
    assert package_react_interactive_breakdown(record) is None


def test_extractor_version_bump_invalidates(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    source = root / "x.tsx"
    source.write_text("export const X = () => null;\n")
    output = tmp_path / "out"
    # relative path as used by mirror_store
    file_path = "x.tsx"
    (tmp_path / file_path).write_text("export const X = () => null;\n")
    write_stored(output, file_path, {
        "contentHash": "deadbeef",
        "extractorVersion": EXTRACTOR_VERSION - 1,
        "filePath": file_path,
    })
    # Force hash match path: rewrite stored with real hash but old version
    from src.extract.common import content_hash
    h = content_hash(tmp_path, file_path)
    write_stored(output, file_path, {
        "contentHash": h,
        "extractorVersion": EXTRACTOR_VERSION - 1,
        "filePath": file_path,
    })
    stale, _ = needs_reanalysis(output, tmp_path, file_path)
    assert stale is True


def test_top_n_cap():
    flows = [{"id": f"f{i}", "title": f"h{i}", "steps": []} for i in range(5)]
    assert len(select_top_lifecycle_flows(flows, n=2)) == 2


def test_flow_title_is_code_trigger():
    flows = build_react_lifecycle_flows({
        "filePath": "X.tsx",
        "eventHandlers": [{"name": "handleSubmit", "lineRange": [10, 20], "assumed": False}],
        "apiCalls": [],
        "hooks": [],
        "fidelity": "regex",
    })
    assert flows[0]["title"] == "handleSubmit"
    assert "checkout" not in flows[0]["title"].lower()
