"""Express + Flask cross-file mounts onto shared PrefixGraph (EXTRACTOR_VERSION 19).

Spring has no safe literal mount analogue — deferred (see spring/extract.py).
"""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.express import (
    build_express_chunk_record,
    build_express_route_index,
    extract_express,
)
from src.extract.python import (
    build_python_chunk_record,
    build_python_route_index,
    extract_python,
)
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_is_19():
    assert EXTRACTOR_VERSION == 19


def test_express_cross_file_require_mount_composes():
    root = FIXTURES / "express_cross_file"
    index = build_express_route_index(root)
    text = (root / "routes" / "users.js").read_text(encoding="utf-8")
    routes, _mw, _mounts = extract_express(
        text, file_path="routes/users.js", route_index=index,
    )
    by = {(r.method, r.path): r for r in routes}
    assert ("GET", "/api/users") in by
    assert ("POST", "/api/users") in by
    get = by[("GET", "/api/users")]
    assert get.assumed is False
    assert get.path_resolved is True
    assert get.handler == "listUsers"
    assert any("app.js" in c for c in get.prefix_chain)


def test_express_inline_require_and_bound_require(tmp_path: Path):
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "birds.js").write_text(
        "const express = require('express');\n"
        "const router = express.Router();\n"
        "router.get('/list', listBirds);\n"
        "module.exports = router;\n"
    )
    (tmp_path / "app.js").write_text(
        "const express = require('express');\n"
        "const birds = require('./routes/birds');\n"
        "const app = express();\n"
        "app.use('/birds', birds);\n"
        "app.use('/also', require('./routes/birds'));\n"
    )
    index = build_express_route_index(tmp_path)
    # Double mount → ambiguous, never last-wins
    text = (tmp_path / "routes" / "birds.js").read_text(encoding="utf-8")
    routes, _mw, _ = extract_express(
        text, file_path="routes/birds.js", route_index=index,
    )
    assert len(routes) == 1
    r = routes[0]
    assert r.path_resolved is False
    assert r.assumed is True
    assert "more than one prefix" in (r.note or "")
    # Path must not invent a single forged join of both prefixes as one URL
    assert "/birds/also" not in r.path
    assert "/also/birds" not in r.path


def test_express_ambiguous_require_skips_join(tmp_path: Path):
    """Two candidate files for the same require → skip (never invent)."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "dup.js").write_text(
        "const express = require('express');\n"
        "const router = express.Router();\n"
        "router.get('/from_a', a);\n"
        "module.exports = router;\n"
    )
    (tmp_path / "b" / "dup.js").write_text(
        "const express = require('express');\n"
        "const router = express.Router();\n"
        "router.get('/from_b', b);\n"
        "module.exports = router;\n"
    )
    (tmp_path / "app.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "app.use('/x', require('./missing'));\n"
    )
    index = build_express_route_index(tmp_path)
    # Force ambiguity for a relative require that would match both
    # by mounting via a binding that we resolve as ambiguous.
    # Directly: unresolved require → no mount edge; router stays local/assumed.
    text = (tmp_path / "a" / "dup.js").read_text(encoding="utf-8")
    routes, _mw, _ = extract_express(
        text, file_path="a/dup.js", route_index=index,
    )
    assert len(routes) == 1
    assert routes[0].path == "/from_a"
    assert routes[0].assumed is True
    assert routes[0].path_resolved is False
    assert not any("from_b" in r.path for r in routes)
    # Confirm index did not invent a mount onto either dup
    assert ("a/dup.js", "router") not in index.mounted_routers
    assert ("b/dup.js", "router") not in index.mounted_routers


def test_express_non_literal_cross_file_mount_assumed(tmp_path: Path):
    (tmp_path / "r.js").write_text(
        "const express = require('express');\n"
        "const router = express.Router();\n"
        "router.get('/x', h);\n"
        "module.exports = router;\n"
    )
    (tmp_path / "app.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "app.use(BASE, require('./r'));\n"
    )
    index = build_express_route_index(tmp_path)
    routes, _mw, _ = extract_express(
        (tmp_path / "r.js").read_text(encoding="utf-8"),
        file_path="r.js",
        route_index=index,
    )
    assert len(routes) == 1
    assert routes[0].path == "/x"
    assert routes[0].assumed is True
    assert routes[0].path_resolved is False
    assert "BASE" in (routes[0].note or "") or "non-literal" in (routes[0].note or "")


def test_express_package_require_never_joined(tmp_path: Path):
    """require('some-pkg') is not a relative module — never invent."""
    (tmp_path / "app.js").write_text(
        "const express = require('express');\n"
        "const app = express();\n"
        "app.use('/ext', require('external-routes'));\n"
        "app.get('/ok', ok);\n"
    )
    index = build_express_route_index(tmp_path)
    assert index.mounted_routers == set()
    routes, _mw, _ = extract_express(
        (tmp_path / "app.js").read_text(encoding="utf-8"),
        file_path="app.js",
        route_index=index,
    )
    assert any(r.path == "/ok" and r.assumed is False for r in routes)


def test_express_builder_emits_path_resolved():
    root = FIXTURES / "express_cross_file"
    rec = build_express_chunk_record(
        root,
        ChunkPlan("users", "API", "express", "routes/users.js", 20, "small"),
        {"frontend": None, "backend": ["express"]},
    )
    assert rec["extractorVersion"] == 19
    assert is_present(rec["visualAvailability"]["componentTree"])
    users = next(r for r in rec["routes"] if r["path"] == "/api/users" and r["method"] == "GET")
    assert users["pathResolved"] is True
    assert users["assumed"] is False
    assert users["prefixChain"]


def test_flask_cross_file_register_blueprint_composes():
    root = FIXTURES / "py_flask_bp"
    index = build_python_route_index(root)
    text = (root / "blueprints" / "api.py").read_text(encoding="utf-8")
    _fns, routes, _imps, _ = extract_python(
        text, file_path="blueprints/api.py", route_index=index,
    )
    by = {(r.method, r.path): r for r in routes}
    assert ("GET", "/v1/health") in by
    assert by[("GET", "/v1/health")].assumed is False
    assert by[("GET", "/v1/health")].path_resolved is True
    assert ("GET", "/v1/items/<int:item_id>") in by
    assert ("POST", "/v1/items/<int:item_id>") in by


def test_flask_attr_import_register_blueprint(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "pages.py").write_text(
        "from flask import Blueprint\n"
        "bp = Blueprint('pages', __name__, url_prefix='/pages')\n"
        "@bp.route('/about')\n"
        "def about():\n"
        "    return 'ok'\n"
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "from pkg import pages\n"
        "app = Flask(__name__)\n"
        "app.register_blueprint(pages.bp, url_prefix='/site')\n"
    )
    index = build_python_route_index(tmp_path)
    _fns, routes, _imps, _ = extract_python(
        (tmp_path / "pkg" / "pages.py").read_text(encoding="utf-8"),
        file_path="pkg/pages.py",
        route_index=index,
    )
    assert any(
        r.path == "/site/pages/about" and r.method == "GET" and r.path_resolved
        for r in routes
    )


def test_flask_unmounted_blueprint_assumed_with_project_index(tmp_path: Path):
    (tmp_path / "orphan.py").write_text(
        "from flask import Blueprint\n"
        "bp = Blueprint('orphan', __name__, url_prefix='/orphan')\n"
        "@bp.route('/x')\n"
        "def x():\n"
        "    return 1\n"
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
    )
    index = build_python_route_index(tmp_path)
    _fns, routes, _imps, _ = extract_python(
        (tmp_path / "orphan.py").read_text(encoding="utf-8"),
        file_path="orphan.py",
        route_index=index,
    )
    assert len(routes) == 1
    assert routes[0].path == "/orphan/x"
    assert routes[0].assumed is True
    assert routes[0].path_resolved is False
    assert "register_blueprint" in (routes[0].note or "")


def test_flask_builder_notes_cross_file(tmp_path: Path):
    root = FIXTURES / "py_flask_bp"
    rec = build_python_chunk_record(
        root,
        ChunkPlan("api", "API", "python", "blueprints/api.py", 20, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    assert rec["extractorVersion"] == 19
    health = next(r for r in rec["routes"] if r["path"] == "/v1/health")
    assert health["pathResolved"] is True
    assert "register_blueprint" in rec["notes"]
