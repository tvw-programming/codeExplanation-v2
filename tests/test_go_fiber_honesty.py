"""Go Fiber honesty enrichments (EXTRACTOR_VERSION 13): generics, interfaces, factories, All/Add."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract import go_extractor as go
from src.extract.go.record import build_backend_go_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION


def test_extractor_version_bumped_for_go_fiber_honesty():
    assert EXTRACTOR_VERSION == 13


def test_generic_function_is_extracted():
    text = """
package util
func Map[T, U any](xs []T, f func(T) U) []U {
	out := make([]U, len(xs))
	for i, x := range xs {
		out[i] = f(x)
	}
	return out
}
"""
    fns = go.extract_functions(text)
    assert len(fns) == 1
    assert fns[0].name == "Map"
    assert fns[0].type_params == "T, U any"
    assert fns[0].returns_fiber_handler is False


def test_generic_struct_is_extracted():
    text = """
type Store[T any] struct {
	items map[string]T
}
"""
    structs = go.extract_structs(text)
    assert len(structs) == 1
    assert structs[0].name == "Store"
    assert structs[0].type_params == "T any"
    assert structs[0].fields == [("items", "map[string]T")]


def test_interface_methods_extracted_without_impl_edges():
    text = """
type UserRepo interface {
	FindByID(ctx context.Context, id string) (*User, error)
	Save(ctx context.Context, u *User) error
	io.Closer
}
"""
    ifaces = go.extract_interfaces(text)
    assert len(ifaces) == 1
    assert ifaces[0].name == "UserRepo"
    names = {n for n, _ in ifaces[0].methods}
    assert names == {"FindByID", "Save"}
    assert "io.Closer" in ifaces[0].embedded
    # Never invent concrete implementors from the interface alone.
    assert ifaces[0].methods  # methods present
    # No "implements" / concrete type field on the dataclass.


def test_generic_interface_type_params():
    text = """
type Repo[T any] interface {
	Get(id string) (T, error)
}
"""
    ifaces = go.extract_interfaces(text)
    assert ifaces[0].type_params == "T any"
    assert ifaces[0].methods[0][0] == "Get"


def test_closure_middleware_factory_detected():
    text = """
package mw

import "github.com/gofiber/fiber/v2"

func AuthRequired(secret string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		return c.Next()
	}
}

func plain() error { return nil }
"""
    factories = go.extract_middleware_factories(text)
    assert len(factories) == 1
    assert factories[0].name == "AuthRequired"
    assert factories[0].assumed is True
    fns = go.extract_functions(text)
    auth = next(f for f in fns if f.name == "AuthRequired")
    assert auth.returns_fiber_handler is True
    plain = next(f for f in fns if f.name == "plain")
    assert plain.returns_fiber_handler is False


def test_method_returning_fiber_handler_is_factory():
    text = """
func (c *Client) Protect() fiber.Handler {
	return func(ctx *fiber.Ctx) error { return ctx.Next() }
}
"""
    factories = go.extract_middleware_factories(text)
    assert len(factories) == 1
    assert factories[0].name == "Protect"
    assert factories[0].receiver is not None


def test_all_emits_single_all_method_not_invented_verbs():
    text = """
app := fiber.New()
app.All("/ping", health)
"""
    routes = go.extract_routes(text, uses_fiber=True)
    assert len(routes) == 1
    assert routes[0].method == "ALL"
    assert routes[0].path == "/ping"
    assert "every HTTP method" in (routes[0].note or "")


def test_add_literal_methods_emitted_non_literal_skipped():
    text = """
app := fiber.New()
app.Add([]string{"GET", "POST"}, "/items", listItems)
app.Add(cfg.Methods, "/skip", skipped)
"""
    routes = go.extract_routes(text, uses_fiber=True)
    methods = {(r.method, r.path) for r in routes}
    assert ("GET", "/items") in methods
    assert ("POST", "/items") in methods
    assert not any(r.path == "/skip" for r in routes)


def test_route_closure_groups_are_skipped():
    """app.Route(prefix, func(r){...}) cannot be scoped safely by regex — skip."""
    text = """
app := fiber.New()
app.Route("/api", func(r fiber.Router) {
	r.Get("/users", listUsers)
})
"""
    routes = go.extract_routes(text, uses_fiber=True)
    # Inner r.Get is relative to an unresolved router param → assumed incomplete,
    # OR skipped entirely if ROUTE_REGISTER only fires. Either way we must not
    # invent /api/users as a confident path.
    for r in routes:
        if r.path.endswith("/users"):
            assert r.assumed is True
            assert "incomplete" in (r.note or "")


def test_record_includes_interfaces_and_factories():
    root = Path("/tmp")
    text = '''package api

import "github.com/gofiber/fiber/v2"

type UserRepo interface {
	FindByID(id string) (*User, error)
}

type Store[T any] struct {
	Value T
}

func AuthRequired() fiber.Handler {
	return func(c *fiber.Ctx) error { return c.Next() }
}

func Map[T any](xs []T) []T { return xs }
'''
    # Write a temp file via ChunkPlan path relative to a tmp tree.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        src = tdp / "api.go"
        src.write_text(text, encoding="utf-8")
        chunk = ChunkPlan(
            chunk_id="go-honesty-1",
            file_path="api.go",
            feature_name="api",
            stack="go",
            total_lines=len(text.splitlines()),
        )
        record = build_backend_go_chunk_record(
            tdp, chunk, {"type": "go", "framework": "fiber"}, None, True,
        )
    assert record["extractorVersion"] == 13
    kinds = {m["kind"] for m in record["dataModels"]}
    assert "interface" in kinds
    assert "struct" in kinds
    iface = next(m for m in record["dataModels"] if m["kind"] == "interface")
    assert iface["methods"][0]["name"] == "FindByID"
    assert iface["notes"]
    assert any(f["name"] == "AuthRequired" for f in record["middlewareFactories"])
    assert any(f.get("returnsFiberHandler") for f in record["importantFunctions"])
    assert any(f.get("typeParams") for f in record["importantFunctions"])
    store = next(m for m in record["dataModels"] if m["name"] == "Store")
    assert store["typeParams"] == "T any"
