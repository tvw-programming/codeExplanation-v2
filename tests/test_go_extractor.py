from src.extract import go_extractor as go


def test_extract_module_path():
    assert go.extract_module_path("module github.com/example/alumni/api\n\ngo 1.22\n") == "github.com/example/alumni/api"


def test_extract_imports_classifies_stdlib_external_internal():
    text = """
import (
	"context"
	"github.com/gofiber/fiber/v2"
	"github.com/example/alumni/api/internal/handler"
)
"""
    imports = go.extract_imports(text, module_path="github.com/example/alumni/api")
    by_path = {i.path: i for i in imports}
    assert by_path["context"].is_stdlib is True
    assert by_path["github.com/gofiber/fiber/v2"].is_stdlib is False
    assert by_path["github.com/gofiber/fiber/v2"].is_internal is False
    assert by_path["github.com/example/alumni/api/internal/handler"].is_internal is True


def test_extract_structs_with_tagged_fields():
    text = """
type Alumni struct {
	ID       int64  `json:"id"`
	FullName string `json:"fullName"`
}
"""
    structs = go.extract_structs(text)
    assert len(structs) == 1
    assert structs[0].name == "Alumni"
    assert structs[0].fields == [("ID", "int64"), ("FullName", "string")]


def test_extract_functions_with_receiver():
    text = """
func (r *AlumniRepository) List(ctx context.Context) (Page, error) {
	return Page{}, nil
}

func NewAlumniRepository(pool *pgxpool.Pool) *AlumniRepository {
	return &AlumniRepository{pool: pool}
}
"""
    functions = go.extract_functions(text)
    names = {f.name for f in functions}
    assert names == {"List", "NewAlumniRepository"}
    listed = next(f for f in functions if f.name == "List")
    assert listed.receiver is not None and "AlumniRepository" in listed.receiver


def test_extract_side_effects_matches_pgx_calls():
    text = """
rows, err := r.pool.Query(ctx, query)
tag, err := r.pool.Exec(ctx, query)
"""
    effects = go.extract_side_effects(text)
    kinds = {k for k, _ in effects}
    assert kinds == {"database_call"}
    assert len(effects) == 2


def test_extract_routes_resolves_group_prefix():
    text = """
v1 := app.Group("/api/v1")
v1.Get("/alumni", alumni.List)
v1.Put("/alumni/:id", alumni.Update)
"""
    routes = go.extract_routes(text, uses_fiber=True)
    assert len(routes) == 2
    get_route = next(r for r in routes if r.method == "GET")
    assert get_route.path == "/api/v1/alumni"
    assert get_route.static_or_dynamic == "static"
    put_route = next(r for r in routes if r.method == "PUT")
    assert put_route.path == "/api/v1/alumni/:id"
    assert put_route.static_or_dynamic == "dynamic"


def test_extract_routes_does_not_false_positive_on_auth_disabled_comment():
    # Regression test for the real bug found against the alumni repo: a
    # comment/variable merely containing the word "auth" (explaining that
    # auth is OFF) must not mark the route protected.
    text = """
// AUTH_MODE below is the switch for disabling authentication.
authMode := env("AUTH_MODE", "")
app.Use(recover.New())
app.Use(cors.New(cors.Config{}))
app.Get("/health", healthHandler)
"""
    routes = go.extract_routes(text, uses_fiber=True)
    assert len(routes) == 1
    assert routes[0].protected is False


def test_extract_routes_detects_real_auth_middleware():
    text = """
v1 := app.Group("/api/v1")
v1.Use(firebaseauth.Middleware())
v1.Get("/alumni", alumni.List)
"""
    routes = go.extract_routes(text, uses_fiber=True)
    assert routes[0].protected is True
    assert routes[0].assumed is True  # always assumed, even when it looks protected


def test_nested_group_prefixes_compose_into_the_full_path():
    """api := app.Group("/api"); v1 := api.Group("/v1"); v1.Get("/users")
    is /api/v1/users. Recording only each group's own segment made this
    /v1/users — a confidently narrated URL that does not exist in the
    running app."""
    source = """package main
func main() {
	app := fiber.New()
	api := app.Group("/api")
	v1 := api.Group("/v1")
	v1.Get("/users", listUsers)
}"""
    routes = go.extract_routes(source, True)
    assert len(routes) == 1
    assert routes[0].path == "/api/v1/users"
    assert "incomplete" not in (routes[0].note or "")


def test_a_chain_rooted_at_a_differently_named_app_still_resolves():
    source = """package main
func main() {
	srv := fiber.New()
	g := srv.Group("/x")
	g.Get("/y", h)
}"""
    routes = go.extract_routes(source, True)
    assert routes[0].path == "/x/y"


def test_a_router_passed_in_from_another_file_is_flagged_not_guessed():
    """The prefix is decided at the call site in another file, so the
    path here is genuinely incomplete and must say so."""
    source = """package routes
func Register(r fiber.Router) {
	r.Get("/users", listUsers)
}"""
    routes = go.extract_routes(source, True)
    assert routes[0].assumed is True
    assert "incomplete" in (routes[0].note or "")


def test_a_route_on_the_app_itself_has_no_prefix():
    source = """package main
func main() {
	app := fiber.New()
	app.Get("/health", health)
}"""
    routes = go.extract_routes(source, True)
    assert routes[0].path == "/health"
    assert "incomplete" not in (routes[0].note or "")
