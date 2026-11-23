"""Hardening slice: honesty fixes + per-stack package layout."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.angular import extract_angular_component, build_angular_chunk_record
from src.extract.express import extract_express, build_express_chunk_record
from src.extract.python import extract_python, build_python_chunk_record
from src.extract.rust import extract_rust
from src.extract.spring import extract_spring, build_spring_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


def test_extractor_version_is_9():
    assert EXTRACTOR_VERSION == 9


def test_python_apirouter_prefix_composes():
    src = """
from fastapi import APIRouter
router = APIRouter(prefix='/api')
@router.get('/users')
def users():
    return []
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/api/users" and r.method == "GET" and not r.assumed for r in routes)


def test_python_flask_methods_not_default_get():
    src = """
@app.route('/x', methods=['POST', 'PUT'])
def x():
    pass
"""
    _fns, routes, _imps, _ = extract_python(src)
    methods = {r.method for r in routes if r.path == "/x"}
    assert methods == {"POST", "PUT"}


def test_angular_signal_input_output():
    src = """
@Component({selector:'app-x', template:`<button (click)="save()">x</button>`})
export class X {
  user = input<string>();
  saved = output<void>();
  @Input() legacy!: string;
  save() {}
}
"""
    comp = extract_angular_component(src)
    assert comp is not None
    assert "user" in comp.inputs
    assert "legacy" in comp.inputs
    assert "saved" in comp.outputs


def test_spring_request_mapping_method_and_lombok_inject():
    src = """
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class C {
    private final UserService userService;

    @GetMapping("/{id:[0-9]+}")
    public User get(@PathVariable String id) { return userService.find(id); }

    @RequestMapping(value="/search", method=RequestMethod.POST)
    public void search() {}
}
"""
    types, routes = extract_spring(src)
    assert types
    assert any(i["type"] == "UserService" and i["via"] == "lombok" for i in types[0].injectees)
    assert any(r.method == "POST" and "/search" in r.path for r in routes)
    assert any(r.method == "GET" and "{id:[0-9]+}" in r.path for r in routes)


def test_express_route_chain():
    src = """
const express = require('express');
const app = express();
const r = express.Router();
app.use('/api', r);
r.route('/book').get(list).post(create);
app.get('/health', ok);
"""
    routes, _mw, mounts = extract_express(src)
    assert mounts.get("r") == "/api"
    paths = {(r.method, r.path) for r in routes}
    assert ("GET", "/api/book") in paths
    assert ("POST", "/api/book") in paths
    assert ("GET", "/health") in paths


def test_rust_method_from_route_helper():
    src = """
Router::new().route("/users", get(list_users)).route("/x", post(create));
#[post("/items")]
async fn items() {}
"""
    facts = extract_rust(src)
    methods = {(r["method"], r["path"]) for r in facts.routes}
    assert ("GET", "/users") in methods
    assert ("POST", "/x") in methods
    assert ("POST", "/items") in methods
    # No duplicate GET for attr that is POST
    assert ("GET", "/items") not in methods


def test_hardened_builders_feed_visual_graphs(tmp_path: Path):
    # Python
    (tmp_path / "app.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api')\n"
        "@router.get('/users')\n"
        "def list_users():\n"
        "    return []\n"
    )
    py = build_python_chunk_record(
        tmp_path, ChunkPlan("app", "API", "python", "app.py", 20, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    assert py["extractorVersion"] == 9
    assert is_present(py["visualAvailability"]["componentTree"])
    assert any(r["path"] == "/api/users" for r in py["routes"])

    # Spring DI
    (tmp_path / "C.java").write_text(
        "@RestController\n@RequestMapping(\"/api\")\n@RequiredArgsConstructor\n"
        "public class C {\n"
        "    private final UserService userService;\n"
        "    @GetMapping\n"
        "    public String list() { return userService.list(); }\n"
        "}\n"
    )
    sp = build_spring_chunk_record(
        tmp_path, ChunkPlan("C", "API", "spring_boot", "C.java", 20, "small"),
        {"frontend": None, "backend": ["spring_boot"]},
    )
    assert sp["visualGraph"]["kind"] == "di_graph"
    assert any(e["kind"] == "injects" for e in sp["visualGraph"]["edges"])

    # Angular signals
    (tmp_path / "x.component.ts").write_text(
        "import { Component, input, output } from '@angular/core';\n"
        "@Component({ selector: 'app-x', template: `<span></span>` })\n"
        "export class X {\n"
        "  name = input<string>();\n"
        "  done = output<void>();\n"
        "}\n"
    )
    ang = build_angular_chunk_record(
        tmp_path, ChunkPlan("X", "UI", "angular", "x.component.ts", 20, "small"),
        {"frontend": "angular", "backend": []},
    )
    assert is_present(ang["visualAvailability"]["componentTree"])
    assert any(e["kind"] == "input_bind" for e in ang["visualGraph"]["edges"])
    assert any(e["kind"] == "output_bind" for e in ang["visualGraph"]["edges"])

    # Express chain
    (tmp_path / "routes.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "const router = express.Router();\n"
        "app.use('/api', router);\n"
        "router.route('/users').get(listUsers).post(createUser);\n"
        "function listUsers(req, res) { res.json([]); }\n"
        "function createUser(req, res) { res.status(201).end(); }\n"
    )
    ex = build_express_chunk_record(
        tmp_path, ChunkPlan("routes", "API", "express", "routes.js", 20, "small"),
        {"frontend": None, "backend": ["express"]},
    )
    assert ex["visualGraph"]["kind"] == "route_tree"
    assert any("/users" in r["path"] for r in ex["routes"])
