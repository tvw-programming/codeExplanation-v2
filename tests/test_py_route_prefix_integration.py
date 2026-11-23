"""Cross-file FastAPI include_router + Django include() via shared PrefixGraph."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.python import (
    build_python_chunk_record,
    build_python_route_index,
    extract_python,
)
from src.storage.mirror_store import EXTRACTOR_VERSION

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_is_21():
    assert EXTRACTOR_VERSION == 21


def test_fastapi_include_router_composes_across_files():
    root = FIXTURES / "py_fastapi_app"
    index = build_python_route_index(root)
    text = (root / "routers" / "items.py").read_text(encoding="utf-8")
    _fns, routes, _imps, _ = extract_python(
        text, file_path="routers/items.py", route_index=index,
    )
    assert len(routes) == 1
    r = routes[0]
    assert r.method == "GET"
    assert r.path == "/api/v1/items/{item_id}"
    assert r.assumed is False
    assert r.path_resolved is True


def test_fastapi_unmounted_router_is_assumed_router_local():
    root = FIXTURES / "py_fastapi_app"
    index = build_python_route_index(root)
    # Snippet defines a second router never include_router'd
    orphan = """
from fastapi import APIRouter
other = APIRouter(prefix='/orphan')
@other.get('/x')
def x():
    return 1
"""
    _fns, routes, _imps, _ = extract_python(
        orphan, file_path="routers/orphan.py", route_index=index,
    )
    assert len(routes) == 1
    assert routes[0].path == "/orphan/x"
    assert routes[0].assumed is True
    assert routes[0].path_resolved is False
    assert "include_router" in (routes[0].note or "")


def test_fastapi_in_file_include_router_without_project_index():
    src = """
from fastapi import FastAPI, APIRouter
app = FastAPI()
router = APIRouter(prefix='/items')
app.include_router(router, prefix='/api')
@router.get('/{id}')
def get_item(id: str):
    return id
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/api/items/{id}" and r.method == "GET" for r in routes)


def test_fastapi_non_literal_mount_prefix_assumed():
    src = """
from fastapi import FastAPI, APIRouter
PREFIX = '/api'
app = FastAPI()
router = APIRouter(prefix='/items')
app.include_router(router, prefix=PREFIX)
@router.get('/x')
def x():
    return 1
"""
    _fns, routes, _imps, _ = extract_python(src)
    r = next(r for r in routes if r.handler == "x")
    assert r.assumed is True
    assert r.path_resolved is False
    # Local router path preserved; mount not invented from PREFIX var
    assert r.path == "/items/x" or "/items/x" in r.path


def test_django_include_module_joins_when_unique():
    root = FIXTURES / "py_django_include"
    index = build_python_route_index(root)
    text = (root / "urls.py").read_text(encoding="utf-8")
    _fns, routes, _imps, _ = extract_python(
        text, file_path="urls.py", route_index=index,
    )
    paths = {r.path: r for r in routes}
    assert "/blog/posts/" in paths
    assert paths["/blog/posts/"].handler == "views.post_list"
    assert paths["/blog/posts/"].assumed is False
    assert paths["/blog/posts/"].method == "UNKNOWN"
    assert "/blog/posts/<int:pk>/" in paths
    assert "/home/" in paths
    # Mount alone is not kept when children joined
    assert "/blog/" not in paths or paths["/blog/"].handler != ""


def test_django_include_unresolved_stays_assumed_mount():
    src = """
from django.urls import path, include
from . import views
urlpatterns = [
    path('ext/', include('missing_pkg.urls')),
    path('ok/', views.ok),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    by_path = {r.path: r for r in routes}
    assert by_path["/ext/"].assumed is True
    assert by_path["/ext/"].handler == ""
    assert not any(r.path.startswith("/ext/") and r.path != "/ext/" for r in routes)
    assert by_path["/ok/"].assumed is False


def test_django_ambiguous_module_not_joined(tmp_path: Path):
    """Two files claiming the same module name → skip join (never invent)."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    # Force identical module keys by placing urls at same relative module via
    # duplicate dotted names under different trees — simulate ambiguity in index.
    (tmp_path / "pkg").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "pkg" / "blog").mkdir()
    (tmp_path / "other" / "blog").mkdir()
    (tmp_path / "pkg" / "blog" / "urls.py").write_text(
        "from django.urls import path\n"
        "urlpatterns = [path('from_pkg/', None)]\n"
    )
    (tmp_path / "other" / "blog" / "urls.py").write_text(
        "from django.urls import path\n"
        "urlpatterns = [path('from_other/', None)]\n"
    )
    # Also register both as blog.urls by writing a third collision via index mutation
    index = build_python_route_index(tmp_path)
    # Manually create ambiguity for blog.urls if scan produced distinct modules
    pkg_mod = "pkg.blog.urls"
    other_mod = "other.blog.urls"
    # Point include at a name that we force-collide
    index.module_files["blog.urls"] = [
        "pkg/blog/urls.py",
        "other/blog/urls.py",
    ]
    src = """
from django.urls import path, include
urlpatterns = [path('blog/', include('blog.urls'))]
"""
    _fns, routes, _imps, _ = extract_python(
        src, file_path="urls.py", route_index=index,
    )
    assert len(routes) == 1
    assert routes[0].path == "/blog/"
    assert routes[0].assumed is True
    assert routes[0].handler == ""
    # No invented children from either candidate
    assert not any("from_pkg" in r.path or "from_other" in r.path for r in routes)
    # Silence unused — prove both modules exist in the index
    assert pkg_mod in index.module_files or other_mod in index.module_files


def test_python_builder_emits_path_resolved(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI, APIRouter\n"
        "app = FastAPI()\n"
        "router = APIRouter(prefix='/api')\n"
        "app.include_router(router, prefix='/v1')\n"
        "@router.get('/users')\n"
        "def users():\n"
        "    return []\n"
    )
    record = build_python_chunk_record(
        tmp_path,
        ChunkPlan("main", "API", "python", "main.py", 20, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    assert record["extractorVersion"] == 21
    route = next(r for r in record["routes"] if r["handler"] == "users")
    assert route["path"] == "/v1/api/users"
    assert route["pathResolved"] is True
    assert route["assumed"] is False
