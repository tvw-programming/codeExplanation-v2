"""Python honesty enrichments beyond Django path() (EXTRACTOR_VERSION 15→17 current)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.python import build_python_chunk_record, extract_python
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


def test_extractor_version_is_17():
    assert EXTRACTOR_VERSION == 17


def test_django_require_post_same_file():
    src = """
from django.urls import path
from django.views.decorators.http import require_POST

@require_POST
def create(request):
    return None

urlpatterns = [
    path('create/', create),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert len(routes) == 1
    assert routes[0].path == "/create/"
    assert routes[0].method == "POST"
    assert routes[0].handler == "create"
    assert routes[0].assumed is False


def test_django_require_http_methods_expands():
    src = """
from django.urls import path
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET", "POST"])
def item(request):
    return None

urlpatterns = [path('item/', item)]
"""
    _fns, routes, _imps, _ = extract_python(src)
    methods = {r.method for r in routes if r.path == "/item/"}
    assert methods == {"GET", "POST"}


def test_django_api_view_methods():
    src = """
from django.urls import path
from rest_framework.decorators import api_view

@api_view(["PUT", "PATCH"])
def update(request):
    return None

urlpatterns = [path('u/', update)]
"""
    _fns, routes, _imps, _ = extract_python(src)
    methods = {r.method for r in routes if r.path == "/u/"}
    assert methods == {"PUT", "PATCH"}


def test_django_cbv_http_verbs_same_file():
    src = """
from django.urls import path
from django.views import View

class ArticleList(View):
    def get(self, request):
        return None
    def post(self, request):
        return None

urlpatterns = [path('list/', ArticleList.as_view())]
"""
    _fns, routes, _imps, _ = extract_python(src)
    methods = {r.method for r in routes if r.path == "/list/"}
    assert methods == {"GET", "POST"}
    assert all(r.handler == "ArticleList.as_view()" for r in routes)


def test_django_cross_file_handler_stays_unknown():
    """views.foo is not defined here — never invent a method."""
    src = """
from django.urls import path
from . import views

urlpatterns = [
    path('articles/', views.year_archive),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert len(routes) == 1
    assert routes[0].method == "UNKNOWN"
    assert routes[0].handler == "views.year_archive"


def test_django_cross_file_as_view_stays_unknown():
    src = """
from django.urls import path
from .views import ArticleList

urlpatterns = [path('list/', ArticleList.as_view())]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert len(routes) == 1
    assert routes[0].method == "UNKNOWN"


def test_django_require_safe():
    src = """
from django.urls import path
from django.views.decorators.http import require_safe

@require_safe
def home(request):
    return None

urlpatterns = [path('', home)]
"""
    _fns, routes, _imps, _ = extract_python(src)
    methods = {r.method for r in routes if r.path == "/"}
    assert methods == {"GET", "HEAD"}


def test_django_bare_api_view_stays_unknown():
    """@api_view() with no literal methods — do not invent GET."""
    src = """
from django.urls import path
from rest_framework.decorators import api_view

@api_view()
def weird(request):
    return None

urlpatterns = [path('w/', weird)]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert routes[0].method == "UNKNOWN"


def test_flask_blueprint_url_prefix_composes():
    src = """
from flask import Blueprint
bp = Blueprint('pages', __name__, url_prefix='/pages')
@bp.route('/about')
def about():
    return 'ok'
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/pages/about" and r.method == "GET" and not r.assumed for r in routes)


def test_fastapi_include_router_mount_composes():
    src = """
from fastapi import APIRouter, FastAPI
router = APIRouter(prefix='/users')
app = FastAPI()
app.include_router(router, prefix='/api')

@router.get('/{id}')
def get_user(id: str):
    return {}
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/api/users/{id}" and r.method == "GET" and not r.assumed for r in routes)


def test_fastapi_include_router_nonliteral_assumed():
    src = """
from fastapi import APIRouter, FastAPI
PREFIX = '/api'
router = APIRouter()
app = FastAPI()
app.include_router(router, prefix=PREFIX)

@router.get('/x')
def x():
    return {}
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/x" and r.method == "GET" and r.assumed for r in routes)


def test_flask_register_blueprint_mount_composes():
    src = """
from flask import Flask, Blueprint
bp = Blueprint('api', __name__)
app = Flask(__name__)
app.register_blueprint(bp, url_prefix='/v1')

@bp.route('/health', methods=['GET'])
def health():
    return 'ok'
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert any(r.path == "/v1/health" and r.method == "GET" and not r.assumed for r in routes)


def test_cross_module_include_router_not_joined():
    """users.router is not a local Name — do not invent a mount join."""
    src = """
from fastapi import FastAPI
from . import users
app = FastAPI()
app.include_router(users.router, prefix='/api')
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert routes == []


def test_builder_notes_and_version(tmp_path: Path):
    (tmp_path / "urls.py").write_text(
        "from django.urls import path\n"
        "from django.views.decorators.http import require_POST\n"
        "@require_POST\n"
        "def create(request):\n"
        "    return None\n"
        "urlpatterns = [path('create/', create)]\n"
    )
    record = build_python_chunk_record(
        tmp_path,
        ChunkPlan("urls", "API", "python", "urls.py", 20, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    assert record["extractorVersion"] == 17
    assert is_present(record["visualAvailability"]["componentTree"])
    create = next(r for r in record["routes"] if r["path"] == "/create/")
    assert create["method"] == "POST"
    notes = record["notes"].lower()
    assert "blueprint" in notes or "require_" in notes or "view" in notes
