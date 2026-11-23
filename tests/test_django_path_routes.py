"""Django urlpatterns path() extraction — honesty over coverage."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.python import build_python_chunk_record, extract_python
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


def test_extractor_version_is_21():
    assert EXTRACTOR_VERSION == 22


def test_django_path_literal_order_and_unknown_method():
    src = """
from django.urls import path
from . import views

urlpatterns = [
    path('articles/<int:year>/', views.year_archive, name='year'),
    path('articles/<int:year>/<int:month>/', views.month_archive),
    path('', views.index),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert [r.path for r in routes] == [
        "/articles/<int:year>/",
        "/articles/<int:year>/<int:month>/",
        "/",
    ]
    assert all(r.method == "UNKNOWN" for r in routes)
    assert all(not r.assumed for r in routes)
    assert routes[0].handler == "views.year_archive"
    assert routes[1].handler == "views.month_archive"
    assert routes[2].handler == "views.index"


def test_django_include_module_is_assumed_not_joined():
    src = """
from django.urls import path, include
from . import views

urlpatterns = [
    path('blog/', include('blog.urls')),
    path('home/', views.home),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    by_path = {r.path: r for r in routes}
    assert "/blog/" in by_path
    assert by_path["/blog/"].assumed is True
    assert by_path["/blog/"].handler == ""
    assert by_path["/blog/"].method == "UNKNOWN"
    # No invented children under /blog/
    assert not any(r.path.startswith("/blog/") and r.path != "/blog/" for r in routes)
    assert by_path["/home/"].assumed is False
    assert by_path["/home/"].handler == "views.home"


def test_django_inline_include_composes_in_file():
    src = """
from django.urls import path, include
from . import views

urlpatterns = [
    path('auth/', include([
        path('login/', views.login),
        path('register/', views.register),
    ])),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    paths = {(r.path, r.handler, r.assumed) for r in routes}
    assert ("/auth/login/", "views.login", False) in paths
    assert ("/auth/register/", "views.register", False) in paths
    # Mount alone is not duplicated when children were expanded in-file.
    assert "/auth/" not in {r.path for r in routes}


def test_django_non_literal_path_skipped():
    src = """
from django.urls import path
from . import views
PREFIX = 'x/'

urlpatterns = [
    path(PREFIX, views.dyn),
    path('ok/', views.ok),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert [r.path for r in routes] == ["/ok/"]
    assert routes[0].handler == "views.ok"


def test_django_dynamic_urlpatterns_emits_nothing():
    src = """
from django.urls import path
from . import views

urlpatterns = build_patterns()
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert routes == []


def test_django_re_path_and_augassign():
    src = """
from django.urls import path, re_path
from . import views

urlpatterns = [
    re_path(r'^articles/(?P<year>[0-9]{4})/$', views.year_archive),
]
urlpatterns += [
    path('extra/', views.extra),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    # re_path regex kept verbatim (no forged leading '/').
    assert any(
        r.path == "^articles/(?P<year>[0-9]{4})/$" and r.method == "UNKNOWN"
        for r in routes
    )
    assert any(r.path == "/extra/" and r.handler == "views.extra" for r in routes)


def test_django_as_view_handler_unparsed():
    src = """
from django.urls import path
from .views import ArticleList

urlpatterns = [
    path('list/', ArticleList.as_view()),
]
"""
    _fns, routes, _imps, _ = extract_python(src)
    assert len(routes) == 1
    assert routes[0].path == "/list/"
    assert routes[0].handler == "ArticleList.as_view()"
    assert routes[0].method == "UNKNOWN"


def test_django_builder_feeds_route_tree(tmp_path: Path):
    (tmp_path / "urls.py").write_text(
        "from django.urls import path, include\n"
        "from . import views\n"
        "urlpatterns = [\n"
        "    path('articles/<int:year>/', views.year_archive),\n"
        "    path('blog/', include('blog.urls')),\n"
        "]\n"
    )
    record = build_python_chunk_record(
        tmp_path,
        ChunkPlan("urls", "API", "python", "urls.py", 20, "small"),
        {"frontend": None, "backend": ["python"]},
    )
    assert record["extractorVersion"] == 22
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "route_tree"
    paths = {r["path"] for r in record["routes"]}
    assert "/articles/<int:year>/" in paths
    assert "/blog/" in paths
    blog = next(r for r in record["routes"] if r["path"] == "/blog/")
    assert blog["method"] == "UNKNOWN"
    assert blog["assumed"] is True
    assert "Django" in record["notes"] or "django" in record["notes"].lower()
