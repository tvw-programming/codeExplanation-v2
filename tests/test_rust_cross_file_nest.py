"""Rust cross-file .nest onto PrefixGraph (EXTRACTOR_VERSION 21).

Same honesty bar as Express #23: unique literal module resolution only;
unresolved/ambiguous → no invented children; pathResolved False ⇒ assumed True.
"""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.rust import (
    build_rust_chunk_record,
    build_rust_route_index,
    extract_rust,
)
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_21():
    assert EXTRACTOR_VERSION == 21


def test_cross_file_nest_mod_fn_composes():
    root = FIXTURES / "rust_cross_file"
    index = build_rust_route_index(root)
    text = (root / "api.rs").read_text(encoding="utf-8")
    facts = extract_rust(text, file_path="api.rs", route_index=index)
    by = {(r["method"], r["path"]): r for r in facts.routes}
    assert ("GET", "/api/items") in by
    assert ("POST", "/api/items") in by
    get = by[("GET", "/api/items")]
    assert get["assumed"] is False
    assert get["pathResolved"] is True
    assert get["handler"] == "list_items"
    assert any("main.rs" in c for c in get["prefixChain"])
    # Never invent unprefixed child as the joined fact when nest composed.
    assert ("GET", "/items") not in by


def test_main_does_not_invent_child_routes():
    root = FIXTURES / "rust_cross_file"
    index = build_rust_route_index(root)
    facts = extract_rust(
        (root / "main.rs").read_text(encoding="utf-8"),
        file_path="main.rs",
        route_index=index,
    )
    paths = {(r["method"], r["path"]) for r in facts.routes}
    assert ("GET", "/health") in paths
    assert ("GET", "/api/items") not in paths
    assert ("GET", "/items") not in paths


def test_unresolved_path_nest_invents_no_children(tmp_path: Path):
    (tmp_path / "main.rs").write_text(
        'let app = Router::new().nest("/api", other::router());\n',
        encoding="utf-8",
    )
    index = build_rust_route_index(tmp_path)
    facts = extract_rust(
        (tmp_path / "main.rs").read_text(encoding="utf-8"),
        file_path="main.rs",
        route_index=index,
    )
    assert facts.routes == []
    assert index.mounted_routers == set()


def test_external_crate_path_never_joined(tmp_path: Path):
    """other_crate::router() is not a local mod — never invent."""
    (tmp_path / "main.rs").write_text(
        "mod api;\n"
        "let app = Router::new()\n"
        '    .nest("/ext", foreign_crate::routes())\n'
        '    .route("/ok", get(ok));\n',
        encoding="utf-8",
    )
    (tmp_path / "api.rs").write_text(
        "pub fn router() -> Router { Router::new().route(\"/x\", get(h)) }\n",
        encoding="utf-8",
    )
    index = build_rust_route_index(tmp_path)
    assert ("api.rs", "router") not in index.mounted_routers
    facts = extract_rust(
        (tmp_path / "main.rs").read_text(encoding="utf-8"),
        file_path="main.rs",
        route_index=index,
    )
    assert any(r["path"] == "/ok" and r["assumed"] is False for r in facts.routes)
    assert not any("foreign" in r["path"] for r in facts.routes)


def test_double_mount_ambiguous_never_last_wins(tmp_path: Path):
    (tmp_path / "api.rs").write_text(
        "pub fn router() -> Router {\n"
        '    Router::new().route("/items", get(list_items))\n'
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "main.rs").write_text(
        "mod api;\n"
        "let app = Router::new()\n"
        '    .nest("/api", api::router())\n'
        '    .nest("/also", api::router());\n',
        encoding="utf-8",
    )
    index = build_rust_route_index(tmp_path)
    facts = extract_rust(
        (tmp_path / "api.rs").read_text(encoding="utf-8"),
        file_path="api.rs",
        route_index=index,
    )
    assert len(facts.routes) == 1
    r = facts.routes[0]
    assert r["pathResolved"] is False
    assert r["assumed"] is True
    assert "more than one prefix" in (r.get("note") or "")
    assert "/api/also" not in r["path"]
    assert "/also/api" not in r["path"]


def test_unmounted_router_fn_assumed(tmp_path: Path):
    (tmp_path / "lonely.rs").write_text(
        "pub fn router() -> Router {\n"
        '    Router::new().route("/x", get(h))\n'
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "main.rs").write_text(
        "fn main() {}\n",
        encoding="utf-8",
    )
    index = build_rust_route_index(tmp_path)
    facts = extract_rust(
        (tmp_path / "lonely.rs").read_text(encoding="utf-8"),
        file_path="lonely.rs",
        route_index=index,
    )
    assert len(facts.routes) == 1
    assert facts.routes[0]["path"] == "/x"
    assert facts.routes[0]["assumed"] is True
    assert facts.routes[0]["pathResolved"] is False


def test_crate_path_nest_composes(tmp_path: Path):
    (tmp_path / "main.rs").write_text(
        "mod api;\n"
        "let app = Router::new()\n"
        '    .nest("/v1", crate::api::router());\n',
        encoding="utf-8",
    )
    (tmp_path / "api.rs").write_text(
        "pub fn router() -> Router {\n"
        '    Router::new().route("/ping", get(ping))\n'
        "}\n",
        encoding="utf-8",
    )
    index = build_rust_route_index(tmp_path)
    facts = extract_rust(
        (tmp_path / "api.rs").read_text(encoding="utf-8"),
        file_path="api.rs",
        route_index=index,
    )
    assert any(
        r["path"] == "/v1/ping" and r["assumed"] is False and r["pathResolved"] is True
        for r in facts.routes
    )


def test_builder_emits_path_resolved():
    root = FIXTURES / "rust_cross_file"
    rec = build_rust_chunk_record(
        root,
        ChunkPlan("api", "API", "rust", "api.rs", 20, "small"),
        {"frontend": None, "backend": ["rust"]},
    )
    assert rec["extractorVersion"] == 21
    assert is_present(rec["visualAvailability"]["componentTree"])
    items = next(r for r in rec["routes"] if r["path"] == "/api/items" and r["method"] == "GET")
    assert items["pathResolved"] is True
    assert items["assumed"] is False
    assert items["prefixChain"]
