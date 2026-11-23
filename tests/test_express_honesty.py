"""Express extractor honesty enrichments — accuracy over coverage; never invent."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.express import build_express_chunk_record, extract_express
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


def test_extractor_version_is_21():
    assert EXTRACTOR_VERSION == 25


def test_nested_literal_mounts_compose():
    src = """
const express = require('express');
const app = express();
const api = express.Router();
const v1 = express.Router();
app.use('/api', api);
api.use('/v1', v1);
v1.get('/users', listUsers);
"""
    routes, _mw, mounts = extract_express(src)
    assert mounts.get("api") == "/api"
    assert mounts.get("v1") == "/api/v1"
    assert any(r.method == "GET" and r.path == "/api/v1/users" and not r.assumed for r in routes)


def test_non_literal_mount_prefix_is_assumed_not_invented():
    src = """
const express = require('express');
const app = express();
const r = express.Router();
app.use(BASE, r);
r.get('/users', listUsers);
"""
    routes, _mw, mounts = extract_express(src)
    # No fabricated prefix from BASE
    assert all(not (r.path.startswith("/BASE") or "BASE" in r.path) for r in routes)
    users = [r for r in routes if r.handler == "listUsers"]
    assert len(users) == 1
    assert users[0].path == "/users"
    assert users[0].assumed is True
    assert users[0].path_resolved is False
    assert users[0].note and "BASE" in users[0].note


def test_path_array_emits_one_route_per_literal():
    src = """
const express = require('express');
const app = express();
app.get(['/a/:id', '/b/:id'], handler);
app.get(['/ok', dynamicPath], other);
"""
    routes, _mw, _ = extract_express(src)
    paths = {(r.method, r.path, r.handler) for r in routes}
    assert ("GET", "/a/:id", "handler") in paths
    assert ("GET", "/b/:id", "handler") in paths
    # Non-literal array element skipped — no invented path
    assert ("GET", "/ok", "other") in paths
    assert not any(r.path == "dynamicPath" or "dynamic" in r.path.lower() for r in routes if r.handler == "other")


def test_regex_path_assumed_not_synthesized_url():
    src = """
const express = require('express');
const app = express();
app.get(/.*fly$/, flyHandler);
"""
    routes, _mw, _ = extract_express(src)
    assert len(routes) == 1
    r = routes[0]
    assert r.method == "GET"
    assert r.path == "<regex:.*fly$>"
    assert r.assumed is True
    assert r.handler == "flyHandler"
    assert r.note and "RegExp" in r.note


def test_non_literal_path_skipped():
    src = """
const express = require('express');
const app = express();
app.post(config.path, handler);
app.get('/real', ok);
"""
    routes, _mw, _ = extract_express(src)
    assert {(r.method, r.path) for r in routes} == {("GET", "/real")}


def test_path_scoped_middleware_not_treated_as_mount():
    src = """
const express = require('express');
const app = express();
const router = express.Router();
app.use('/api', router);
app.use('/admin', requireAuth);
router.get('/x', handler);
"""
    routes, mw, mounts = extract_express(src)
    assert "requireAuth" not in mounts
    assert mounts.get("router") == "/api"
    assert any(m.name == "requireAuth" and m.mount_path == "/admin" for m in mw)
    assert any(r.path == "/api/x" and not r.assumed for r in routes)


def test_per_route_middleware_args_and_head_options():
    src = """
const express = require('express');
const app = express();
app.get('/x', requireAuth, validate, handler);
app.head('/x', handler);
app.options('/x', handler);
app.get('/y', [gate, log], finalHandler);
"""
    routes, _mw, _ = extract_express(src)
    by = {(r.method, r.path): r for r in routes}
    assert by[("GET", "/x")].handler == "handler"
    assert by[("GET", "/x")].route_middleware == ["requireAuth", "validate"]
    assert by[("HEAD", "/x")].handler == "handler"
    assert by[("OPTIONS", "/x")].handler == "handler"
    assert by[("GET", "/y")].handler == "finalHandler"
    assert by[("GET", "/y")].route_middleware == ["gate", "log"]


def test_express_app_binding_not_only_app_name():
    src = """
const express = require('express');
const server = express();
server.get('/health', ok);
"""
    routes, _mw, _ = extract_express(src)
    assert any(r.path == "/health" and r.router_var == "server" and not r.assumed for r in routes)


def test_unmounted_router_routes_are_assumed():
    src = """
const express = require('express');
const router = express.Router();
router.get('/about', about);
module.exports = router;
"""
    routes, _mw, _ = extract_express(src)
    assert len(routes) == 1
    assert routes[0].path == "/about"
    assert routes[0].assumed is True


def test_route_chain_still_works_with_nested_prefix():
    src = """
const express = require('express');
const app = express();
const r = express.Router();
app.use('/api', r);
r.route('/book').get(list).post(create);
"""
    routes, _mw, mounts = extract_express(src)
    assert mounts.get("r") == "/api"
    paths = {(r.method, r.path, r.assumed) for r in routes}
    assert ("GET", "/api/book", False) in paths
    assert ("POST", "/api/book", False) in paths


def test_builder_feeds_route_tree_with_route_arg_middleware(tmp_path: Path):
    (tmp_path / "routes.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "const router = express.Router();\n"
        "app.use('/api', router);\n"
        "router.get('/users', requireAuth, listUsers);\n"
        "function requireAuth(req, res, next) { next(); }\n"
        "function listUsers(req, res) { res.json([]); }\n"
    )
    rec = build_express_chunk_record(
        tmp_path,
        ChunkPlan("routes", "API", "express", "routes.js", 20, "small"),
        {"frontend": None, "backend": ["express"]},
    )
    assert rec["extractorVersion"] == 25
    assert is_present(rec["visualAvailability"]["componentTree"])
    users = next(r for r in rec["routes"] if r["path"] == "/api/users")
    assert users["assumed"] is False
    assert users["handler"] == "listUsers"
    assert users["protected"] is True
    assert any(m["name"] == "requireAuth" for m in users["middleware"])
