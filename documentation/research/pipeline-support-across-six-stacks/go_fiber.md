# Go / Fiber Backend Analysis for Automated Code-Explanation Video Generation

> Scope note: this file covers what a static analyzer must understand about Go + Fiber to explain a file accurately, and a critical assessment of a regex-based Go extractor. Two primary sources could not be retrieved directly (`https://docs.gofiber.io/guide/routing` and `https://raw.githubusercontent.com/gofiber/docs/master/docs/core/guide/routing.md` both returned a fetch-permission error, as did `https://pypi.org/project/tree-sitter-go/`). Fiber documentation content below was obtained via the Context7 documentation index, which cites the same `docs.gofiber.io` source URLs; those source URLs are given in the citations.

## Q1. How are routes declared in Go Fiber, and how do you resolve a route's FULL path across nested groups and multiple files?

### Takeaway
Fiber route paths are composed at **runtime** by chaining `Group`/`Route`/`Use` calls on router values held in local variables, so a route's full path is a property of the *dataflow* through those variables — not of any single line of text. Resolving it correctly requires at minimum intra-package variable tracking and, in real projects, interprocedural tracking across files and packages, because the idiomatic pattern is to pass a `fiber.Router` into a registration function in another file.

### Cited Findings
- Fiber registers routes with one method per verb, all with the same shape: `func (app *App) Get(path string, handler any, handlers ...any) Router`, and likewise `Head`, `Post`, `Put`, `Delete`, `Connect`, `Options`, `Trace`, `Patch`, `Query` — [Fiber App API](https://docs.gofiber.io/api/app)
- `Add(methods []string, path string, handler any, handlers ...any) Router` registers the same handlers on several methods at once; `All(path string, ...)` registers on **every** HTTP method at the **exact** path, "unlike `Use`, which is prefix-matched" — [Fiber App API](https://docs.gofiber.io/api/app)
- Groups nest and prefixes concatenate; the official grouping example is explicit that "Routes are flattened with their group prefixes": `api := app.Group("/api", middleware)` → `v1 := api.Group("/v1", middleware)` → `v1.Get("/list", handler)` resolves to `/api/v1/list` — [Fiber grouping guide](https://docs.gofiber.io/guide/grouping)
- `Group` accepts middleware inline as additional arguments (`app.Group("/api", middleware)`), so middleware attachment and prefix declaration happen in the same call — [Fiber grouping guide](https://docs.gofiber.io/guide/grouping)
- `app.Route(prefix, func(r fiber.Router){...}, namePrefix)` is a closure-based shorthand for nested `Group` calls and also carries a **name** prefix: `app.Route("/api/v1", func(r fiber.Router) { r.Get("/users", handler).Name("users") }, "v1.")` yields path `/api/v1/users` and route name `v1.users` — [Fiber grouping guide](https://docs.gofiber.io/guide/grouping), [Fiber routing guide](https://docs.gofiber.io/guide/routing)
- `func (app *App) Use(args ...any) Router` is heavily overloaded. Documented forms: `app.Use(handler)` (matches every request, any method); `app.Use("/api", handler)` (prefix match); `app.Use([]string{"/api","/home"}, handler)` (multiple prefixes); `app.Use("/api", h1, h2)` (several handlers run in order, each must call `c.Next()`); and `app.Use("/api", api)` where `api` is a **sub-app** — [Fiber routing guide](https://docs.gofiber.io/guide/routing)
- Mounting a whole sub-application under a prefix is the v3-recommended replacement for `app.Mount()`: `api := fiber.New(); api.Get("/users", listUsers); app.Use("/api", api)` — [Fiber v3 adapter pattern blog](https://docs.gofiber.io/blog/fiber-v3-adapter-pattern)
- Fiber v3 changed the handler signature: v2 handlers are `func(c *fiber.Ctx) error`, v3 handlers are `func(c fiber.Ctx) error` (interface, not pointer-to-struct) — [Fiber What's New](https://docs.gofiber.io/whats_new)
- In v3 the handler parameter type is `any`, and Fiber "also accepts simplified function signatures that automatically handle return values" in addition to the canonical one — [Fiber App API](https://docs.gofiber.io/api/app), [Fiber route handlers](https://docs.gofiber.io/partials/routing/route-handlers)

### Inferences
- **A correct full-path resolver needs a symbol table of router values, not a regex.** The minimum viable algorithm: (1) find the app constructor (`x := fiber.New()`) and seed `prefix[x] = ""`; (2) for every assignment whose RHS is `recv.Group(lit, ...)` where `recv` is a known router, set `prefix[lhs] = prefix[recv] + lit`; (3) for every `recv.<Verb>(lit, ...)`, emit `prefix[recv] + lit`; (4) for `recv.Route(lit, func(r fiber.Router){...})`, bind the closure parameter `r` to `prefix[recv] + lit` inside the closure body; (5) for `recv.Use(lit, subApp)` where `subApp` is a known app value, re-base every route registered on `subApp` under `prefix[recv] + lit`.
- **The common real-world pattern defeats step 2 entirely.** Idiomatic Fiber projects do `routes.RegisterUserRoutes(v1)` where the callee lives in another file/package as `func RegisterUserRoutes(r fiber.Router) { r.Get("/", list); r.Get("/:id", get) }`. Inside that function the prefix is unknown; it exists only at the call site. So path resolution is **interprocedural**, and for a function called from two places a route legitimately has *two* full paths. A per-file extractor explaining `user_routes.go` in isolation can only honestly say "these routes are registered relative to whatever prefix the caller supplies."
- **Non-literal paths are unresolvable statically.** `app.Get(cfg.BasePath+"/users", h)`, `app.Get(routeUsers, h)` with a package const, or paths built in a loop over a slice of route structs are all common; the analyzer must mark these `assumed: true` rather than emit a wrong path.
- **Handler identity has two shapes with very different explainability.** A handler *reference* (`v1.Get("/users", handlers.ListUsers)`) gives a cross-file edge the analyzer can follow and is the better narrative unit; an *inline closure* (`v1.Get("/users", func(c fiber.Ctx) error { ... })`) puts the logic in the routing file itself and means the "routes" chunk and the "handlers" chunk are the same chunk. A tool must detect both and change its narrative structure accordingly.
- **Middleware ordering is semantically load-bearing and order-sensitive in source order**, because `Use` is prefix-matched and runs for every method on that prefix, and each handler must call `c.Next()`. An explanation that lists middleware without the registration order is misleading. Correctly describing "what runs before this handler" requires collecting every `Use` whose prefix is a prefix of the resolved route path, in registration order — which again requires the whole-package (often whole-program) view, not one file.
- **Version detection is mandatory before any signature matching.** A regex keyed on `*fiber.Ctx` silently finds zero handlers in a v3 codebase, and vice versa. The import path (`github.com/gofiber/fiber/v2` vs `/v3`) is the reliable discriminator and should be read from `go.mod` plus the file's import block.

### Gaps
- Could not retrieve the official routing guide page directly (fetch blocked), so the exhaustive list of path-parameter syntaxes (`:param`, `:param?`, `+`, `*`, constraints like `:id<int>`) is not cited here. These matter for explaining a route's contract and should be verified against `https://docs.gofiber.io/guide/routing` before the report asserts specifics.
- No source found quantifying how often real Fiber projects use the `RegisterXRoutes(router)` cross-file pattern vs. inline registration in `main.go`; the claim that it is "common" is my judgment from the framework's API shape, not a measured statistic.

## Q2. How does Fiber differ from net/http, Gin, Echo and Chi, and which patterns generalize?

### Takeaway
The *prefix-group + verb-method* pattern generalizes across Fiber, Gin and Echo; Chi and net/http do not fit it. Handler signatures, middleware signatures, and path-parameter syntax differ in all five, so a single regex set cannot claim "Go support" — each framework needs its own adapter, and the net/http 1.22+ pattern syntax is a sixth case.

### Cited Findings
- Handler signatures diverge: Gin `func(c *gin.Context)` (no error return); Echo `func(c echo.Context) error`; Chi `func(w http.ResponseWriter, r *http.Request)` — [Leapcell: Routing and Middleware in Gin, Echo and Chi](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi)
- Fiber is a third shape again: `func(c *fiber.Ctx) error` in v2, `func(c fiber.Ctx) error` in v3 — [Fiber What's New](https://docs.gofiber.io/whats_new)
- Group syntax: Gin and Echo both return a group object (`admin := r.Group("/admin"); admin.Use(mw); admin.GET("/dashboard", h)`), while Chi uses a closure sub-router (`r.Route("/admin", func(r chi.Router) { r.Use(mw); r.Get("/dashboard", h) })`), described as "routers within routers" — [Leapcell](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi)
- Verb-method casing differs: Gin and Echo use `GET`/`POST` (all caps); Chi uses `Get`/`Post` — [Leapcell](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi). Fiber also uses `Get`/`Post` — [Fiber App API](https://docs.gofiber.io/api/app)
- Middleware signatures diverge structurally: Gin returns a `gin.HandlerFunc` that calls `c.Next()`; Echo returns a `MiddlewareFunc` of shape `func(next echo.HandlerFunc) echo.HandlerFunc`; Chi middleware is plain `func(http.Handler) http.Handler` calling `next.ServeHTTP` — [Leapcell](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi)
- Path parameter syntax diverges: Gin `:id` and `*filepath`, read with `c.Param("id")`; Echo `:id` and `*`, read with `c.Param("*")`; Chi `{id}` and `*`, read with `chi.URLParam(r, "id")` — [Leapcell](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi)
- Chi "uses plain net/http types throughout, so its middleware composes with any standard http.Handler" — [Leapcell](https://leapcell.io/blog/understanding-routing-and-middleware-in-gin-echo-and-chi)

### Inferences
- **What generalizes:** a rule of the form `<routerVar>.<Verb>(<pathLiteral>, <handler...>)` plus `<newVar> := <routerVar>.Group(<pathLiteral>, ...)` covers Fiber, Gin and Echo if you parameterize the verb casing and allow both `*X.Context` and `X.Context`. The prefix-accumulation algorithm from Q1 is identical for all three.
- **What does not generalize:** Chi's `r.Route(prefix, func(r chi.Router){...})` rebinds the *same identifier* `r` to a new sub-router inside the closure — so a naive `prefix[r]` table is corrupted unless the resolver is scope-aware (shadowing). Fiber's `app.Route` has the same hazard. This is exactly the class of bug a regex extractor cannot even represent, because regex has no notion of lexical scope.
- **net/http is a fourth pattern.** Routes are `mux.HandleFunc(pattern, handler)` with no verb method, and since Go 1.22 the pattern string itself encodes method and wildcards (`"POST /items/{id}"`), so the verb lives *inside the string literal*. Middleware is manual handler wrapping (`mux = Logging(Auth(mux))`), i.e. nested call expressions with no registration call at all. A tool that looks for `.Use(` finds nothing. (Mechanism stated from the standard library's documented behavior; I did not fetch a citation for the 1.22 pattern syntax in this pass — treat as needing verification.)
- **Honest capability statement for the product:** "Go support" should be scoped per framework and per major version. A tool that handles Fiber v2 only, and silently degrades on Fiber v3, Gin, Echo, Chi and net/http, will produce videos that confidently describe a routing table that is empty or wrong. Detecting the framework from `go.mod` and *refusing* to narrate routes for an unsupported framework is strictly better output than guessing.

### Gaps
- The Leapcell article is a secondary source (a blog). Its code examples are consistent with my knowledge of all three frameworks and with each framework's own docs, but for a published report the signatures should ideally be re-cited to `gin-gonic.com/docs`, `echo.labstack.com/docs` and `go-chi.io/#/`.
- I did not find a primary-source citation in this pass for Go 1.22's `net/http` method-in-pattern routing; flagged above.

## Q3. Which Go language constructs break a naive regex extractor?

### Takeaway
Almost every nontrivial Go declaration form breaks a line-anchored regex, and the two most damaging failures are (a) treating methods-with-receivers as free functions (or missing them entirely), which destroys the type→behavior mapping, and (b) brace counting, which is wrong in the presence of braces inside raw strings, interpreted strings, rune literals and comments — all of which are common in exactly the files a backend tool cares about.

### Cited Findings
- `go/doc` models receivers as first-class: `Func` carries `Recv` ("receiver type, possibly with type parameters"), `Orig` (original receiver) and `Level` (embedding depth, 0 if not embedded) — i.e. the standard library treats "which type does this method belong to, and was it promoted through embedding?" as essential metadata, not an afterthought — [go/doc package docs](https://pkg.go.dev/go/doc)
- `go/doc` `Mode` flags include `AllMethods`, documented as "show all embedded methods" — confirming that embedded-method promotion changes a type's apparent method set — [go/doc](https://pkg.go.dev/go/doc)
- `go/doc.Type.Funcs` is specifically "functions returning this type", distinct from `Methods` — a distinction a regex extractor has no way to compute, since it requires reading return types — [go/doc](https://pkg.go.dev/go/doc)
- GORM's `embedded` tag flattens a nested struct's fields into the parent: `Author Author \`gorm:"embedded"\`` makes `Blog` behave as if it declared `Name` and `Email` directly — so even *field* sets are not literal in the source text — [GORM models](https://gorm.io/docs/models.html)

### Inferences (concrete syntax that breaks regex / brace matching)
These are my analysis of the Go grammar, not quoted from a source. Grouped by failure mode.

**1. Declaration-shape failures (the regex matches the wrong thing or nothing):**
- Methods with receivers: `func (c *Client) Protect() fiber.Handler {`. A pattern like `func\s+(\w+)\s*\(` captures nothing useful here; a sloppier pattern captures `c` as the function name. The real name is `Protect` and the owner is `*Client`. Getting this wrong means every method in the codebase is attributed to no type.
- Generics (Go 1.18+): `func Map[T, U any](xs []T, f func(T) U) []U`. The `[` immediately after the name breaks `func\s+(\w+)\s*\(`. Constraint syntax makes it worse: `func Sum[T int|float64](...)`, `func New[T any, K comparable]() *Store[T, K]`, and generic *types*: `type Store[T any] struct {`. Generic methods on generic types: `func (s *Store[T]) Get(k string) (T, bool)` — the receiver now contains brackets.
- Multi-line signatures:
  ```go
  func CreateUser(
      ctx context.Context,
      in CreateUserInput,
  ) (*User, error) {
  ```
  A single-line regex sees only `func CreateUser(` and loses the entire parameter list and both return types. Very common in Fiber service layers.
- Multiple and named returns: `func Get() (u *User, err error)`, `func Parse() (int, string, error)`. Named returns matter for explanation because they interact with bare `return` and with `defer` that mutates the result.
- Function types as parameters/returns: `func Protect(next fiber.Handler) fiber.Handler`, `func Logger(cfg Config) func(c fiber.Ctx) error`. The nested `func(...)` inside the signature means a regex scanning for `func` finds three "functions" on one line.
- Closures returned from functions — the dominant Go middleware idiom:
  ```go
  func AuthRequired(secret string) fiber.Handler {
      return func(c fiber.Ctx) error { ... }
  }
  ```
  Two `func` tokens, one declaration. If the extractor counts functions, it over-reports; if it assigns the inner closure a name, it invents one.
- Interface declarations: `type UserRepo interface { FindByID(ctx context.Context, id string) (*User, error) }`. The methods inside have no `func` keyword at all, so a `func`-anchored extractor reports an interface as having zero behavior — catastrophic for explaining a repository/service boundary, which is the single most important architectural fact in a layered Fiber app.
- Struct embedding: `type Admin struct { User; Role string }` and `type Service struct { *BaseService }`. The embedded field has no field name, and it silently adds the embedded type's whole method set to `Service`. An extractor that lists only literally-declared methods understates the type.
- `init()`: lowercase, takes no arguments, may appear multiple times *in the same file*, and is called automatically. A "functions" list that shows three identically-named `init` entries with no explanation is confusing; a leading-capital exportedness rule marks it unexported, which is true but beside the point.
- Grouped declarations: `var ( a = 1; b = 2 )`, `const ( A Status = iota; B; C )`, `type ( X struct{...}; Y struct{...} )`. One `type`/`var`/`const` keyword, N declarations. `iota` constant blocks define enums whose values are implicit — a regex sees `B` with no value and cannot say it equals 1.
- One-line and empty bodies: `func (e NotFound) Error() string { return "not found" }` — open and close brace on the same line as the signature, so a "find the matching brace by scanning following lines" routine computes a zero- or negative-length range.
- Anonymous structs and struct literals in signatures/returns: `return struct{ OK bool }{true}, nil`.

**2. Brace / range-matching failures (the extracted line range is wrong, so the video shows the wrong code):**
- Braces inside interpreted string literals: `c.JSON(fiber.Map{"msg": "}"})`, `fmt.Printf("{%s}", v)`, and the very common `c.SendString("{\"error\": \"x\"}")`.
- Braces inside **raw string literals** (backticks), which also span lines and may contain `//`:
  ```go
  const schema = `
  CREATE TABLE users ( id text ); -- } // not a comment
  `
  ```
  A naive scanner both miscounts braces and mistakes `//` inside the raw string for a comment.
- Rune literals: `if ch == '}' {` and `'{'`.
- Braces inside comments: `// returns fiber.Map{...}` and block comments `/* { */`.
- Struct tags are raw-string literals containing quotes, colons and sometimes braces/semicolons: `` `json:"id" gorm:"primaryKey;column:id"` ``. A regex that splits fields on `"` is immediately wrong.
- `//go:embed`, `//go:generate`, `//nolint` directive comments sit exactly where a doc comment would, so a "comment directly above the declaration is the doc comment" rule will narrate a build directive as the function's purpose.
- `defer func() { ... }()` and `go func() { ... }()` — immediately-invoked closures nested inside a function body; they add brace depth and, if the extractor emits "functions found", add phantom entries.
- Goroutines and channels (`go worker(ch)`, `<-ch`, `select { case ... }`) — `select` and `switch` bodies with `case` clauses contain braces and colons; `switch` with no braces around case bodies means case bodies are not brace-delimited, so a "block = braces" model cannot delimit them.
- Semicolon-free, significant-newline grammar: Go inserts semicolons automatically, which is why `{` must be on the same line as the signature — but that also means a signature cannot be reflowed arbitrarily, and the closing `)` of a multi-line signature sits on its own line followed by return types and `{`. Any regex must be multiline-aware with `(?s)`-style handling to catch it.

**3. Exportedness: the leading-capital rule is correct but only in a narrow sense.**
- It is a correct *syntactic* rule only for identifiers declared at package scope, plus struct field names and method names. Any identifier declared inside a function body is invisible outside that function regardless of case, so `LocalThing := 1` inside a handler is not "exported".
- The rule is Unicode uppercase, not ASCII `[A-Z]` — `Ünicode` is exported, so an `^[A-Z]` regex under-reports in non-English codebases.
- Exported ≠ public API: anything under an `internal/` directory can only be imported within its parent subtree, enforced by the compiler — [golang-standards/project-layout](https://github.com/golang-standards/project-layout). So `internal/service.UserService` is "exported" and simultaneously not part of the module's public surface. A tool narrating "this is a public API" from capitalization alone will be wrong for most of a well-structured Fiber service.

### Gaps
- I did not find (and did not look for) published measurements of how often each of these constructs appears in Fiber codebases, so the ranking of "most damaging" is reasoned, not measured.

## Q4. Go doc comments: what does `go/doc` actually do, and what conventions should the tool follow?

### Takeaway
Go's doc-comment convention is machine-checkable and `go/doc` already implements the association rules, including several non-obvious exclusions that a naive "take the comment block above the declaration" heuristic gets wrong.

### Cited Findings
- A doc comment is the comment group immediately preceding a declaration; the package comment goes before the `package` clause, and a comment directly above `Greet` becomes `Greet`'s `Doc` — [go/doc](https://pkg.go.dev/go/doc)
- `go/doc` explicitly **refuses** comments beginning with an illegal prefix — `copyright`, `all rights`, `author` (`IllegalPrefixes`) — "to avoid mistaking a copyright notice above a `package` line for documentation" — [go/doc](https://pkg.go.dev/go/doc)
- `Synopsis` extracts the first sentence: it ends at a period followed by a space, **unless** that period follows a single uppercase letter (so "Dr. Foo" / initials do not truncate it), or at the first paragraph break — [go/doc](https://pkg.go.dev/go/doc)
- `Doc` is a field on `Package`, `Func`, `Type` and `Value` alike; `Value` documents a possibly *grouped* `var`/`const` declaration and carries `Names` in declaration order — [go/doc](https://pkg.go.dev/go/doc)
- Structured notes use the form `MARKER(uid): note body`, where the marker is two or more uppercase letters and the uid is at least one character (colon optional); these land in `Package.Notes`, keyed by marker. `Bugs` is deprecated in favor of `Notes` — [go/doc](https://pkg.go.dev/go/doc)
- By default `go/doc` hides unexported declarations; `Mode` flag `AllDecls` includes them — [go/doc](https://pkg.go.dev/go/doc)
- `Package` exposes `Markdown`, `HTML`, `Text` renderers and `Parser`/`Printer` for customization, so comment bodies can be rendered to Markdown without writing a comment parser — [go/doc](https://pkg.go.dev/go/doc)
- `Examples` live in `_test.go` files and attach by name to types, functions, methods or the package; `Suffix` is only populated by `NewFromFiles`, and a *playable* example must be in a package whose name ends in `_test` — [go/doc](https://pkg.go.dev/go/doc)
- `NewFromFiles` "uses every file provided", so the caller must filter by build context (e.g. `go/build.Context.MatchFile`) itself, and it may mutate the ASTs unless `PreserveAST` is set — [go/doc](https://pkg.go.dev/go/doc)

### Inferences
- **Conventions the tool should adopt:** treat the leading comment group as the declaration's intent only after stripping `//go:` directives and applying the `IllegalPrefixes` rule; use the `Synopsis`-style first-sentence extraction for the on-screen one-liner and the full `Doc` for the narration script; surface `TODO(uid)` / `BUG(uid)` notes as a separate "known issues" beat rather than as the function's purpose.
- **The highest-value, lowest-effort win for narration quality** is `Examples` from `_test.go`: a compiling, name-matched usage example per function is exactly the artifact an explanation video wants, and `go/doc` resolves the name matching for free. A regex extractor that ignores `_test.go` throws this away.
- **A regex extractor will mis-attribute doc comments** in three specific ways: it will attach a license header to the package; it will attach `//go:embed` or `//nolint` to the next function; and for grouped `var`/`const` blocks it cannot tell whether a comment documents the block or the single line beneath it (`go/doc`'s `Value.Doc` vs per-name docs make that distinction explicit).

### Gaps
- `https://go.dev/doc/comment` (the official "Go Doc Comments" style spec, which covers lists, links, headings and deprecation notation inside comments) was not fetched in this pass. If the report wants to state the *formatting* rules of doc comments (not just their association), cite that page.

## Q5. Idiomatic Go project layout, package semantics, and whether per-FILE explanation makes sense

### Takeaway
A Go **package is a directory**, and all files in it share one lexical scope — so per-file explanation is structurally mismatched with Go in a way it is not for, say, Python or TypeScript modules. The pipeline should chunk at package granularity with files as sub-units; and it should know that `cmd/ internal/ pkg/` is a community convention, explicitly not a Go-team standard.

### Cited Findings
- `cmd/` holds main applications, one subdirectory per executable, with `main` kept small and importing logic from `internal/` and `pkg/` — [golang-standards/project-layout](https://github.com/golang-standards/project-layout)
- `internal/` holds private code other projects cannot import, **enforced by the Go compiler**, and may appear at multiple levels of the tree — [project-layout](https://github.com/golang-standards/project-layout)
- `pkg/` holds library code external applications may import; the repo advises caution and notes `internal/` is the stronger privacy mechanism while `pkg/` signals "safe for others" — [project-layout](https://github.com/golang-standards/project-layout)
- `api/` holds API definitions (OpenAPI/Swagger, JSON schema, protobuf); `configs/` holds config templates; `web/` holds static assets, server templates and SPAs — [project-layout](https://github.com/golang-standards/project-layout)
- The repo itself states the layout is "NOT an official standard defined by the core Go dev team", calls it a community collection of historical and emerging patterns, says it is overkill for small projects, and points to the official Go docs on organizing a module — [project-layout](https://github.com/golang-standards/project-layout)
- The layout is actively criticized: a widely-shared critique argues it is not a standard and that the repo's reasoning (e.g. rejecting `/src` because its users "came from the Java world") is ad hominem and technically weak, burying the real GOPATH-era import-path argument that matters less under Go Modules — [project-layout issue #278](https://github.com/golang-standards/project-layout/issues/278), [dev.to: "golang-standards/project-layout is not a standard"](https://dev.to/gabrielanhaia/golang-standardsproject-layout-is-not-a-standard-russ-cox-said-so-4kjh)
- `go/doc.Package` carries `Filenames` (plural) for one package, i.e. the standard library's unit of documentation is the package, assembled from many files — [go/doc](https://pkg.go.dev/go/doc)

### Inferences
- **Per-file explanation is genuinely weaker for Go than for other stacks, for concrete mechanical reasons:**
  1. Files in a package share scope with **no import statement** between them. So an import-graph-based dependency model sees `service/user.go` and `service/repo.go` as unrelated, when `user.go` may call a function defined in `repo.go`. The extractor's "imports" signal is blind to the majority of the edges inside a package.
  2. A method can be declared in a different file from its receiver type. Explaining `user_methods.go` alone cannot show the struct the methods operate on.
  3. Interface definition and implementation are structurally decoupled (Go has implicit satisfaction, no `implements` keyword). "Which concrete type satisfies `UserRepo`?" is a *type-checking* question, not a text question — and it is precisely the question an explanation video of a layered Fiber app needs to answer. No regex, and no AST-only parse, can answer it; it needs `go/types`.
  4. `init()` functions and package-level `var` initialization run in dependency order across the whole package, so "what happens at startup" is a package fact.
- **Recommended chunking:** package = chapter, file = scene. Order packages by the architectural role inferred from path (`cmd/` → entrypoint; `internal/server` or `internal/router` → wiring; `internal/middleware`; `internal/handler` or `internal/api`; `internal/service`; `internal/repository` or `internal/store`; `internal/model` or `internal/domain`). Then, within a package, order files so type declarations precede the methods on those types.
- **The tool must not hardcode `golang-standards` as truth.** Many real Fiber projects are flat (`main.go`, `handlers/`, `models/`, `database/`) or use a `domain/`-per-feature layout. Role inference should be *heuristic and reported as such* (name-based scoring over directory and file names, plus evidence: "this package is the handler layer because its functions have signature `func(c fiber.Ctx) error`"), with a fallback to "role unknown" rather than a confident wrong label.
- **Signature-based role detection is more reliable than path-based** for Fiber specifically: handlers are functions returning `error` with a single `fiber.Ctx`-ish parameter; middleware are functions returning `fiber.Handler`; repositories are methods whose receiver holds a `*gorm.DB` or `*sql.DB` field; models are structs with `gorm:` or `json:` tags and no methods with side effects.

### Gaps
- The dev.to article's headline attributes the "not a standard" position to Russ Cox, but when I fetched issue #278 I found **no statement from any Go team member in that thread**. The only solidly citable version of this claim is the project-layout README's own disclaimer. The report should cite the README, not attribute a quote to Russ Cox without a primary link (the dev.to piece points at `golang.org/issue/45861`, which I did not fetch and therefore cannot vouch for). Flagging this as a source-conflict/unverified attribution.

## Q6. How can a Python pipeline get a real Go AST?

### Takeaway
There are three realistic options with a clear ranking: a **small Go helper binary** using `go/parser` + `go/doc` (+ optionally `go/packages`/`go/types`) that emits JSON is the most faithful and the only one that can answer type-level questions; **tree-sitter-go via py-tree-sitter** is the best pure-Python option and is good enough for structure; **gopls** is powerful but the wrong tool for a batch pipeline.

### Cited Findings
- `go/doc` is in the Go standard library and already provides declaration-to-doc association, receiver/embedding metadata, grouped-value handling, example extraction and Markdown/Text rendering — i.e. a helper binary gets all of this for free rather than reimplementing it — [go/doc](https://pkg.go.dev/go/doc)
- `go/doc.NewFromFiles(fset, files, importPath, opts...)` takes parsed `*ast.File` values and a `*token.FileSet`; it does **not** filter by build context, so the helper must do that (e.g. `go/build.Context.MatchFile`) — a real implementation detail for the helper binary — [go/doc](https://pkg.go.dev/go/doc)
- py-tree-sitter installs as `pip install tree-sitter`, "has no library dependencies and provides pre-compiled wheels for all major platforms", and grammars ship as **separate** pre-compiled binary wheels (`pip install tree-sitter-<lang>`) — [py-tree-sitter README](https://github.com/tree-sitter/py-tree-sitter)
- Usage pattern: `Language(ts<lang>.language())` → `Parser(LANGUAGE)` → `parser.parse(bytes(src, "utf8"))` → `tree.root_node`; queries via `Query(LANGUAGE, pattern)` + `QueryCursor(query)`, with `captures(node)` and `matches(node)` (the README notes `matches()` is "much more useful when your captures within a query relate to each other"); `tree.walk()` returns a `TreeCursor` — [py-tree-sitter README](https://github.com/tree-sitter/py-tree-sitter)
- A `tree-sitter-go` grammar exists and is widely packaged across ecosystems (Go, Rust, Haskell bindings all publish it) — [tree-sitter/go-tree-sitter](https://pkg.go.dev/github.com/tree-sitter/go-tree-sitter), [docs.rs tree-sitter-go](https://docs.rs/tree-sitter-go/^0.21.0), [Hackage tree-sitter-go](https://hackage.haskell.org/package/tree-sitter-go-0.4.1.1/candidate)

### Inferences — trade-offs
| Option | What it gives | Costs / limits |
|---|---|---|
| **Go helper binary** (`go/parser` + `go/doc`, JSON out) | Exact Go grammar, correct line/column spans from `token.FileSet`, receivers, generics type params, grouped decls, interface method sets, struct tags, doc-comment association with `IllegalPrefixes` already applied, `_test.go` examples. Parses files that do not compile. | Requires the Go toolchain (or a cross-compiled static binary) in the pipeline image; adds a second language to the build; subprocess + JSON schema to maintain. |
| **Go helper binary + `go/packages` / `go/types`** | Everything above **plus** type resolution: which concrete type satisfies an interface, what a method call resolves to, the real type behind `any`/aliases, cross-package call edges. This is the only option that can answer the layered-architecture questions a Fiber explanation video needs. | Requires the module to **build** (deps downloadable, correct Go version). Much slower. Fails hard on broken or partially-vendored repos. Needs network or a warm module cache. |
| **tree-sitter-go via py-tree-sitter** | Pure `pip install`, prebuilt wheels, no Go toolchain, byte-accurate spans, error-tolerant on invalid code, declarative S-expression queries that map cleanly to "find all `call_expression` where function is a `selector_expression` with field `Get`". Handles every construct in Q3 correctly because it is a real grammar. | Syntax only — no type info, no interface satisfaction, no cross-package resolution. Grammar node names are not stable across grammar versions, so queries need pinning. Variable/prefix tracking (Q1) must still be written by hand on top of the tree. |
| **gopls** | Full LSP semantics: definitions, references, implementations, hovers with resolved types. | Designed as a long-lived interactive server, not a batch extractor; needs the module to build; JSON-RPC lifecycle management from Python is heavy; no stable machine-consumption contract. Wrong shape for a pipeline. |
| **Regex (status quo)** | Zero dependencies, works on any file. | Fails on everything in Q3. Cannot represent scope, so cannot resolve route prefixes or shadowed routers at all. |

- **Recommended architecture:** tree-sitter-go as the always-available baseline (keeps the pipeline pure-Python and tolerant of non-building repos), plus an *optional* Go helper binary that, when the toolchain and a building module are present, enriches the chunk JSON with doc comments, examples and interface-implementation edges. Emit a `fidelity` field on each chunk (`"regex" | "syntax" | "typed"`) so the narration generator can hedge its language when fidelity is low instead of asserting falsehoods.
- The route-prefix resolver from Q1 is **the same code either way** — it is a dataflow pass over an AST, not a parsing concern. So the parser decision and the Fiber-semantics decision are independent and should be sequenced: fix the parser first, then write the resolver against the tree.

### Gaps
- I could not confirm the current `tree-sitter-go` PyPI package name/version directly (`https://pypi.org/project/tree-sitter-go/` fetch was blocked). The py-tree-sitter README documents the `tree-sitter-<lang>` wheel convention with `tree-sitter-python` as its example and does not mention Go, so the exact Python package name and its grammar version should be verified with `pip index`/PyPI before the report states it.
- No benchmark found comparing tree-sitter-go parse throughput vs. a `go/parser` helper on a real repo; the "much slower" note for `go/packages` is about type-checking requiring a build, which is well known but not cited here.

## Q7. Data models: structs as DTOs/entities, and what struct tags tell a tool

### Takeaway
Struct tags are the richest machine-readable signal in a Go backend — `json:` tags define the exact wire shape of every API request/response and `gorm:` tags define the table mapping — and they are also the single most regex-hostile construct in Go, because they are raw string literals containing quotes, colons and semicolons.

### Cited Findings
- `gorm.Model` is the canonical embedded base: `type Model struct { ID uint \`gorm:"primaryKey"\`; CreatedAt time.Time; UpdatedAt time.Time; DeletedAt gorm.DeletedAt \`gorm:"index"\` }` — embedding it silently adds four columns and soft-delete behavior to any entity — [GORM models](https://gorm.io/docs/models.html)
- `gorm:"primaryKey"` on any field overrides the default `ID` primary key: `UUID string \`gorm:"primaryKey"\`` — [GORM conventions](https://gorm.io/docs/conventions.html)
- `gorm:"embedded"` on a **named** (non-anonymous) struct field flattens that struct's fields into the parent table — [GORM models](https://gorm.io/docs/models.html)
- Associations are expressed by field *type*, not by tag: `type User struct { gorm.Model; CreditCards []CreditCard }` is a has-many, with `CreditCard.UserID` as the implicit foreign key by convention — [GORM has-many](https://gorm.io/docs/has_many.html)
- `gorm:"foreignKey:UserRefer"` overrides the implicit foreign-key field name — [GORM has-many](https://gorm.io/docs/has_many.html)

### Inferences
- **What a tool can extract, and what each signal means for the narration:**
  - `json:"name,omitempty"` / `json:"-"` → the exact API field name, whether it is optional, and whether it is *excluded from the response*. The last one is a security-relevant beat: a `Password string \`json:"-"\`` field is worth narrating explicitly.
  - `json:"id,string"` → type coercion on the wire; the JSON type differs from the Go type.
  - `gorm:"column:x;type:varchar(255);not null;uniqueIndex;default:0"` → column name, SQL type, constraints. Semicolon-separated key:value pairs inside one tag; the parser must split on `;` then `:`, with values that may themselves contain parentheses and commas (`type:varchar(255)`).
  - `validate:"required,email"` (go-playground/validator) → the request-validation contract, which is exactly what a "how does this endpoint validate input" narration beat needs.
  - Embedded `gorm.Model` → implies soft deletes and timestamps that appear nowhere in the struct's own field list.
  - A slice-of-struct or pointer-to-struct field → an association; the tool should emit a relationship edge, not just a field.
- **How to extract them correctly:** struct tags are a `field_declaration`'s `tag` child in tree-sitter-go, or `ast.Field.Tag` (a `*ast.BasicLit`) in `go/ast`. Either way, get the raw literal from the parser and then parse it with the documented tag convention (space-separated `key:"value"` pairs, per `reflect.StructTag`). Never regex the field line. A regex that splits on `"` breaks on `gorm:"column:name"` the moment a tag value contains an escaped quote, and breaks on multi-tag fields in ways that silently drop the second tag.
- **DTO vs entity discrimination** is a useful narrative distinction the tool can infer: a struct with only `json:`/`validate:` tags and no `gorm:` tags, living in a `handler`/`dto`/`request` package, is a DTO; a struct with `gorm:` tags or embedded `gorm.Model`, in a `model`/`domain`/`entity` package, is an entity. Structs with *both* indicate the project leaks its DB model to the API — a genuinely interesting thing for an explanation video to point out.
- A regex extractor that reports "data models (structs)" without parsing tags reports the field *names and Go types*, i.e. the least useful half of the information. The API contract and the DB schema — the two things a backend explanation video is actually about — live in the tags.

### Gaps
- No citation gathered here for `reflect.StructTag`'s exact format grammar (space-separated `key:"value"`, conventional key = package name). Worth citing `https://pkg.go.dev/reflect#StructTag` in the report.
- No citation gathered for `encoding/json` tag option semantics (`omitempty`, `-`, `,string`); cite `https://pkg.go.dev/encoding/json#Marshal` if the report asserts them.

## Q8. What narrative ordering makes a Go Fiber codebase comprehensible?

### Takeaway
Follow the request's path through the program, not the filesystem: entrypoint → config/DI wiring → router and group tree → middleware chain → handler → service → repository → model/schema, with the models explained *inline at first use* rather than as a final chapter. The ordering is justified by Fiber's own structure, where the group tree is the index of the application.

### Cited Findings
- The grouping guide's own framing — nested `api` → `v1`/`v2` groups whose routes "are flattened with their group prefixes" — presents the group tree as the organizing structure of a Fiber app — [Fiber grouping guide](https://docs.gofiber.io/guide/grouping)
- Middleware runs before handlers and must explicitly continue the chain with `c.Next()`, and several handlers on one `Use` "run in order" — so the chain is ordered and the order is in the source — [Fiber routing guide](https://docs.gofiber.io/guide/routing)
- `cmd/` main code "should stay small, mostly importing logic from `internal/` and `pkg/`" — so the entrypoint is the right opening chapter precisely because it is a table of contents — [project-layout](https://github.com/golang-standards/project-layout)

### Inferences — proposed chapter order
1. **`go.mod`**: module path, Go version, and the framework + version detection (Fiber v2 vs v3, GORM, driver). 20–30s. This is also where the tool should state its own fidelity for the rest of the video.
2. **`cmd/.../main.go`**: what is constructed and in what order — config load, DB connect, `fiber.New(fiber.Config{...})` (the config struct is worth reading: error handler, prefork, body limit), route registration call, `app.Listen`.
3. **Router / wiring**: the resolved route table as a single visual — method, full path, handler, middleware chain. This is the highest-value artifact the whole pipeline can produce and the one most dependent on getting Q1 right. Present it as a tree mirroring the groups.
4. **Middleware**, in registration order, with the `fiber.Handler`-returning-closure idiom explained once (it is unfamiliar to viewers from other stacks and recurs everywhere).
5. **One route traced end to end**, chosen as the "spine": handler → service → repository → DB → response. Explain the DTO at the handler boundary and the entity at the repository boundary *here*, where they are motivated.
6. **Handlers** package: the `func(c fiber.Ctx) error` contract, how params/body are bound, how errors become responses (and whether a custom `ErrorHandler` in `fiber.Config` intercepts them).
7. **Services**: the business logic; note interface dependencies.
8. **Repositories**: the `*gorm.DB` usage, queries, transactions.
9. **Models/schema**: the full struct set with tags → JSON shape and table mapping, associations as a diagram.
10. **Cross-cutting**: `init()` functions, package-level state, goroutines/background workers, graceful shutdown.

- **Two Go-specific narrative beats a tool should not skip**, because they are where Go differs most from the stacks viewers come from: (a) implicit interface satisfaction — "this concrete repo satisfies this interface without saying so" — which is the whole dependency-inversion story of the codebase; and (b) the explicit `if err != nil` error-propagation chain, which replaces exceptions and visibly shapes every function signature.
- **Per-package, not per-file, chapters** follow from Q5; a per-file video for `service/user.go` that cannot show the type its methods hang off will read as disjointed.

### Gaps
- No source found evaluating narrative orderings for code-explanation video specifically; this ordering is my synthesis from how Fiber's own docs sequence material (routing → grouping → middleware) plus the request-path logic. Presented as a recommendation, not a cited finding.
