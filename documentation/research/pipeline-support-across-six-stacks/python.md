# Python (incl. Django, FastAPI, Flask) support for an automated code-explanation pipeline

Scope note: the existing pipeline is regex-based, brace-matched, and oriented to TypeScript/TSX and Go. Every section below is written against that baseline, with emphasis on what silently breaks on Python.

## Q1 (CRITICAL): Python has no braces — how do you find where a function ends, and how cheap is the correct approach?

### Takeaway
Brace matching cannot work on Python at all; the correct and essentially free answer is the standard-library `ast` module, which since Python 3.8 records `end_lineno`/`end_col_offset` on every node that has a position — so exact line ranges for functions and classes come out of a zero-dependency parse, and the pipeline is already written in Python so the parser is the same interpreter it runs under.

### Cited Findings
- `ast.parse(source, filename, mode, *, type_comments=False, feature_version=None, optimize=-1, module=None)` parses source into a tree; "In particular, `ast.parse()` won't do any scoping checks, which the compilation step does." It raises `ValueError` if the source contains a null character. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Position attributes: "The `lineno` and `end_lineno` are the first and last line numbers of source text span (1-indexed so the first line is line 1) and the `col_offset` and `end_col_offset` are the corresponding UTF-8 byte offsets of the first and last tokens that generated the node." They are documented for `expr` and `stmt` nodes and also for `alias`, `arg`, `keyword`, `excepthandler`, `type_param`. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- End positions are optional in the grammar: "Note that the end positions are not required by the compiler and are therefore optional. The end offset is *after* the last symbol, for example one can get the source segment of a one-line expression node using `source_line[node.col_offset : node.end_col_offset]`." Their grammar type is `int?`, so they can be `None`, and hand-built nodes may lack them. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `end_lineno`/`end_col_offset` were added in Python 3.8: "AST nodes now have `end_lineno` and `end_col_offset` attributes, which give the precise location of the end of the node. (This only applies to nodes that have `lineno` and `col_offset` attributes.)" (Contributed by Ivan Levkivskyi, bpo-33416.) — [What's New in Python 3.8](https://docs.python.org/3/whatsnew/3.8.html)
- `ast.get_source_segment(source, node, *, padded=False)` (added 3.8) "Get source code segment of the *source* that generated *node*. If some location information (`lineno`, `end_lineno`, `col_offset`, or `end_col_offset`) is missing, return `None`." — [Python `ast` docs](https://docs.python.org/3/library/ast.html); [What's New in Python 3.8](https://docs.python.org/3/whatsnew/3.8.html)
- Node fields the pipeline needs, verbatim from the grammar table:
  - `FunctionDef`: `name`, `args`, `body`, `decorator_list`, `returns`, `type_comment`, `type_params`. `returns` is the return annotation; `decorator_list` is "stored outermost first."
  - `AsyncFunctionDef`: same fields as `FunctionDef`, used for `async def`.
  - `ClassDef`: `name`, `bases`, `keywords`, `body`, `decorator_list`, `type_params` (`keywords` mainly holds `metaclass=`).
  - `Import`: `names` (list of `alias`). `ImportFrom`: `module`, `names`, `level` — `module` is `None` for `from . import foo`, `level` is 0 for absolute imports. `alias`: `name`, `asname` (`None` without `as`).
  - `Call`: `func`, `args`, `keywords` — `func` is often a `Name` or `Attribute`.
  - `Assign`: `targets`, `value`, `type_comment`. `AnnAssign`: `target`, `annotation`, `value`, `simple` (`simple` is 1 only for a bare, unparenthesized name).
  - `arguments`: `posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kw_defaults`, `kwarg`, `defaults` (`defaults` covers the last *n* positional arguments). `arg`: `arg`, `annotation`, `type_comment`.
  — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Traversal: `ast.walk(node)` "Recursively yield all descendant nodes in the tree starting at *node* (including *node* itself), in no specified order." `ast.NodeVisitor` warns that "child nodes of nodes that have a custom visitor method won't be visited unless the visitor calls `generic_visit()` or visits them itself." — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `ast.unparse()` (3.9+) exists for rendering a node back to source, but "The produced code string will not necessarily be equal to the original code that generated the `ast.AST` object." — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `type_comments=True` on `ast.parse` surfaces PEP 484/526 type comments; "Without this flag, type comments will be ignored, and the `type_comment` field on selected AST nodes will always be `None`." `feature_version=(3, N)` lets you parse as an earlier Python 3 (e.g. `(3, 4)` treats `async`/`await` as non-reserved words). — [Python `ast` docs](https://docs.python.org/3/library/ast.html); [What's New in Python 3.8](https://docs.python.org/3/whatsnew/3.8.html)

### Inferences
- The whole "find the function body" problem collapses to `node.lineno .. node.end_lineno` for `FunctionDef`/`AsyncFunctionDef`/`ClassDef`. Cost is one `ast.parse()` per file — a C-implemented parse of the same grammar CPython itself uses, so it is both faster and strictly more accurate than multi-pass regex, and adds zero third-party dependencies to a Python-hosted pipeline. This is the single highest-leverage change for Python support.
- Caveat worth encoding: `node.lineno` for a decorated function points at the `def` line, **not** at the first decorator. To render a "full definition" slide (decorators included) the start line must be `min(d.lineno for d in node.decorator_list)` when `decorator_list` is non-empty. A pipeline that uses `lineno` naively will cut `@app.get("/items")` off the top of the clip — which is exactly the line that explains what the function is.
- `end_lineno` ends at the last token of the body, so trailing blank lines and trailing comments after a function are excluded. That is the behaviour you want for a code clip, but it means two adjacent functions' ranges are not contiguous; don't assume `next.lineno == prev.end_lineno + 1`.
- Because end positions are typed `int?`, defensive code should fall back to `ast.get_source_segment` returning `None` rather than assuming a span exists.
- `ast.walk` returning nodes "in no specified order" means it must not be used to produce the narrative ordering of a file. Use an explicit `NodeVisitor` over `module.body` in source order, or sort collected nodes by `lineno`.

### Things a brace-and-regex pipeline gets silently WRONG on Python (the important list)
These are inferences from the cited `ast` semantics plus the language definition, but they are the failure modes most worth calling out in the report:
- **Brace matching has nothing to match.** There are `{}` in Python source, but they are dict and set literals, f-string replacement fields, and `%`/`.format` style templates. A brace matcher pointed at Python will pick an arbitrary dict literal inside the body and report a function that "ends" in the middle of itself. It fails *silently* — it produces a plausible-looking wrong line range, not an error.
- **Colon-and-indent block structure.** The correct non-AST fallback (if one were ever needed) is: a block ends at the first subsequent line whose indentation is less than or equal to the `def` line's indentation and which is not blank and not a continuation. Getting that right requires tracking implicit line joining inside `()[]{}`, explicit `\` continuations, tabs-vs-spaces, and triple-quoted strings that contain lines that *look* dedented. `ast` handles all of these; a line-indent heuristic will mis-handle at least the triple-quoted-string case.
- **Regex "def" detection over-matches.** `def` appearing inside a docstring, a comment, or a string literal (`sql = "... def ..."`) is indistinguishable to regex. `#` inside a string is not a comment. Python has no `/* */`, so a comment-stripping pre-pass written for TS/Go will corrupt Python strings.
- **One-line bodies and nesting.** `def f(): return 1` is legal, as are nested `def`s, closures, decorators that are themselves functions, and methods inside classes inside functions. Regex line-range heuristics typically flatten the nesting and mis-attribute the inner functions.
- **Multi-line signatures.** Long parameter lists wrapped across lines mean the `def` "line" is not one line; `node.args` gives the structured parameters regardless.
- **`async def` and decorators are separate node types / separate lines.** A single regex for `def` misses that `async def` must be classified as `AsyncFunctionDef` (relevant for FastAPI narration), and that the decorator above the `def` is the part carrying the route.
- **`@property`, `@staticmethod`, `@classmethod`, `@overload`, `@functools.cached_property`** change what a method *is* for explanation purposes; they are `decorator_list` entries, not part of the `def` line.
- **Significant whitespace means line ranges are the only safe slicing unit.** Column-based slicing of a Python block (as you might do for a brace-delimited body) produces syntactically invalid fragments.

### Gaps
- The `ast` docs page does not itself state the version that introduced `end_lineno`; that had to be confirmed from the 3.8 release notes (done above). No conflict found between the two.
- I could not fetch LibCST's "Why LibCST?" page (WebFetch hit a usage limit), so the precise stated tradeoffs of LibCST vs `ast` are uncited below.

## Q2: Docstrings are inside the body as a string literal, not a comment above — how does this differ from JSDoc/Go doc comments, and what does `ast.get_docstring` give?

### Takeaway
A Python doc comment is the first statement *inside* the suite, so "scan upward from the definition for leading comment lines" — the JSDoc/Go strategy — returns nothing on well-documented Python; `ast.get_docstring(node, clean=True)` is the correct extractor and also does the dedent for you.

### Cited Findings
- "Return the docstring of the given *node* (which must be a `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, or `Module` node), or `None` if it has no docstring. If *clean* is true, clean up the docstring's indentation with `inspect.cleandoc()`." "Changed in version 3.5: `AsyncFunctionDef` is now supported." The docs do not say what happens for other node types, so it should not be relied on for them. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Griffe parses docstrings into structured data and ships parsers for **Google**, **Numpydoc** and **Sphinx** styles, plus `griffe.parse_auto` which detects the style automatically. — [Griffe docs](https://mkdocstrings.github.io/griffe/)
- PEP 8: module-level dunder names "should be placed after the module docstring but before any import statements" (except `from __future__` imports) — i.e. the module docstring is positionally first. — [PEP 8](https://peps.python.org/pep-0008/)

### Inferences
- `ast.get_docstring` works on exactly four node types: `Module`, `ClassDef`, `FunctionDef`, `AsyncFunctionDef`. There is **no** docstring for a variable, a parameter, or a module-level attribute in the AST sense; tools that appear to show attribute docs (Sphinx autodoc, pdoc, Griffe) recover them from the *following* string-expression statement or from `#:` comments, which the pipeline would have to implement by hand if it wants them.
- Because the docstring is `node.body[0]`, naive "body = everything after the def line" code includes the docstring in the body clip, and the narration then re-reads text the slide already shows. Worth stripping: body for narration purposes should start at `node.body[1].lineno` when `body[0]` is a docstring `Expr(Constant(str))`.
- Conversely, a comment block *above* a Python def is usually a sectioning/TODO comment, not documentation. Reporting it as the doc comment (the TS/Go behaviour) produces actively misleading narration.
- Structure recoverable from docstrings is style-dependent. Google style (`Args:` / `Returns:` / `Raises:`) and Numpydoc (underlined sections) are parseable into per-parameter descriptions; Sphinx/reST style uses `:param x:` / `:returns:` / `:raises:` field lists. A pipeline that wants per-parameter narration should either vendor one parser or delegate to Griffe's `parse_auto` rather than regexing all three. Raw docstring text is still fine as narration input.
- Docstrings are *runtime values*, which means they can be f-strings, concatenated literals, or absent-but-replaced by `__doc__` assignment. `ast.get_docstring` returns `None` for an f-string docstring (it is not a plain constant). Treat `None` as "undocumented" and fall back to the signature.

### Gaps
- No primary source fetched for how Sphinx autodoc / pdoc specifically recover *attribute* docstrings; stated above as inference.

## Q3: There is no `export` keyword — what should the tool report as "exported"?

### Takeaway
Python visibility is convention plus one optional declaration: a single leading underscore means non-public, `__all__` is the explicit public-API declaration, and PEP 8 additionally treats *documented* interfaces as public and *imported* names as implementation details — so "exported" should be computed, not pattern-matched, and reported as a confidence-bearing judgement.

### Cited Findings
- PEP 8, Public and Internal Interfaces: "Documented interfaces are considered public" and "All undocumented interfaces should be assumed to be internal." — [PEP 8](https://peps.python.org/pep-0008/)
- "modules should explicitly declare the names in their public API using the `__all__` attribute"; setting `__all__` to an empty list means the module "has no public API." — [PEP 8](https://peps.python.org/pep-0008/)
- "Even with `__all__` set appropriately, internal interfaces" should still be "prefixed with a single leading underscore." — [PEP 8](https://peps.python.org/pep-0008/)
- "An interface is also considered internal if any containing namespace (package, module or class) is considered internal." — [PEP 8](https://peps.python.org/pep-0008/)
- "Imported names should always be considered an implementation detail." — [PEP 8](https://peps.python.org/pep-0008/)
- "Use one leading underscore only for non-public methods and instance variables"; `_single_leading_underscore` is a "weak 'internal use' indicator." — [PEP 8](https://peps.python.org/pep-0008/)
- Designing for Inheritance: "If in doubt, choose non-public; it's easier to make it public later than to make a public attribute non-public." "Public attributes should have no leading underscores." — [PEP 8](https://peps.python.org/pep-0008/)
- Griffe models this distinction explicitly: its breakage output refers to `is_exported` and `is_public` methods, its serialized model includes an `exports` list, and `griffe.find_breaking_changes` takes an `ignore_private` parameter. It also ships extensions named `public-redundant-aliases` and `public-wildcard-imports`. — [Griffe docs](https://mkdocstrings.github.io/griffe/)

### Inferences
- Concrete rule the pipeline can implement, in priority order:
  1. If the module defines `__all__` (an `Assign` whose target is `Name(id="__all__")` with a `List`/`Tuple` of `Constant` strings), the public surface **is** that list. Names not in it are internal, even without an underscore. Report `exported = name in __all__`.
  2. Otherwise, `exported = not name.startswith("_")`, and additionally require that no enclosing module/package component starts with `_` (PEP 8's containing-namespace rule — so anything under a `_internal/` package is internal).
  3. Dunder methods (`__init__`, `__str__`, …) are special: they start with `_` but are part of the public behaviour of a class. Classify them as "protocol/magic methods", not as private.
  4. Name mangling: `__x` (two leading, at most one trailing underscore) inside a class is strongly private; `_x` is weakly private.
  5. Names that are only *imported* into the module (`Import`/`ImportFrom` aliases) should be reported as re-exports/dependencies, not as things this file defines — PEP 8 says imported names are implementation details. The exception is a package `__init__.py`, where `from .thing import Thing` plus `__all__` is the idiomatic public-API façade; there, imports *are* the exports.
- Therefore "is_exported" should be a tri-state with provenance (`declared_in_all` / `public_by_convention` / `private_by_underscore`), not a boolean. For narration this matters: "this module's public API is the three names in `__all__`" is a genuinely useful opening sentence, and is only available when `__all__` exists.
- A regex looking for `export`/capitalised-identifier (Go's rule) finds nothing in Python and will mark everything either exported or nothing exported. Go's "capital letter = exported" rule is actively inverted in Python, where capitalised names are *classes* by convention (PEP 8 CapWords) and say nothing about visibility.

### Gaps
- Griffe's exact algorithm for `is_public` (how it weighs `__all__`, underscores, and re-export aliasing) is not spelled out on the page fetched; it links to a "Public APIs" recommendations page I did not fetch.

## Q4: Units of meaning for Django, and which files matter most

### Takeaway
Django's semantics live in the *file name*, not in the code: a Django project is a settings module plus a root URLconf plus N app packages whose roles are fixed by filename convention (`models.py`, `views.py`, `urls.py`, `admin.py`, `apps.py`, `migrations/`), so a Django-aware analyzer should dispatch on path first and parse second.

### Cited Findings
- Django finds the root URLconf from the `ROOT_URLCONF` setting (unless middleware sets `request.urlconf`), then looks for a `urlpatterns` list in that module. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- `urlpatterns` is an ordered list; "Django tests the patterns in order and stops at the first match, so put special cases first." Matching runs against `path_info`, excluding query string and domain. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- `include()` delegates the remainder of the URL to another URLconf module, and parent-captured parameters are passed down; `include()` also accepts an inline list of patterns to share a prefix. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- Application namespace is set with `app_name` in the app's URLconf; instance namespace with `namespace=` in `include()`, defaulting to the application namespace. Namespaced routes are reversed with `:` (e.g. `reverse("polls:detail", args=(5,))`, `{% url 'publisher-polls:detail' pk=3 %}`). — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- `handler400`, `handler403`, `handler404`, `handler500` are module-level assignments valid **only** in the root URLconf; values can be callables or dotted import strings. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)

### Inferences
- **Ordering for explanation** (most to least load-bearing, and this is the order a video should follow):
  1. `settings.py` — `INSTALLED_APPS` tells you what the project *is* made of; `DATABASES`, `MIDDLEWARE`, `AUTH_USER_MODEL`, `TEMPLATES`, `ROOT_URLCONF` are the project's wiring. This file is the map.
  2. Root `urls.py` — the request-entry table; the `include()` edges give you the app graph for free.
  3. Per app: `models.py` — the domain vocabulary. Everything else is phrased in terms of these nouns.
  4. Per app: `urls.py` (routes) → `views.py` (behaviour) → `serializers.py` / `forms.py` (I/O shape) → `admin.py` (back-office surface).
  5. Supporting, explain only on demand: `apps.py` (AppConfig, `ready()` is where signals get wired), `signals.py`, `managers.py` / custom `QuerySet`s, `middleware.py`, `templates/`, `tasks.py` (Celery), `tests.py`.
  6. `migrations/` — **auto-generated; should be excluded from narration by default.** They are the highest-line-count, lowest-explanatory-value files in a Django repo, and a naive "explain every .py file" pipeline will waste most of its runtime on them. They are useful only as a schema-history timeline.
- Structural features a Django-aware extractor should recognise:
  - A **model** = `ClassDef` whose `bases` include `models.Model` (or an `Attribute` ending in `.Model`, or a project base class). Fields = class-body `Assign` statements whose `value` is a `Call` to `models.<X>Field`. The field *type* and its kwargs (`null`, `blank`, `max_length`, `choices`, `related_name`, `on_delete`) are the explanation content.
  - **Relations** are the graph edges: `ForeignKey`, `OneToOneField`, `ManyToManyField`. The first positional arg (a `Name`, an `Attribute`, or a **string** like `"app.Model"` for lazy references) is the target. String targets are why a regex import-graph misses most Django relations.
  - `class Meta:` nested inside a model (ordering, `db_table`, `unique_together`, `constraints`, `indexes`, `abstract`) and `def __str__` are the two highest-value non-field members.
  - A **view** is either a function taking `request` as first parameter, or a `ClassDef` inheriting a generic view (`ListView`, `DetailView`, `APIView`, `ModelViewSet`); for CBVs the explanatory content is the *class attributes* (`model`, `queryset`, `serializer_class`, `template_name`, `permission_classes`) plus overridden hook methods (`get_queryset`, `get_context_data`, `form_valid`).
  - `admin.py`: `@admin.register(Model)` decorator or `admin.site.register(Model, ModelAdmin)` call; the `ModelAdmin` attributes (`list_display`, `search_fields`, `inlines`) are the content.
  - `apps.py`: `AppConfig` subclass; `default_auto_field`, `name`, and `ready()` (signal registration happens here).
  - DRF `serializers.py`: `ClassDef` inheriting `serializers.ModelSerializer`/`Serializer`, with `class Meta: model = X; fields = [...]`. This is the API contract and deserves its own narration beat.
- The decorator set to recognise on Django views: `@login_required`, `@permission_required`, `@require_http_methods` / `@require_POST`, `@csrf_exempt`, `@cache_page`, `@transaction.atomic`, and DRF's `@api_view(["GET","POST"])`, `@action(detail=True, methods=["post"])`, `@permission_classes`.

### Gaps
- I was unable to fetch the Django "reusable apps"/tutorial page that enumerates the `startapp` and `startproject` file layouts (WebFetch usage limit hit). The per-file roles above are therefore marked as inference rather than quoted from Django docs; the report writer should cite https://docs.djangoproject.com/en/5.2/intro/tutorial01/ and https://docs.djangoproject.com/en/5.2/intro/reusable-apps/ if a direct quote is wanted.
- `handler404`-style module-level string assignments are the one case where a *dotted string* is a view reference; I found no doc statement about how documentation tools resolve these.

## Q5: Units of meaning for FastAPI, and extracting method + path

### Takeaway
FastAPI route information lives entirely in a decorator (`@router.get("/{item_id}")`) plus the handler's typed signature, and the *full* path is only knowable by composing `APIRouter(prefix=...)` with `app.include_router(..., prefix=...)` — so method+path extraction is a two-file join, not a single-line regex.

### Cited Findings
- `APIRouter` is described as "a 'mini `FastAPI`' class", and `app/routers/` is "the equivalent of Flask's Blueprints." — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Router declaration and path operations:
  ```python
  from fastapi import APIRouter
  router = APIRouter()

  @router.get("/users/", tags=["users"])
  async def read_users(): ...

  @router.get("/users/{username}", tags=["users"])
  async def read_user(username: str): ...
  ```
  The router variable "can be named anything", and all `FastAPI` parameters (`parameters`, `responses`, `dependencies`, `tags`, …) are supported. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Router-level configuration carries a prefix that must not end with `/`:
  ```python
  router = APIRouter(
      prefix="/items",
      tags=["items"],
      dependencies=[Depends(get_token_header)],
      responses={404: {"description": "Not found"}},
  )

  @router.get("/{item_id}")
  async def read_item(item_id: str): ...
  ```
  — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Assembly in `main.py`:
  ```python
  app = FastAPI(dependencies=[Depends(get_query_token)])   # global dependency
  app.include_router(users.router)
  app.include_router(
      admin.router,
      prefix="/admin",
      tags=["admin"],
      dependencies=[Depends(get_token_header)],
      responses={418: {"description": "I'm a teapot"}},
  )

  @app.get("/")
  async def root(): ...
  ```
  `include_router` accepts the same `prefix`, `tags`, `dependencies`, `responses`, so a router you don't own can be configured at inclusion time; those settings apply only in the including app. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Per-operation `tags` and `responses` are **merged** with the router's values (the example `PUT` gets tags `["items", "custom"]` and both 404 and 403 responses). — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Documented dependency execution order: (1) router dependencies, (2) decorator `dependencies`, (3) normal parameter dependencies. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Shared dependencies are plain (often `async`) functions using `Annotated[...]` parameter metadata, e.g. `async def get_token_header(x_token: Annotated[str, Header()])`, raising `HTTPException` on failure. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Other inclusion patterns: the same router can be included under two prefixes (`/api/v1`, `/api/latest`); routers nest via `router.include_router(other_router)`; the docs warn not to mutate `router.routes` directly. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Relative-import discipline matters for resolving the join: `from ..dependencies import ...` reaches `app/dependencies.py` from `app/routers/`. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- The entrypoint can be declared in `pyproject.toml` as `[tool.fastapi] entrypoint = "app.main:app"`. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- The Bigger Applications page does **not** document `response_model`; it appears only as a navigation link, so the authoritative source for it is the "Response Model - Return Type" tutorial. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)

### Inferences
- Extraction algorithm for method+path, concretely:
  1. For each `FunctionDef`/`AsyncFunctionDef`, walk `decorator_list` for a `Call` whose `func` is an `Attribute` with `attr` in `{get, post, put, patch, delete, head, options, trace}` (also `api_route`, `websocket`) and whose `value` is a `Name`.
  2. HTTP method = `attr.upper()`; local path = `decorator.args[0]` if it is a `Constant` str.
  3. Resolve the decorator's receiver `Name` by scanning module-level `Assign` statements for `x = APIRouter(...)` or `x = FastAPI(...)`, and read `prefix=` from its keywords. **Do not assume the variable is called `app` or `router`** — the docs explicitly say it can be named anything.
  4. Cross-file: find `*.include_router(<module>.<var>, prefix=...)` calls (and nested `router.include_router(...)`) to compute the mount prefix. Full path = concat of app-level prefix(es) + router prefix + decorator path.
  5. Report `confidence < 1` and `assumed: true` whenever the path or prefix is a variable/f-string rather than a literal, or when the router could not be traced to an `include_router` call.
- A regex that only matches `@app.get("...")` will under-report badly in any realistic FastAPI project, because real projects put routes on `APIRouter`s with prefixes. Worse, it will report *wrong* paths — `/{item_id}` instead of `/items/{item_id}` — which is a confidently-stated falsehood in a narration. The same router included twice means one function legitimately has two paths.
- The explanatory units of a FastAPI file, in order: (1) the Pydantic models (request/response schemas), (2) the dependencies (`Depends` graph — this is FastAPI's distinctive feature and the thing most worth a visual), (3) the path operations, (4) `response_model`/`status_code`/`tags` as the contract metadata, (5) `async def` vs `def` (FastAPI runs sync handlers in a threadpool — worth one narration sentence because it is a frequent source of confusion).
- The `Depends` graph is extractable statically and is a genuine call graph: for each parameter, an `Annotated[T, Depends(fn)]` or a default value `= Depends(fn)` names a function in the project. That gives per-endpoint edges to auth, DB-session and pagination helpers without any type inference. `Annotated[...]` is the modern form and a pipeline that only looks at *default values* will miss it entirely.
- Other FastAPI decorators/registrations worth recognising: `@app.on_event("startup")` (legacy) and the `lifespan=` async context manager, `@app.middleware("http")`, `@app.exception_handler(ExcType)`, `@app.websocket("/ws")`, `app.mount("/static", StaticFiles(...))`, `app.add_middleware(CORSMiddleware, ...)`.
- `Query`, `Path`, `Body`, `Header`, `Cookie`, `Form`, `File`, `Security` inside `Annotated` tell you *where* each parameter comes from — this is the single richest source of accurate narration about an endpoint and is invisible to a route-regex.

### Gaps
- `response_model` semantics are not covered by the page I fetched; cite the dedicated FastAPI response-model tutorial instead of this page.

## Q6: Units of meaning for Flask

### Takeaway
Flask's structure is an app (often built by a `create_app()` factory) plus Blueprints that *record* route registrations to be applied later, so the real URL of a view is only known at `register_blueprint(..., url_prefix=...)` time — the same deferred-registration join as FastAPI's routers.

### Cited Findings
- A `Blueprint` "works similarly to a `Flask` application object, but it is not actually an application. Rather it is a *blueprint* of how to construct or extend an application." — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Creation takes a name and `__name__`; the second argument sets the resource folder and the name becomes the endpoint prefix:
  ```python
  simple_page = Blueprint('simple_page', __name__, template_folder='templates')
  ```
  — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Route decorators on a blueprint don't attach immediately: "the blueprint will record the intention of registering the function `show` on the application when it's later registered. Additionally it will prefix the endpoint of the function with the name of the blueprint." Multiple decorators can stack on one view:
  ```python
  @simple_page.route('/', defaults={'page': 'index'})
  @simple_page.route('/<page>')
  def show(page): ...
  ```
  — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Registration and prefixing:
  ```python
  app.register_blueprint(simple_page)                       # /<page> and /
  app.register_blueprint(simple_page, url_prefix='/pages')  # /pages/<page> and /pages/
  ```
  The blueprint name affects only the endpoint, not the URL; endpoints are referenced as `url_for('simple_page.show', page='about')`, or `url_for('.show', ...)` relatively inside the same blueprint. `app.url_map` shows the resolved rules. — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Nesting: `parent.register_blueprint(child)` makes endpoints `parent.child.<view>` and URL prefixes combine. — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Blueprint template folders have lower priority than the application's; the docs recommend namespacing templates in a subfolder (`admin/templates/admin/index.html`, rendered as `admin/index.html`). — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Blueprint-level 404/405 handlers "run only when raised from one of the blueprint's own views", so URL-based decisions need application-level handlers. — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- The Blueprints page does not name the application-factory pattern, but states the supporting idea — a project "could instantiate an application object, initialize several extensions, and register a collection of blueprints" — and notes the limit that "you cannot unregister a blueprint once an application was created without having to destroy the whole application object." — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)

### Inferences
- Explanatory units, in order: (1) `create_app()` factory / `app = Flask(__name__)` and the config loading, (2) extension initialisation (`db = SQLAlchemy()` at module scope + `db.init_app(app)` in the factory — the two-step `init_app` pattern is the thing newcomers find confusing and deserves narration), (3) Blueprint definitions and their `url_prefix` at registration, (4) view functions, (5) models (usually SQLAlchemy `db.Model` subclasses), (6) `before_request`/`after_request`/`teardown_appcontext` hooks, (7) `errorhandler`s, (8) CLI commands (`@app.cli.command()`).
- Extraction notes: `@app.route("/x", methods=["GET","POST"])` carries the method list in a **keyword argument**, not in the decorator name — the opposite of FastAPI. Default is GET-only. Flask also supports `app.add_url_rule("/x", "endpoint", view_func)` (no decorator at all) and `MethodView`/`as_view()` class-based views, both of which a decorator-only regex misses entirely.
- Stacked `@route` decorators mean one function legitimately maps to several URL rules; a "one route per function" data model is wrong for Flask.
- Because the factory defers everything, `app` often does not exist at module scope in a well-structured Flask project. A regex looking for `app = Flask(` to anchor route search will find nothing in exactly the codebases most worth explaining.
- Flask-SQLAlchemy models, Flask-Migrate migrations, Flask-WTF forms, Flask-Login `current_user`, Marshmallow schemas are the common extension vocabulary; recognising the base classes (`db.Model`, `FlaskForm`, `ma.Schema`) is enough to classify the file.

### Gaps
- The Blueprints page does not document the factory pattern by name; the canonical source is Flask's "Application Factories" / tutorial pages, which I did not fetch.

## Q7: Route declaration syntax across the three frameworks, side by side

### Takeaway
All three declare routes in a way that requires joining a decorator (or a list entry) to a separate registration/mount site; none of them puts method and full path on one line.

### Cited Findings
- **Django** — routes are *data*, not decorators: an ordered `urlpatterns` list of `path()`/`re_path()`/`include()` entries; HTTP method is **not** in the route at all.
  ```python
  urlpatterns = [
      path("articles/<int:year>/<int:month>/", views.month_archive),
      path("articles/<int:pk>/", views.ArticleDetailView.as_view(), name="article-detail"),
      re_path(r"^articles/(?P<year>[0-9]{4})/$", views.year_archive),
      path("community/", include("aggregator.urls")),
      path("blog/<int:year>/", views.year_archive, {"foo": "bar"}),   # extra kwargs
  ]
  ```
  Converters: `str` (default, no `/`), `int`, `slug`, `uuid`, `path` (includes `/`); custom converters are registered with `register_converter(Cls, "yyyy")` and need `regex`, `to_python`, `to_url`. `re_path` named groups `(?P<name>...)` reach the view as **strings**, not converted types; if a regex mixes named and unnamed groups, only the named groups are passed. Trailing slashes must match exactly. Function views are passed by reference; class-based views via `.as_view()`. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- **FastAPI** — method is the decorator *name*, path is its first argument, full path needs the router prefix and the `include_router` prefix (examples quoted in Q5). — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- **Flask** — `@bp.route("/<page>")` records intent; the URL is finalised by `register_blueprint(bp, url_prefix="/pages")` (examples quoted in Q6). — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)

### Inferences
- The three parameter syntaxes a tool must normalise for a slide: Django `<int:year>`, Django-regex `(?P<year>[0-9]{4})`, FastAPI/Starlette `{item_id}`, Flask/Werkzeug `<int:page>`. Flask and Django both use angle brackets with a `converter:name` form; FastAPI uses braces. Normalising all four to a single display form (`:year`) makes cross-framework slides consistent.
- Django is the odd one out in two ways that break a shared data model: (a) there is **no HTTP method** on a URL pattern — the method lives in the view (`if request.method == "POST"`, `@require_POST`, a CBV's `get`/`post` methods, or DRF's `@api_view([...])` / `ViewSet` action mapping), so a `{method, path}` record type cannot be filled from Django's URLconf alone; (b) routes are list elements, so the extractor must evaluate a list literal, including nested `include([...])`, rather than scan decorators.
- Django's view reference can be: a `Name`/`Attribute` (`views.month_archive`), a `Call` (`X.as_view()`), or a **dotted string** (`"mysite.views.custom_404"` for handlers; also `include("aggregator.urls")` as a string module path). All three forms must be resolved to link route → view.
- `include()` makes Django's routing a tree whose edges are *module path strings*. Resolving `include("polls.urls")` to `polls/urls.py` is a filesystem/package-resolution step, not a parse step.

### Gaps
- None material; all three route syntaxes are confirmed from primary docs.

## Q8: Type hints, Pydantic, dataclasses, attrs — how much structure do they give?

### Takeaway
Annotations are first-class AST data (`arg.annotation`, `FunctionDef.returns`, `AnnAssign.annotation`), so a Python analyzer gets typed signatures for free when the author wrote them — and Pydantic/dataclass/attrs classes are the cleanest "data model" signal in the language because their fields are literally annotated class-body statements.

### Cited Findings
- `arg` nodes carry `annotation` ("an expression node or `None`"); `FunctionDef`/`AsyncFunctionDef` carry `returns` (the return annotation); `AnnAssign` carries `target`, `annotation`, `value`, `simple`. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `arguments` separates `posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kw_defaults`, `kwarg`, `defaults`, where "`defaults` covers the last *n* positional arguments." — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Griffe's whole purpose is extracting "signatures for entire Python programs" statically (`griffe.visit` is marked `"analysis": "static"`; `griffe.inspect` is the dynamic alternative), and it detects signature-level breaking changes such as "a parameter's kind changing" and "a parameter's default value changing." — [Griffe docs](https://mkdocstrings.github.io/griffe/)
- FastAPI dependencies and parameters are declared through annotations — `x_token: Annotated[str, Header()]`, `token: str` — so the annotation *is* the API contract. — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)

### Inferences
- Signature rendering for a slide should be built from `arguments` structurally, not from the raw `def` line, so that `*`, `/`, `*args`, `**kwargs`, defaults and annotations are all correct even when the signature wraps across lines. `ast.unparse(node.args)` / `ast.unparse(annotation)` gives a clean one-line rendering (3.9+), with the caveat that unparse is not byte-identical to the source.
- Annotations are *expressions*, so `Optional[User]`, `list[Item] | None`, `Annotated[int, Query(ge=0)]`, and string forward references (`"User"`, and everything under `from __future__ import annotations`) all appear as syntax, not resolved types. A tool should report the annotation *text* and not claim to know the type. Parameter-kind information (positional-only vs keyword-only) is often more useful for narration than the type itself.
- Data-model detection rules that work statically:
  - **Pydantic**: `ClassDef` with a base named `BaseModel`; fields = `AnnAssign` statements in the class body, optionally with `= Field(...)` as the value. `model_config = ConfigDict(...)` (v2) or nested `class Config:` (v1) is the metadata. `@field_validator` / `@model_validator` (v2) or `@validator` / `@root_validator` (v1) mark validation logic — and the v1-vs-v2 decorator names are a usable version fingerprint.
  - **dataclasses**: `@dataclass` (bare or called with `frozen=True`, `slots=True`, `kw_only=True`) on a `ClassDef`; fields = `AnnAssign` in the body, with `field(default_factory=...)` values. `ClassVar[...]` and `InitVar[...]` annotations are *not* fields.
  - **attrs**: `@attrs.define` / `@attr.s` on a `ClassDef`; fields are either annotated (`x: int = attrs.field()`) in the modern API or `x = attr.ib()` in the old one.
  - **SQLAlchemy 2.0**: `Mapped[int] = mapped_column(...)` under a `DeclarativeBase` subclass; SQLAlchemy 1.x uses `Column(...)` assignments and `__tablename__`.
  - **TypedDict / NamedTuple / Protocol / Enum**: all are `ClassDef`s with a recognisable base and annotated bodies, and all are legitimate "data model" units for a slide.
  - **Django models** are the exception to the annotation rule: fields are plain `Assign` with `Call` values, not `AnnAssign` (see Q4).
- Practical consequence for the pipeline: a single generic "class with annotated body + known base/decorator ⇒ data model, fields = annotated assignments" extractor covers Pydantic, dataclasses, attrs, TypedDict and SQLAlchemy 2.0, and a second `Assign`-with-`Call` extractor covers Django and SQLAlchemy 1.x. Two rules cover nearly all Python data models.
- Conversely, Python has no interface/type-alias declaration syntax to mirror TS `interface`/`type`, so a TS-shaped "types" bucket should be populated from these class forms plus `TypeAlias`/`type X = ...` statements rather than left empty.

### Gaps
- I did not fetch Pydantic or dataclasses primary docs in this pass (WebFetch limit), so the Pydantic v1/v2 decorator names and `model_config` details above are uncited inference from working knowledge; the report writer should confirm against https://docs.pydantic.dev/latest/concepts/models/ and https://docs.python.org/3/library/dataclasses.html before stating them as fact.

## Q9: Existing tools that do this well

### Takeaway
`ast` is the right engine for this pipeline; Griffe is the best reference implementation of "extract a Python API surface statically"; call-graph tools exist but are explicitly heuristic and should not be trusted for narration without hedging.

### Cited Findings
- **`ast` (stdlib)**: parsing, `NodeVisitor`/`NodeTransformer`/`walk`, positions, `get_docstring`, `get_source_segment`, `unparse`, `type_comments`, `feature_version`. All of the above, quoted in Q1/Q2. — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- **Griffe**: "A Python tool and library that extracts the structure of a project, its 'signatures,' to generate API documentation or detect breaking changes" — usable as a library or CLI; the mkdocstrings Python handler uses it. Two agents: `griffe.visit` (static — parses and visits a module file) and `griffe.inspect` (dynamic inspection). Ships Google/Numpydoc/Sphinx docstring parsers plus `parse_auto`. Models `exports`, `is_exported`, `is_public`, and `ignore_private`. `griffe check` compares two versions of a package and reports e.g. an object switching from function to attribute, a parameter's kind changing, a default value changing. Its internal expressions are "basically abstract syntax trees (AST)," with differences from `ast`'s nodes, and it provides helpers to extract expressions from regular AST nodes. — [Griffe docs](https://mkdocstrings.github.io/griffe/)
- **code2flow**: generates call graphs for dynamic languages (Python, JavaScript, Ruby, PHP), outputs DOT for Graphviz. AST-based but heuristic for call resolution: it parses files into ASTs, finds function definitions, determines where they're called, and connects them; because variable types are unknown it matches calls to in-scope variables first, then falls back to a single match among all other groups and nodes. Stated limitations: it gives a "pretty good estimate" and the README says a perfect call graph for a dynamic language is not possible; functions without definitions are skipped (often because a file wasn't included); functions with identical names in different namespaces are skipped with a warning; imported functions from outside the project, including the standard library, may be linked incorrectly to local functions with the same name; anonymous/generated functions such as lambdas and factories are skipped; functions that are renamed or passed around as parameters are skipped. — [code2flow README](https://github.com/scottrogowski/code2flow)

### Inferences
- Recommendation for this pipeline: use stdlib `ast` as the extractor (zero dependencies, exact, same-process), and treat Griffe as the model to copy for the public/private and docstring-structure logic — or depend on it directly if structured per-parameter docstring parsing is wanted, since re-implementing three docstring dialects is the expensive part.
- `tree-sitter-python` is the right choice only if the pipeline later needs *one* parser across six stacks (it already has TS and Go grammars) or needs error-tolerant parsing of broken files; it costs a native dependency and gives a less semantic tree than `ast`. For a Python-hosted pipeline parsing Python, `ast` strictly dominates.
- `LibCST` is the right choice when comments and exact formatting must round-trip (codemods, or attaching trailing `#` comments to the nodes they annotate — something `ast` discards entirely). For read-only explanation, the loss of comments is the one real `ast` limitation: if the pipeline wants inline comments as narration material, it needs `tokenize` (stdlib) alongside `ast`, or LibCST.
- `pyan`, `code2flow` and similar call-graph tools should be used for *diagram candidates*, not for assertions in narration: every one of code2flow's documented limitations (same-name collisions, cross-module imports, functions passed as parameters, decorators) is common in Django/FastAPI code, where routing and DI deliberately pass functions around. A pipeline that narrates "this function calls X" off a heuristic graph will state falsehoods.
- `jedi` and `rope` do name resolution / go-to-definition with scope awareness, and are the pragmatic way to resolve `views.month_archive` → a definition across files without writing an import resolver. `pydoc` and Sphinx `autodoc` are *import-based* (they execute the module), which is wrong for an untrusted-repo pipeline — this is the main argument for static extraction over introspection, and it is the same argument Griffe makes by offering `visit` (static) alongside `inspect` (dynamic). `pdoc` likewise imports.
- Also worth naming as prior art that already solves parts of this: `pyflakes`/`ruff` (scope and unused-name analysis on AST), `mypy`/`pyright` (real type resolution, if the pipeline ever needs resolved types), `pydeps` and `importlab` (module-level import graphs, which are far more reliable than call graphs and probably sufficient for an architecture slide), and FastAPI's own `app.openapi()` (the exact, authoritative route table — available only if you're willing to import the app).

### Gaps
- I could not fetch LibCST's or tree-sitter-python's docs in this pass (WebFetch usage limit), so their claims above are uncited inference. Suggested primary sources: https://libcst.readthedocs.io/en/latest/why_libcst.html and https://github.com/tree-sitter/tree-sitter-python.
- No citation gathered for pyan's current maintenance status or accuracy claims.

## Q10: Narrative ordering that makes a Django or FastAPI codebase comprehensible

### Takeaway
For all three frameworks the comprehensible order is the same: entrypoint/config → route table → data models → handlers → cross-cutting concerns, which is "follow a request" rather than "walk the filesystem alphabetically."

### Cited Findings
- Django's own dispatch order supports the "route table first" framing: `ROOT_URLCONF` → `urlpatterns`, tested in order, first match wins, with `include()` delegating to per-app URLconfs. — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- FastAPI documents an explicit dependency execution order per request — router dependencies, then decorator `dependencies`, then normal parameter dependencies — which is a ready-made narration sequence for "what happens before your handler runs." — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Flask's deferred registration means the app is assembled in one place (factory + `register_blueprint`) and described in another (the blueprint module), so the assembly site is the natural starting point. — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)

### Inferences
- **Django video order**: `settings.py` (`INSTALLED_APPS`, `DATABASES`, `MIDDLEWARE`, `AUTH_USER_MODEL`) → root `urls.py` as the app map → for each app, `models.py` (nouns, with the FK/M2M graph as a diagram) → `urls.py` → `views.py` → `serializers.py`/`forms.py` → `admin.py` → cross-cutting (`middleware.py`, `signals.py`, custom managers, Celery tasks) → `migrations/` only as an optional schema-history appendix. Rationale: Django's vocabulary is its models, and every view is phrased in terms of them, so models must precede views.
- **FastAPI video order**: `main.py` (`FastAPI()` construction, middleware, `include_router` calls — this is the whole route map on one screen) → schemas (`models.py`/`schemas.py` Pydantic classes) → `dependencies.py`/`deps.py` (auth, DB session, pagination — the `Depends` graph is the most explanation-worthy diagram in a FastAPI app) → each router module's path operations in route order → DB layer (SQLAlchemy models, CRUD helpers) → config/settings (`BaseSettings`). Rationale: FastAPI's structure is the dependency graph, not the file tree.
- **Flask video order**: `create_app()` factory and config → extension init (`db.init_app`) → blueprint registration table → per blueprint: views grouped by URL → models → forms/schemas → request hooks and error handlers → CLI commands.
- **Per-file order** (framework-agnostic, for a single-file clip): module docstring → imports grouped as stdlib / third-party / local (the local ones are the dependency edges worth drawing) → `__all__` if present → module-level constants → data models/classes → public functions in source order → private (`_`-prefixed) helpers last. Source order should be preserved within a tier because Python files are read top-to-bottom and the author's grouping carries intent; sorting alphabetically destroys that.
- Chunking guidance specific to Python, given the existing 200/800-line rules: a `ClassDef` should be the chunk unit, not an arbitrary line window, because splitting a class body at a line boundary produces a fragment that is not valid Python and reads as nonsense. `ast` end positions make class-aligned chunking trivial. Within a large class, group methods as dunder/protocol methods, public API, and private helpers.
- Highest-value "explain this first" heuristic for a repo: rank files by (a) is it an entrypoint or config (`settings.py`, `main.py`, `app.py`, `__init__.py` of the top package, `urls.py`), (b) in-degree in the import graph, (c) number of route decorators or model classes defined. Deprioritise `migrations/`, `tests/`, `conftest.py`, and generated protobuf/`_pb2.py` files — on a real Django repo these are the majority of files and almost none of the meaning.

### Gaps
- I found no published research or primary-source guidance specifically on *narration ordering* for automated code explanation; the orderings above are reasoned from the frameworks' own documented request/dispatch order rather than cited from a source that studies comprehension.
