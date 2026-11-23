"""Go Fiber visual slice — route trees, middleware order, honesty gates."""

from __future__ import annotations

import json
from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract import go_extractor as go
from src.extract.json_builder import build_backend_go_chunk_record
from src.narrate.breakdown_script import script_breakdown_teaser
from src.narrate.lifecycle_script import build_lifecycle_beats
from src.narrate.tree_script import build_tree_beats
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present
from src.visual.graph_builder import build_go_fiber_route_tree
from src.visual.lifecycle_builder import build_go_fiber_lifecycle_flows, select_top_lifecycle_flows
from src.visual.package_interactive import (
    canvas_go_fiber_node_detail,
    package_go_fiber_interactive_breakdown,
)
from src.visual.pipeline import attach_visuals, build_visual_artifacts

FIXTURE = Path(__file__).parent / "fixtures" / "go" / "routes.go"


def _routes_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_middleware_order_from_fixture():
    text = _routes_text()
    mw = go.extract_middleware(text)
    names = [m.name for m in mw]
    assert "cors.New" in names or any("cors" in n.lower() for n in names)
    assert any(m.is_auth for m in mw)
    # Registration order: cors on app before AuthMiddleware on api
    cors = next(m for m in mw if m.is_cors)
    auth = next(m for m in mw if m.is_auth)
    assert cors.order < auth.order


def test_go_route_tree_prefixes():
    text = _routes_text()
    routes = go.extract_routes(text, uses_fiber=True)
    paths = {r.path for r in routes}
    assert "/api/v1/users" in paths
    assert "/health" in paths
    users = next(r for r in routes if r.path == "/api/v1/users" and r.method == "GET")
    assert users.protected is True  # ancestor api.Use(AuthMiddleware)
    health = next(r for r in routes if r.path == "/health")
    assert health.protected is False


def test_go_middleware_order_in_lifecycle():
    text = _routes_text()
    routes = go.extract_routes(text, uses_fiber=True)
    middleware = go.extract_middleware(text)
    groups, roots = go.extract_route_groups(text)
    routes_out = []
    for r in routes:
        chain = go.middleware_chain_for_router(r.router_var, groups, middleware, roots)
        routes_out.append({
            "path": r.path,
            "method": r.method,
            "handler": r.handler,
            "assumed": r.assumed,
            "protected": r.protected,
            "routerVar": r.router_var,
            "line": r.line,
            "middleware": [
                {
                    "name": m.name,
                    "order": m.order,
                    "line": m.line,
                    "isAuth": m.is_auth,
                    "isCors": m.is_cors,
                    "assumed": m.assumed,
                    "routerVar": m.router_var,
                }
                for m in chain
            ],
        })
    record = {
        "filePath": "cmd/api/routes.go",
        "routes": routes_out,
        "middleware": [
            {
                "name": m.name,
                "order": m.order,
                "line": m.line,
                "isAuth": m.is_auth,
                "isCors": m.is_cors,
                "assumed": m.assumed,
                "routerVar": m.router_var,
                "source": m.source,
            }
            for m in middleware
        ],
        "routeGroups": [
            {"var": v, "parent": p, "prefix": pref}
            for v, (p, pref) in groups.items()
        ],
        "importantFunctions": [
            {"name": "listUsers", "lineRange": [30, 40], "calls": [], "sideEffects": ["database_call"]},
        ],
        "fidelity": "regex",
        "usesFiber": True,
    }
    flows = build_go_fiber_lifecycle_flows(record)
    assert flows
    get_users = next(f for f in flows if f["title"] == "GET /api/v1/users")
    actions = [s["action"] for s in get_users["steps"]]
    assert actions[0] == "middleware"
    assert "handler" in actions
    assert "response" in actions
    # Middleware steps preserve registration order (cors then auth on chain).
    mw_labels = [s["label"] for s in get_users["steps"] if s["action"] == "middleware"]
    assert len(mw_labels) >= 1
    assert any("Auth" in lab or "auth" in lab.lower() for lab in mw_labels)
    # Orders strictly increase
    orders = [s["order"] for s in get_users["steps"]]
    assert orders == sorted(orders)


def test_go_route_tree_golden_sorted_edges():
    text = _routes_text()
    routes = go.extract_routes(text, uses_fiber=True)
    middleware = go.extract_middleware(text)
    groups, roots = go.extract_route_groups(text)
    record = {
        "filePath": "cmd/api/routes.go",
        "chunkId": "routes",
        "usesFiber": True,
        "routes": [
            {
                "path": r.path,
                "method": r.method,
                "handler": r.handler,
                "assumed": r.assumed,
                "protected": r.protected,
                "routerVar": r.router_var,
                "line": r.line,
                "notes": r.note,
                "middleware": [
                    {
                        "name": m.name,
                        "order": m.order,
                        "line": m.line,
                        "isAuth": m.is_auth,
                        "isCors": m.is_cors,
                        "assumed": m.assumed,
                        "routerVar": m.router_var,
                    }
                    for m in go.middleware_chain_for_router(r.router_var, groups, middleware, roots)
                ],
            }
            for r in routes
        ],
        "middleware": [
            {
                "name": m.name,
                "order": m.order,
                "line": m.line,
                "isAuth": m.is_auth,
                "isCors": m.is_cors,
                "assumed": m.assumed,
                "routerVar": m.router_var,
                "source": m.source,
            }
            for m in middleware
        ],
        "routeGroups": [
            {"var": v, "parent": p, "prefix": pref}
            for v, (p, pref) in groups.items()
        ],
    }
    graph = build_go_fiber_route_tree(record)
    assert graph is not None
    assert graph["kind"] == "route_tree"
    edge_ids = [e["id"] for e in graph["edges"]]
    assert edge_ids == sorted(edge_ids)
    assert any(e["kind"] == "routes_to" for e in graph["edges"])
    assert any(e["kind"] == "middleware_before" for e in graph["edges"])


def test_flow_title_is_http_trigger_not_business_epic():
    flows = build_go_fiber_lifecycle_flows({
        "filePath": "routes.go",
        "routes": [{
            "method": "POST",
            "path": "/api/v1/users",
            "handler": "createUser",
            "assumed": False,
            "middleware": [],
            "routerVar": "v1",
            "line": 20,
        }],
        "importantFunctions": [],
        "fidelity": "regex",
    })
    assert flows[0]["title"] == "POST /api/v1/users"
    assert "checkout" not in flows[0]["title"].lower()
    assert "journey" not in flows[0]["title"].lower()


def test_tree_script_hedges_assumed_go():
    graph = {
        "kind": "route_tree",
        "rootId": "module:routes",
        "nodes": [
            {"id": "module:routes", "label": "routes"},
            {"id": "route:GET:/users", "label": "GET /users", "kind": "route", "meta": {"method": "GET"}},
        ],
        "edges": [
            {
                "id": "r1",
                "kind": "routes_to",
                "from": "module:routes",
                "to": "route:GET:/users",
                "assumed": True,
            }
        ],
    }
    beats = build_tree_beats(graph, "go", "partial")
    spoken = " ".join(b["spoken"] for b in beats)
    assert "It looks like" in spoken


def test_go_lifecycle_assumed_hedge():
    flow = {
        "id": "flow:x",
        "title": "GET /health",
        "steps": [
            {"order": 1, "action": "handler", "label": "healthHandler", "assumed": False},
            {"order": 2, "action": "response", "label": "response write", "assumed": True},
        ],
    }
    beats = build_lifecycle_beats(flow, "go")
    assert any("It looks like" in b["spoken"] for b in beats)


def test_teaser_copy_file_scoped_go():
    beats = script_breakdown_teaser({"filePath": "cmd/api/routes.go"})
    assert "routes.go" in beats[0]["spoken"]
    assert "checkout" not in beats[0]["spoken"].lower()
    assert "chat" not in beats[0]["spoken"].lower()


def test_full_go_record_from_fixture(tmp_path):
    root = tmp_path
    (root / "go.mod").write_text(
        (Path(__file__).parent / "fixtures" / "go" / "go.mod").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    dest = root / "cmd" / "api" / "routes.go"
    dest.parent.mkdir(parents=True)
    dest.write_text(_routes_text())

    chunk = ChunkPlan(
        chunk_id="routes",
        feature_name="API",
        stack="go",
        file_path="cmd/api/routes.go",
        total_lines=50,
        size_class="small",
    )
    record = build_backend_go_chunk_record(
        root, chunk, {"frontend": None, "backend": ["go"]},
        "github.com/example/cev-go-fixture", True,
    )
    assert record["extractorVersion"] == EXTRACTOR_VERSION == 21
    assert record["fidelity"] == "regex"
    assert record.get("middleware")
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "route_tree"
    assert is_present(record["visualAvailability"]["lifecycleFlow"])
    assert record["lifecycleFlows"]
    assert is_present(record["visualAvailability"]["interactiveBreakdown"])
    payload = package_go_fiber_interactive_breakdown(record)
    assert payload is not None
    assert "http://" not in json.dumps(payload)
    route_node = next(
        n for n in payload["visualGraph"]["nodes"]
        if n.get("kind") == "route" and (n.get("meta") or {}).get("method") == "GET"
        and "/users" in (n.get("label") or "")
    )
    detail = canvas_go_fiber_node_detail(route_node, payload["visualGraph"], payload["lifecycleFlows"])
    assert detail["filePath"]
    assert detail["middlewareCount"] >= 1

    summary = build_visual_artifacts(record, tmp_path / "visuals")
    assert summary["written"]
    assert (tmp_path / "visuals" / "go" / "routes" / "visualGraph.json").is_file()


def test_refuse_empty_go_canvas_payload():
    record = attach_visuals({
        "chunkId": "empty",
        "filePath": "empty.go",
        "stack": "go",
        "routes": [],
        "middleware": [],
        "projectType": {"frontend": None, "backend": ["go"]},
        "confidence": 0.3,
    }, stack="go")
    assert package_go_fiber_interactive_breakdown(record) is None
    assert record["visualAvailability"]["componentTree"] == "unavailable"


def test_non_go_backend_still_unavailable():
    record = attach_visuals({
        "chunkId": "spring1",
        "filePath": "App.java",
        "stack": "spring_boot",
        "notes": "Extraction for stack 'spring_boot' is not yet implemented in Phase 3.",
        "confidence": 0,
        "projectType": {"frontend": None, "backend": ["spring_boot"]},
    }, stack="spring_boot")
    assert record["visualAvailability"]["componentTree"] == "unavailable"
    assert record.get("visualGraph") is None


def test_top_n_cap_go():
    flows = [{"id": f"f{i}", "title": f"GET /{i}", "steps": []} for i in range(5)]
    assert len(select_top_lifecycle_flows(flows, n=2)) == 2


def test_react_slice_still_works_alongside_go():
    """Do not invent Go graphs for React or vice versa."""
    react = attach_visuals({
        "chunkId": "X",
        "filePath": "X.tsx",
        "stack": "react",
        "jsxMounts": [],
        "projectType": {"frontend": "react", "backend": []},
        "confidence": 0.4,
    }, stack="react")
    assert react["visualGraph"] is None
    go_rec = attach_visuals({
        "chunkId": "Y",
        "filePath": "y.go",
        "stack": "go",
        "routes": [],
        "projectType": {"frontend": None, "backend": ["go"]},
        "confidence": 0.4,
    }, stack="go")
    assert go_rec["visualGraph"] is None
