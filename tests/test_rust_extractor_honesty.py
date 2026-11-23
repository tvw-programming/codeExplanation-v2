"""Rust extractor honesty enrichments — never invent edges."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.rust import build_rust_chunk_record, extract_rust
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


def test_extractor_version_is_18():
    assert EXTRACTOR_VERSION == 20


def test_qualified_axum_routing_helper_and_real_handler():
    src = """
use axum::Router;
let app = Router::new().route("/users", axum::routing::get(list_users));
async fn list_users() {}
"""
    facts = extract_rust(src)
    assert len(facts.routes) == 1
    r = facts.routes[0]
    assert r["method"] == "GET"
    assert r["path"] == "/users"
    assert r["handler"] == "list_users"
    assert r["assumed"] is False


def test_chained_method_router_emits_each_method():
    src = 'Router::new().route("/x", get(a).post(b).put(c));'
    facts = extract_rust(src)
    methods = {(r["method"], r["handler"]) for r in facts.routes}
    assert methods == {("GET", "a"), ("POST", "b"), ("PUT", "c")}
    assert all(r["path"] == "/x" and r["assumed"] is False for r in facts.routes)


def test_nest_let_bound_composes_in_file():
    src = """
let api = Router::new()
    .route("/items", get(list_items))
    .route("/items", post(create_item));
let app = Router::new()
    .nest("/api", api)
    .route("/health", get(health));
"""
    facts = extract_rust(src)
    by = {(r["method"], r["path"], r["handler"]) for r in facts.routes}
    assert ("GET", "/api/items", "list_items") in by
    assert ("POST", "/api/items", "create_item") in by
    assert ("GET", "/health", "health") in by
    assert all(r["assumed"] is False for r in facts.routes)
    # Never leave the unprefixed child as a fact when nest composed.
    assert ("GET", "/items", "list_items") not in by


def test_nest_inline_composes_and_nested_nests():
    src = """
let app = Router::new()
    .nest("/api", Router::new().route("/items", get(list_items)))
    .route("/health", get(health));
"""
    facts = extract_rust(src)
    paths = {(r["method"], r["path"]) for r in facts.routes}
    assert ("GET", "/api/items") in paths
    assert ("GET", "/health") in paths
    assert ("GET", "/items") not in paths

    deep = 'Router::new().nest("/api", Router::new().nest("/v1", Router::new().route("/x", get(h))));'
    deep_facts = extract_rust(deep)
    assert [(r["method"], r["path"], r["handler"]) for r in deep_facts.routes] == [
        ("GET", "/api/v1/x", "h")
    ]


def test_unresolved_nest_invents_no_children():
    src = 'let app = Router::new().nest("/api", other::router());'
    facts = extract_rust(src)
    assert facts.routes == []


def test_express_style_get_path_is_not_axum():
    src = """
something.get("/nope");
app.get("/also-nope", handler);
"""
    facts = extract_rust(src)
    assert facts.routes == []


def test_attr_macros_handler_from_following_fn():
    src = """
#[post("/items")]
async fn create_item() {}

#[route(GET, "/hello")]
fn hello() {}

#[route("/index", method = "GET")]
async fn index() {}
"""
    facts = extract_rust(src)
    by = {(r["method"], r["path"], r["handler"], r["framework"]) for r in facts.routes}
    assert ("POST", "/items", "create_item", "attr_macro") in by
    assert ("GET", "/hello", "hello", "rocket") in by
    assert ("GET", "/index", "index", "actix") in by
    assert all(r["assumed"] is False for r in facts.routes)


def test_fixture_feeds_route_tree(tmp_path: Path):
    src = (Path(__file__).resolve().parent / "fixtures" / "rust" / "main.rs").read_text()
    (tmp_path / "main.rs").write_text(src)
    record = build_rust_chunk_record(
        tmp_path,
        ChunkPlan("main", "api", "rust", "main.rs", 20, "small"),
        {"frontend": None, "backend": ["rust"]},
    )
    assert record["extractorVersion"] == 20
    assert any(
        r["path"] == "/users" and r["handler"] == "list_users" and not r["assumed"]
        for r in record["routes"]
    )
    assert is_present(record["visualAvailability"]["componentTree"])
    assert record["visualGraph"]["kind"] == "route_tree"
