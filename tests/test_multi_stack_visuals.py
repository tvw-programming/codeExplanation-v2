"""Multi-stack visual ship — honesty gates + extractors for remaining stacks."""

from __future__ import annotations

import json
from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.detect.project_type import detect_project_type
from src.extract.stack_records import (
    build_angular_chunk_record,
    build_express_chunk_record,
    build_javascript_chunk_record,
    build_python_chunk_record,
    build_qwik_chunk_record,
    build_rust_chunk_record,
    build_solid_chunk_record,
    build_spring_chunk_record,
    build_vue_chunk_record,
)
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present
from src.visual.pipeline import attach_visuals

FIX = Path(__file__).parent / "fixtures"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_extractor_version_is_9():
    assert EXTRACTOR_VERSION == 11


def test_express_detect_not_react_or_angular(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"express": "^4.19.0"}}))
    result = detect_project_type(tmp_path)
    assert result.frontend_stack is None
    assert "express" in result.backend_stacks
    assert result.frontend_stack != "react_or_angular"


def test_detect_vue_solid_qwik_javascript_rust(tmp_path):
    _write(tmp_path / "fe-vue" / "package.json", json.dumps({"dependencies": {"vue": "^3.0.0"}}))
    assert detect_project_type(tmp_path / "fe-vue").frontend_stack == "vue"

    _write(tmp_path / "fe-solid" / "package.json", json.dumps({"dependencies": {"solid-js": "^1.0.0"}}))
    assert detect_project_type(tmp_path / "fe-solid").frontend_stack == "solid"

    _write(tmp_path / "fe-qwik" / "package.json", json.dumps({"dependencies": {"@builder.io/qwik": "^1.0.0"}}))
    assert detect_project_type(tmp_path / "fe-qwik").frontend_stack == "qwik"

    _write(tmp_path / "fe-js" / "package.json", json.dumps({"dependencies": {"lodash": "^4.0.0"}}))
    assert detect_project_type(tmp_path / "fe-js").frontend_stack == "javascript"

    _write(tmp_path / "crate" / "Cargo.toml", "[package]\nname='demo'\nversion='0.1.0'\n")
    assert "rust" in detect_project_type(tmp_path / "crate").backend_stacks


def test_python_ast_route_graph(tmp_path):
    dest = tmp_path / "app.py"
    dest.write_text((FIX / "python" / "app.py").read_text())
    chunk = ChunkPlan("app", "API", "python", "app.py", 30, "small")
    record = build_python_chunk_record(tmp_path, chunk, {"frontend": None, "backend": ["python"]})
    assert record["fidelity"] == "syntax"
    assert record["extractorVersion"] == 11
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] in ("route_tree", "module_graph")
    assert any(r["path"] == "/users" for r in record["routes"])
    assert is_present(record["visualAvailability"]["lifecycleFlow"])


def test_express_route_tree(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"express": "^4.0.0"}}))
    dest = tmp_path / "routes.js"
    dest.write_text((FIX / "express" / "routes.js").read_text())
    chunk = ChunkPlan("routes", "API", "express", "routes.js", 40, "small")
    record = build_express_chunk_record(tmp_path, chunk, {"frontend": None, "backend": ["express"]})
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "route_tree"
    paths = {r["path"] for r in record["routes"]}
    assert any("/users" in p for p in paths)
    assert record["lifecycleFlows"]
    titles = [f["title"] for f in record["lifecycleFlows"]]
    assert all("checkout" not in t.lower() for t in titles)


def test_spring_di_not_import_as_inject(tmp_path):
    dest = tmp_path / "UserController.java"
    dest.write_text((FIX / "spring" / "UserController.java").read_text())
    chunk = ChunkPlan("UserController", "Users", "spring_boot", "UserController.java", 40, "small")
    record = build_spring_chunk_record(tmp_path, chunk, {"frontend": None, "backend": ["spring_boot"]})
    assert record["springTypes"]
    graph = record["visualGraph"]
    assert graph is not None
    assert graph["kind"] == "di_graph"
    assert all(e["kind"] != "imports" for e in graph["edges"] if e["kind"] == "injects" or True)
    inject_edges = [e for e in graph["edges"] if e["kind"] == "injects"]
    assert inject_edges
    # Inject target is UserService type, not an import path
    assert any("UserService" in (e["to"] or "") for e in inject_edges)


def test_angular_dedicated_not_empty_valid(tmp_path):
    dest = tmp_path / "user-card.component.ts"
    dest.write_text((FIX / "angular" / "user-card.component.ts").read_text())
    chunk = ChunkPlan("UserCard", "User", "angular", "user-card.component.ts", 40, "small")
    record = build_angular_chunk_record(tmp_path, chunk, {"frontend": "angular", "backend": []})
    assert record.get("angularComponent")
    assert record["inputs"]
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "component_tree"
    assert any(e["kind"] == "input_bind" for e in record["visualGraph"]["edges"])


def test_angular_empty_still_unavailable():
    record = attach_visuals({
        "chunkId": "empty",
        "filePath": "empty.component.ts",
        "stack": "angular",
        "projectType": {"frontend": "angular", "backend": []},
        "confidence": 0.3,
    }, stack="angular")
    assert record["visualAvailability"]["componentTree"] == "unavailable"
    assert record.get("visualGraph") is None


def test_vue_solid_qwik_js_rust_graphs(tmp_path):
    # Vue
    p = tmp_path / "UserCard.vue"
    p.write_text((FIX / "vue" / "UserCard.vue").read_text())
    vue = build_vue_chunk_record(tmp_path, ChunkPlan("UserCard", "UI", "vue", "UserCard.vue", 20, "small"),
                                 {"frontend": "vue", "backend": []})
    assert is_present(vue["visualAvailability"]["componentTree"])
    assert vue["visualGraph"]

    # Solid
    p = tmp_path / "Counter.tsx"
    p.write_text((FIX / "solid" / "Counter.tsx").read_text())
    sol = build_solid_chunk_record(tmp_path, ChunkPlan("Counter", "UI", "solid", "Counter.tsx", 20, "small"),
                                   {"frontend": "solid", "backend": []})
    assert sol["signals"] or sol.get("jsxMounts")
    assert is_present(sol["visualAvailability"]["componentTree"]) or sol["visualGraph"] is not None or sol["signals"]

    # Qwik
    p = tmp_path / "Greeter.tsx"
    p.write_text((FIX / "qwik" / "Greeter.tsx").read_text())
    qw = build_qwik_chunk_record(tmp_path, ChunkPlan("Greeter", "UI", "qwik", "Greeter.tsx", 20, "small"),
                                 {"frontend": "qwik", "backend": []})
    assert qw.get("qwikBoundaries")
    assert is_present(qw["visualAvailability"]["componentTree"])

    # JS
    p = tmp_path / "main.js"
    p.write_text((FIX / "javascript" / "main.js").read_text())
    js = build_javascript_chunk_record(tmp_path, ChunkPlan("main", "app", "javascript", "main.js", 20, "small"),
                                       {"frontend": "javascript", "backend": []})
    assert is_present(js["visualAvailability"]["componentTree"])
    assert js["visualGraph"]["kind"] == "module_graph"

    # Rust
    p = tmp_path / "main.rs"
    p.write_text((FIX / "rust" / "main.rs").read_text())
    rs = build_rust_chunk_record(tmp_path, ChunkPlan("main", "api", "rust", "main.rs", 20, "small"),
                                 {"frontend": None, "backend": ["rust"]})
    assert rs["visualGraph"]
    assert rs["visualGraph"]["kind"] in ("route_tree", "crate_graph")


def test_never_invent_graph_for_empty_python(tmp_path):
    _write(tmp_path / "empty.py", "# just a comment\n")
    record = build_python_chunk_record(
        tmp_path, ChunkPlan("empty", "x", "python", "empty.py", 2, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    # No imports/routes/functions with edges → unavailable or no graph
    if record.get("visualGraph") is None:
        assert record["visualAvailability"]["componentTree"] == "unavailable"
    else:
        assert record["visualGraph"]["edges"]


def test_flow_titles_are_code_triggers_across_stacks(tmp_path):
    dest = tmp_path / "app.py"
    dest.write_text((FIX / "python" / "app.py").read_text())
    record = build_python_chunk_record(
        tmp_path, ChunkPlan("app", "API", "python", "app.py", 30, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    for flow in record["lifecycleFlows"]:
        assert flow["title"].startswith(("GET", "POST", "PUT", "DELETE", "PATCH"))
        assert "journey" not in flow["title"].lower()
