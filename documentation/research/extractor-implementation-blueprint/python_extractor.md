# Implementation blueprint: `src/extract/py_extractor.py` on stdlib `ast`

Scope: a code-level design an engineer can implement directly, matching the record shape the existing extractors produce. Everything below was checked against the actual repo files at `/home/claude/codeExplanation-v2` (read in full: `src/extract/common.py`, `go_extractor.py`, `ts_extractor.py`, `function_context.py`, `json_builder.py`, `extractor.py`, `reuse_pipeline.py`, `src/storage/mirror_store.py`, `src/validate/schema_check.py`, `src/chunk/chunk_splitter.py`, `src/chunk/chunker.py`, `tests/test_go_extractor.py`, `tests/test_function_context.py`) and against `ast` behaviour executed locally on CPython 3.13.18.

Verified locally (CPython 3.13.18), used throughout:

```
AsyncFunctionDef lineno 8 end_lineno 10      # decorator sits on line 7
decorator lineno [7]
ast.get_docstring(fn, clean=True) -> 'Fetch one item.'
decorator .func -> Attribute(value=Name(id='router'), attr='get'); .args[0] -> Constant('/{item_id}')
Annotated[Session, Depends(get_db)] -> Subscript(value=Name('Annotated'), slice=Tuple(elts=[Name('Session'), Call(func=Name('Depends'), args=[Name('get_db')])]))
user=Depends(current_user)          -> args.defaults[-1] = Call(func=Name('Depends'), args=[Name('current_user')])
Django: path("articles/<int:year>/", views.month_archive, name="m") -> Call(func=Name('path'), args=[Constant, Attribute], keywords=[name])
Pydantic: AnnAssign(target=name, annotation=str, value=None, simple=1); price: float = Field(default=0)
Django model field: Assign(targets=['full_name'], value=Call(models.CharField, keywords=[max_length,null]))
SQLAlchemy 2.0: AnnAssign(target=id, annotation=Mapped[int], value=mapped_column(primary_key=True))
```

## Q1. Exact node-type → record-field mapping

### Takeaway
One `ast.parse()` per file plus a single source-ordered pass over `module.body` (never `ast.walk` for ordering) fills every list the existing record carries; the mapping is mechanical, and the only node types needed are `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, `Assign`, `AnnAssign`, `Import`, `ImportFrom`, `Call`, `Raise`, `Return`, `With`/`AsyncWith`, `Try`, `Await`.

### Cited Findings
- Node fields, verbatim from the grammar table: `FunctionDef`: `name`, `args`, `body`, `decorator_list`, `returns`, `type_comment`, `type_params`; `decorator_list` is "stored outermost first". `AsyncFunctionDef` has the same fields. `ClassDef`: `name`, `bases`, `keywords`, `body`, `decorator_list`, `type_params`. `Import`: `names` (list of `alias`); `ImportFrom`: `module`, `names`, `level` (`module` is `None` for `from . import foo`, `level` 0 for absolute). `alias`: `name`, `asname`. `Call`: `func`, `args`, `keywords`. `Assign`: `targets`, `value`, `type_comment`; `AnnAssign`: `target`, `annotation`, `value`, `simple`. `arguments`: `posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kw_defaults`, `kwarg`, `defaults` — "`defaults` covers the last *n* positional arguments"; `arg`: `arg`, `annotation`, `type_comment` — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `ast.walk(node)` "Recursively yield all descendant nodes in the tree starting at *node* (including *node* itself), **in no specified order**." `ast.NodeVisitor` warns that "child nodes of nodes that have a custom visitor method won't be visited unless the visitor calls `generic_visit()`" — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `ast.parse()` "won't do any scoping checks" and raises `ValueError` if the source contains a null character — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `ast.unparse()` (3.9+) renders a node back to source, but "the produced code string will not necessarily be equal to the original code" — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- The repo's record builders are `build_frontend_chunk_record` and `build_backend_go_chunk_record` in `src/extract/json_builder.py`; the fields a record must carry are exactly the keys those two return. Required-for-schema subset is enforced in `src/validate/schema_check.py:14-18`: `chunkId, filePath, featureName, projectType, language, lineRange, frameworkOrLibrary, featureMapping, confidence, confidenceLevel` plus storage keys `contentHash, lastUpdated, pullRequest` (key must exist; `pullRequest` may be null) — repo source.

### Inferences

**Mapping table** (record key ← node type → attributes used):

| Record key (`json_builder` shape) | `ast` node | Attributes used |
|---|---|---|
| `importantFunctions[]` | `FunctionDef`, `AsyncFunctionDef` at module level **and** inside `ClassDef` (methods, name reported `Class.method`) | `name`, `args`, `returns`, `decorator_list`, `body`, `lineno`, `end_lineno` |
| `importantFunctions[].signature` | same | `ast.unparse(node.args)` + `-> ast.unparse(node.returns)`; prefix `async ` for `AsyncFunctionDef` |
| `importantFunctions[].description` | same | `ast.get_docstring(node, clean=True)` |
| `importantFunctions[].params` | `arguments`/`arg` | `posonlyargs + args + ([vararg]) + kwonlyargs + ([kwarg])`, each `arg.arg`, with `arg.annotation` text |
| `importantFunctions[].raisesError` | `Raise` inside the function's own body | presence; `exc` (`Call.func` name, e.g. `HTTPException`) for the note |
| `importantFunctions[].isAsync` | `AsyncFunctionDef`, `Await` | node type, plus any `Await` in body |
| `dataModels[]` | `ClassDef` | `name`, `bases`, `keywords`, `decorator_list`, `body` (`AnnAssign`/`Assign`), `lineno`/`end_lineno` |
| `dataModels[].fields[]` | `AnnAssign` (Pydantic/dataclass/TypedDict/SQLA 2.0) or `Assign` with `Call` value (Django/SQLA 1.x) | `target.id`/`targets[0].id`, `annotation`, `value` |
| `routes[]` | `Call` in `decorator_list` (FastAPI/Flask) or `Call` elements of the module-level `urlpatterns` `Assign`/`AnnAssign` (Django) | `func` (`Attribute.attr`/`Attribute.value`/`Name.id`), `args[0]` (`Constant.value`), `keywords` (`methods=`, `prefix=`, `url_prefix=`, `name=`) |
| `dependencies[]` | `Import`, `ImportFrom` | `alias.name`, `alias.asname`, `module`, `level` (`level >= 1` ⇒ internal relative import) |
| `frameworkOrLibrary` | `Import`/`ImportFrom` top-level module names, intersected with declared deps | `module.split(".")[0]` / `alias.name.split(".")[0]` |
| `apiCalls[]` (outbound HTTP) | `Call` | `func` as `Attribute`: `requests.get`, `httpx.AsyncClient().post`, `session.get`; `args[0]` `Constant` or `JoinedStr` |
| `sideEffects[]` | `Call` (`session.add/commit/execute`, `.save()`, `logger.*`, `open(...)`), `With`/`AsyncWith` (`open()` context manager), `Try` (error handling boundary) | `func`, `items[].context_expr`, `handlers[].type` |
| `eventHandlers[]` | — | **Empty for Python backends**, exactly as the Go builder leaves it (`json_builder.py` returns `"eventHandlers": []` for Go). Python has no DOM events; the honest analogue is routes + `Depends`, not a faked handler list. |
| `inputs[]` | `arguments` of a route handler | each `arg.arg`, `ast.unparse(arg.annotation)`, default from `defaults`/`kw_defaults`; `Query/Path/Body/Header/Cookie/Form/File` inside `Annotated` gives the *source* of the value |
| `outputs[]` | `returns` annotation + `response_model=` keyword on the route decorator | `ast.unparse(node.returns)`, decorator keyword value text |
| `fileDescription` | `Module` | `ast.get_docstring(tree, clean=True)` |
| `lineRange` | file | `[1, len(lines)]` — same as both existing builders |

**Traversal skeleton** (explicit, source-ordered, nesting-aware — not `ast.walk`):

```python
def _collect(tree: ast.Module) -> tuple[list[ast.AST], list[ast.ClassDef]]:
    """Module-body order is narrative order (PEP 8 reading order).
    Methods are collected with their owning class so names stay qualified."""
    funcs, classes = [], []
    for node in tree.body:                      # source order, guaranteed
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((None, node))
        elif isinstance(node, ast.ClassDef):
            classes.append(node)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.append((node.name, sub))
    return funcs, classes
```

Nested closures (`def` inside `def`) are reached by a second, explicitly recursive pass only when the outer function is a decorator factory; otherwise they are deliberately left out of `importantFunctions` and noted (`"closure defined inside <outer>; not listed separately"`). `ast.walk` is used **only** for within-body predicate scans (`Raise`, `Await`, `Call`), where order does not matter.

**Body scans are scoped to the owning function.** The existing `function_context.build_function_context` scopes `apiCalls`/`sideEffects` by line number (`in_range(line)`), so `py_extractor` must emit every API call and side effect with a `line`, same as `ts.ExtractedApiCall`/`ExtractedSideEffect` and Go's `(kind, line)` tuples — `function_context` already normalises both shapes (`function_context.py`, `normalised_effects`).

### Gaps
- `ast` discards comments entirely; inline `#` comments are unavailable without `tokenize` or LibCST. Not needed for this blueprint (Python documentation lives in docstrings) but it means a Python record's `description` is `None` for an undocumented function and must stay `None`, never back-filled from a nearby comment.

## Q2. Line ranges: the decorator trap, Optional `end_lineno`, and the `trim_snippet` contract

### Takeaway
Use `min(d.lineno for d in node.decorator_list)` as the start line whenever `decorator_list` is non-empty, treat `end_lineno` as `Optional[int]` with an explicit fallback, and then call the existing `trim_snippet(lines, start, end)` unchanged — it already does the 120-line cap, the continuation note, and the `redact_secrets` choke point.

### Cited Findings
- "The `lineno` and `end_lineno` are the first and last line numbers of source text span (1-indexed so the first line is line 1)" — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- "Note that the end positions are not required by the compiler and are therefore optional"; their grammar type is `int?`, so they can be `None` — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- `end_lineno`/`end_col_offset` were added in Python 3.8 (bpo-33416) — [What's New in Python 3.8](https://docs.python.org/3/whatsnew/3.8.html)
- `ast.get_source_segment(source, node, *, padded=False)` "If some location information (`lineno`, `end_lineno`, `col_offset`, or `end_col_offset`) is missing, return `None`" — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Locally verified: for a function decorated with `@router.get(...)` on line 7, `node.lineno == 8` and `decorator_list[0].lineno == 7` — so a naive `node.lineno` clip loses the route line.
- `trim_snippet(lines, start_line, end_line, max_lines=120)` takes a 1-indexed inclusive slice, returns `CodeSnippet(text, truncated, continuation_note, secrets_redacted)`, and runs `redact_secrets()` on every snippet — `src/extract/common.py`.
- Both existing builders carry `codeSnippet`, `truncated`, `continuationNote`, `secretsRedacted` per function and per data model — `src/extract/json_builder.py`.

### Inferences

The exact expression, as a single helper every extraction path goes through:

```python
def node_line_range(node: ast.AST, total_lines: int) -> tuple[int, int, bool, str | None]:
    """1-indexed inclusive [start, end] for a definition, decorators included.

    Returns (start, end, assumed, note).

    Two traps are encoded here rather than at each call site:

    1. For a decorated def, `node.lineno` points at the `def` keyword, not
       at the first decorator (verified: decorator on line 7, def on line 8).
       Starting the clip at `node.lineno` cuts off `@router.get("/items")` —
       the one line that says what the function is.
    2. `end_lineno` is typed `int?` in the grammar and may be None (hand-built
       or synthesized nodes). Falling back to `start` would silently report a
       one-line function; falling back to EOF would over-claim. We fall back to
       EOF and mark the range assumed with a note saying what to verify.
    """
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min(start, min(d.lineno for d in decorators))

    end = getattr(node, "end_lineno", None)
    if end is None:
        return start, total_lines, True, (
            "End line unavailable from the parser for this definition (ast end "
            "positions are optional); the range runs to end of file. Verify the "
            "real extent before relying on this snippet."
        )
    return start, max(start, end), False, None
```

- `end_lineno` ends at the last token of the body: trailing blank lines and trailing comments after a function are excluded, so two adjacent definitions' ranges are **not** contiguous — never assume `next.lineno == prev.end_lineno + 1`. Decorator-inclusive start lines also mean ranges of adjacent decorated functions can be tight with no gap; de-duplicate by `(start, end)` as `ts_extractor.extract_functions` already does with `seen_spans`.
- Snippet production is then identical to the existing extractors, which is what keeps the record shape byte-compatible:

```python
start, end, range_assumed, range_note = node_line_range(node, len(lines))
snippet = trim_snippet(lines, start, end)          # unchanged contract
```

- Do **not** use `ast.get_source_segment`: it returns a column-sliced string, and column-based slicing of an indented Python block produces a syntactically invalid fragment (and it drops decorators unless `padded=True`, which still does not include them). `trim_snippet` over whole lines is both the correct unit for Python and the only unit that keeps the snippet pipeline (redaction, continuation notes) intact.
- Docstring-aware variant for narration: when `node.body[0]` is an `Expr(Constant(str))`, `body_start = node.body[1].lineno` if a second statement exists. Emit this as an extra field (`bodyStartLine`) rather than changing `lineRange`, so the slide can show the whole definition while the narration does not re-read the docstring the slide already displays. This is additive and does not break any consumer.

### Gaps
- `end_lineno` is documented as optional but I found no doc statement enumerating which real-world parses produce `None` for a `FunctionDef` from `ast.parse()` (in practice `ast.parse` always sets it on 3.8+). The fallback above is defensive, not a response to an observed case.

## Q3. Docstrings: `ast.get_docstring` vs the upward comment scan in `function_context.py`

### Takeaway
`py_extractor` should supply `description` directly from `ast.get_docstring(node, clean=True)` and `function_context.build_function_context` should take an optional `description`/`description_source` override rather than growing a Python branch — the upward `//`-scan is not merely wrong on Python, it is *actively misleading*, and a language branch inside `function_context` would have to re-parse the file to do the right thing.

### Cited Findings
- "Return the docstring of the given *node* (which must be a `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, or `Module` node), or `None` if it has no docstring. If *clean* is true, clean up the docstring's indentation with `inspect.cleandoc()`." "Changed in version 3.5: `AsyncFunctionDef` is now supported." — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- PEP 8: module-level dunder names "should be placed after the module docstring but before any import statements" — i.e. the module docstring is positionally first — [PEP 8](https://peps.python.org/pep-0008/)
- The repo's `leading_doc_comment(lines, start_line)` recognises only a block ending `*/` or a run of lines starting `//`, and returns `None` for anything else; `file_header_comment(lines)` requires the file to open with `/*` or `//` — `src/extract/function_context.py`. On a Python file both return `None` for every definition, including fully documented ones.
- `build_function_context` is the single place both builders call for per-function facts, and it hardcodes `"description": leading_doc_comment(lines, start)` and `"descriptionSource": "doc-comment" if ... else None` — `src/extract/function_context.py`.
- Griffe ships Google, Numpydoc and Sphinx docstring parsers plus `griffe.parse_auto` for style detection — [Griffe docs](https://mkdocstrings.github.io/griffe/)

### Inferences

**Recommendation: supply it from `py_extractor`, via a narrow optional parameter on `build_function_context`.** Rationale, in order of weight:

1. The right answer needs the *node*, not the lines. `function_context` receives `lines`, `name`, `signature`, `line_range` — no AST. A language branch there would have to re-parse the file (a second `ast.parse` per function, or a cache keyed on file content), duplicating work `py_extractor` has already done. Passing the value in costs one parameter.
2. A Python comment block above a `def` is usually a section marker or TODO, not documentation. If `function_context` grew a `language == "python"` branch that still fell back to the upward scan when no docstring was found, it would report those as documentation — a confidently stated falsehood in spoken narration. Supplying the value from the extractor makes "no docstring" mean `description: None`, which is what the project's honesty stance requires.
3. `descriptionSource` becomes meaningful: `"docstring"` for Python, `"doc-comment"` for TS/Go. Narration can then legitimately say "the author's own description" for both, and a reader of the JSON can tell which mechanism produced it.

Minimal change to `function_context.py` (backwards compatible — both existing callers keep working unchanged):

```python
def build_function_context(
    name, signature, line_range, lines, all_functions, language,
    api_calls=None, side_effects=None,
    description: str | None = None,            # NEW
    description_source: str | None = None,     # NEW
    exported: bool | None = None,              # NEW — see Q4
    visibility: str | None = None,             # NEW — see Q4
    is_async: bool | None = None,              # NEW — AsyncFunctionDef is a node type, not a keyword scan
) -> dict:
    ...
    if description is None and description_source is None:
        description = leading_doc_comment(lines, start)       # TS/Go path, unchanged
        description_source = "doc-comment" if description else None
    ...
    "exported": is_exported(signature, name, language) if exported is None else exported,
    "visibility": visibility,
    "isAsync": (bool(_AWAIT_RE.search(body)) or "async" in signature) if is_async is None else is_async,
```

Note the existing code calls `leading_doc_comment` **twice** per function (once for `description`, once for `descriptionSource`); the guard above also removes that duplicate call.

`py_extractor` side:

```python
doc = ast.get_docstring(node, clean=True)      # None for an f-string or absent docstring
```

- `ast.get_docstring` is documented only for `Module`, `ClassDef`, `FunctionDef`, `AsyncFunctionDef` — do not call it on anything else. Module docstring feeds `fileDescription` (replacing `file_header_comment(lines)`, which returns `None` on Python); class docstring feeds a `description` on the `dataModels[]` entry (a new, additive field — the TS/Go model entries have no description today).
- An f-string docstring, a concatenated-literal docstring, or `__doc__ = ...` assignment all yield `None`. Treat `None` as undocumented and fall back to the signature; do not attempt recovery.
- Run the docstring through `redact_secrets()` before it enters the record, exactly as `leading_doc_comment` does — a docstring can carry a credential and would be spoken aloud as well as written. This is a hard requirement, not a nicety; the module docstring of a config file is a realistic place for a sample connection string.
- Structured per-parameter docstring parsing (Google `Args:` / Numpydoc / Sphinx `:param x:`) is explicitly **out of scope** for v1. Store the cleaned raw text. If per-parameter narration is wanted later, delegate to Griffe's `parse_auto` rather than regexing three dialects.

### Gaps
- No primary source consulted on how Sphinx autodoc / pdoc recover *attribute* docstrings (the string literal following an `AnnAssign`). v1 does not extract them; if wanted, the implementation is "an `Expr(Constant(str))` statement immediately following an `AnnAssign`/`Assign` in a class body", which is inference, not a cited behaviour.

## Q4. Visibility: a tri-state against a schema with a boolean `exported`

### Takeaway
Keep `exported` as a boolean (so every existing consumer and the schema check keep working) and add one sibling field `visibility` with three values `declared_in_all | public_by_convention | private_by_underscore` plus `visibilitySource`; that is the minimal schema change, it is purely additive, and it is gated by bumping `EXTRACTOR_VERSION` from 4 to 5 in `src/storage/mirror_store.py`.

### Cited Findings
- PEP 8: "modules should explicitly declare the names in their public API using the `__all__` attribute"; an empty `__all__` means the module "has no public API"; "Even with `__all__` set appropriately, internal interfaces" should still be "prefixed with a single leading underscore"; "An interface is also considered internal if any containing namespace (package, module or class) is considered internal"; "Imported names should always be considered an implementation detail"; "Documented interfaces are considered public" and "All undocumented interfaces should be assumed to be internal" — [PEP 8](https://peps.python.org/pep-0008/)
- `_single_leading_underscore` is a "weak 'internal use' indicator" — [PEP 8](https://peps.python.org/pep-0008/)
- Griffe models this distinction explicitly with `is_exported` / `is_public` methods, an `exports` list in its serialized model, and an `ignore_private` parameter — [Griffe docs](https://mkdocstrings.github.io/griffe/)
- The repo's `is_exported(signature, name, language)` returns `name[0].isupper()` for `"go"` and otherwise `signature.lstrip().startswith("export")` — so on Python it returns `False` for **every** definition — `src/extract/function_context.py`.
- `EXTRACTOR_VERSION = 4` in `src/storage/mirror_store.py`; `needs_reanalysis` returns stale when `stored.get("extractorVersion", 1) != EXTRACTOR_VERSION`, and the file carries a documented version history (1: contentHash-only; 2: handler lineRange; 3: function context; 4: file header comment) — repo source.
- Go's "capital letter = exported" rule is inverted in Python, where CapWords names are *classes* by PEP 8 convention and say nothing about visibility — [PEP 8](https://peps.python.org/pep-0008/)

### Inferences

`__all__` extraction, handling the forms that actually occur:

```python
def module_exports(tree: ast.Module) -> tuple[set[str] | None, bool, str | None]:
    """The module's declared public API.

    Returns (names, assumed, note). `names is None` means the module declares
    no __all__ at all (different from an empty __all__, which PEP 8 says means
    "no public API"). `assumed=True` means an __all__ exists but could not be
    read literally — computed, concatenated, or extended at runtime — in which
    case the caller must NOT report a name as private merely for being absent
    from a list we could not read.
    """
    names: set[str] | None = None
    assumed = False
    note = None

    for node in tree.body:
        target_names = []
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]          # __all__: list[str] = [...]
            value = node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            # __all__ += submodule.__all__  — a real pattern in package __init__.py
            if node.target.id == "__all__":
                assumed = True
                note = ("__all__ is extended with += at module level, so the declared "
                        "public API is not fully readable from this file alone; names "
                        "absent from the literal part are not necessarily private.")
            continue
        else:
            continue

        if "__all__" not in target_names or value is None:
            continue

        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            literal, non_literal = set(), False
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    literal.add(elt.value)
                else:
                    non_literal = True            # a Starred, a Name, an f-string
            names = literal if names is None else names | literal
            if non_literal:
                assumed = True
                note = ("__all__ contains entries that are not string literals; the "
                        "public API list is incomplete as read.")
        else:
            # __all__ = other_module.__all__, a comprehension, a call result
            assumed = True
            note = ("__all__ is computed rather than a literal list, so this file's "
                    "declared public API could not be read statically.")
    return names, assumed, note
```

Classification, in PEP 8's priority order:

```python
PROTOCOL = "protocol_method"        # dunder: public behaviour, not private

def classify_visibility(name, exports, exports_assumed, file_path, in_class):
    """(visibility, exported, source, assumed, note)."""
    bare = name.rsplit(".", 1)[-1]

    # PEP 8's containing-namespace rule: internality is inherited.
    private_package = any(
        part.startswith("_") and part != "__init__.py"
        for part in Path(file_path).parts
    )

    if bare.startswith("__") and bare.endswith("__"):
        return PROTOCOL, True, "dunder", False, None
    if in_class and bare.startswith("__"):
        return "private_by_underscore", False, "name_mangling", False, None

    if exports is not None:
        inside = bare in exports
        if inside:
            return "declared_in_all", True, "__all__", False, None
        if exports_assumed:
            return ("public_by_convention" if not bare.startswith("_") else "private_by_underscore",
                    not bare.startswith("_"), "convention_with_unreadable_all", True,
                    "This module declares __all__ but it could not be read in full, so "
                    "visibility falls back to the underscore convention. Verify against __all__.")
        return "private_by_underscore", False, "__all__", False, (
            "Not listed in this module's __all__, which PEP 8 treats as the declaration "
            "of the public API, so it is reported internal despite having no underscore.")

    if bare.startswith("_"):
        return "private_by_underscore", False, "convention", False, None
    if private_package:
        return "private_by_underscore", False, "containing_namespace", False, (
            "Public by name, but an enclosing package component starts with an "
            "underscore; PEP 8 treats anything inside an internal namespace as internal.")
    return "public_by_convention", True, "convention", False, None
```

**Why boolean `exported` stays.** The schema check does not look at `exported` at all (`schema_check.py` checks only the ten core fields plus three storage keys), but the narration layer and both existing builders consume `build_function_context`'s dict, and `exported` is already in it for TS and Go. Changing its type to a string would break Python *and* TS/Go consumers for no gain. Adding `visibility` alongside it is purely additive: existing readers ignore the new key, and a Python-aware narrator can say "this module's public API is the three names in `__all__`" — a genuinely useful opening sentence that is only available when `__all__` exists.

**Mapping tri-state → boolean**, so the two fields never disagree: `declared_in_all` and `public_by_convention` and `protocol_method` ⇒ `exported: True`; `private_by_underscore` ⇒ `exported: False`.

**Migration.** Three steps, all in one commit:

1. In `src/extract/function_context.py`, add the optional `exported` / `visibility` parameters (Q3 snippet). TS and Go pass neither and keep `is_exported(...)` behaviour byte-for-byte.
2. Add a `"visibility": None` default to the context dict so TS/Go records carry the key with an honest null (`None` = "this language has no visibility declaration we model"), rather than Python records having a key the others lack. Narration must treat `None` as "not modelled", never as private.
3. Bump `EXTRACTOR_VERSION` to `5` in `src/storage/mirror_store.py` with the history line `5 - python extractor on stdlib ast; records carry visibility provenance and Python docstring descriptions.` `needs_reanalysis` then returns stale for every stored record, so every chunk is re-extracted once and the new fields reach stores whose source files never changed. Without the bump, the improvement silently does nothing — which is the exact failure the file's own docstring says the version gate exists to prevent.

Note there is **no** migration of stored JSON needed: the gate forces regeneration rather than rewriting files in place, and `write_stored` overwrites.

**Imported names are not exports.** PEP 8 is explicit that imported names are implementation details, so `Import`/`ImportFrom` aliases go to `dependencies[]`, never to `importantFunctions[]` or the public surface — with one exception worth special-casing: in a package `__init__.py`, `from .thing import Thing` plus `__all__` *is* the public façade. Implement as: if `Path(file_path).name == "__init__.py"` and the name appears in `__all__`, emit a `reExports[]` entry (additive) with the originating module, and do not claim the symbol is defined here.

### Gaps
- Griffe's exact `is_public` algorithm (how it weighs `__all__` vs underscores vs re-export aliasing) is not spelled out on the fetched page, so the ordering above is derived from PEP 8 directly, not copied from Griffe.
- PEP 8's "documented interfaces are considered public" is *not* implemented above: using "has a docstring" as a visibility signal would make an undocumented public helper look internal, which is a worse error than the underscore rule. Noted as a deliberate deviation from PEP 8's letter.

## Q5. Routes: FastAPI, Flask, Django — concrete `ast` patterns

### Takeaway
All three need the same two-stage shape the Go extractor already has (resolve prefixes from assignments and registration calls, then join them onto each registration site), and in all three the prefix can be non-literal — in which case emit the local path with `assumed: True` and a note naming exactly which prefix could not be resolved.

### Cited Findings
- FastAPI: `APIRouter` is "a 'mini `FastAPI`' class"; the router variable "can be named anything"; routers take `prefix="/items"` (which "must not end with `/`"), `tags`, `dependencies`, `responses`; `app.include_router(admin.router, prefix="/admin", ...)` applies the same parameters at inclusion time and "only in the including app"; the same router can be included under two prefixes (`/api/v1`, `/api/latest`); routers nest via `router.include_router(other_router)` — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- FastAPI dependency execution order is documented as (1) router dependencies, (2) decorator `dependencies`, (3) normal parameter dependencies — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- Flask: a `Blueprint` "works similarly to a `Flask` application object, but it is not actually an application"; a route decorator on a blueprint means "the blueprint will record the intention of registering the function `show` on the application when it's later registered"; `app.register_blueprint(simple_page, url_prefix='/pages')` yields `/pages/<page>`; the blueprint name affects only the endpoint, not the URL; stacked decorators are legal (`@simple_page.route('/', defaults={'page': 'index'})` above `@simple_page.route('/<page>')`); nesting via `parent.register_blueprint(child)` combines URL prefixes — [Flask Blueprints docs](https://flask.palletsprojects.com/en/stable/blueprints/)
- Django: the root URLconf comes from `ROOT_URLCONF`, then Django "looks for a `urlpatterns` list"; patterns are tested in order and the first match wins; `include()` delegates the remainder of the URL to another URLconf and also accepts an inline list; `app_name` sets the application namespace; `handler400/403/404/500` are module-level assignments valid only in the root URLconf; converters are `str, int, slug, uuid, path`; `re_path` named groups reach the view as strings; function views are passed by reference and class-based views via `.as_view()` — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/)
- There is **no HTTP method on a Django URL pattern**; the method lives in the view — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/) (and the repo's own validation doc reaches the same conclusion, `documentation/14-stack-support-validation.md`)
- Verified locally: `path("articles/<int:year>/", views.month_archive, name="m")` parses to `Call(func=Name('path'), args=[Constant, Attribute], keywords=[keyword(arg='name')])`; `include("aggregator.urls")` is a nested `Call` in `args[1]`.
- The existing `ExtractedRoute` dataclass is `method, path, handler, static_or_dynamic, routing_library, protected, assumed, note`, and the record shape is `{path, method, type, routingLibrary, protected, assumed, handler, notes}` — `src/extract/go_extractor.py`, `src/extract/json_builder.py`.

### Inferences

Reuse the existing dataclass verbatim (`from .go_extractor import ExtractedRoute` would couple the modules; better to move `ExtractedRoute` into `common.py` and import it from both — a two-line refactor that keeps one definition of the record shape). `routing_library` takes `"fastapi" | "flask" | "django"`.

**Shared prefix model.** Mirror `_resolve_group_prefix`'s design: a dict of `var -> (parent, own_prefix)` plus a set of roots, walked to the root, with a `fully_resolved` flag.

```python
HTTP_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options", "trace",
                   "api_route", "websocket", "route"}

def _literal_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None
```

**FastAPI.**

```python
def _fastapi_router_vars(tree: ast.Module) -> dict[str, tuple[str | None, bool, str | None]]:
    """var -> (own prefix, prefix_assumed, assumed_note) for `x = APIRouter(...)`
    and `x = FastAPI(...)`. The docs say the variable can be named anything, so
    this is resolved by the CALL, never by assuming the name is `app`/`router`."""
    out = {}
    for node in ast.walk(tree):                     # order irrelevant here
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        callee = node.value.func
        fname = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)
        if fname not in {"APIRouter", "FastAPI"}:
            continue
        prefix_node = _kw(node.value, "prefix")
        if prefix_node is None:
            prefix, assumed, note = "", False, None
        else:
            literal = _literal_str(prefix_node)
            if literal is None:
                prefix, assumed = "", True
                note = (f"This router's prefix= is the expression "
                        f"`{ast.unparse(prefix_node)}`, not a string literal, so the "
                        f"full path could not be composed. Verify the resolved prefix.")
            else:
                prefix, assumed, note = literal.rstrip("/"), False, None
        for t in node.targets:
            if isinstance(t, ast.Name):
                out[t.id] = (prefix, assumed, note)
    return out

def extract_fastapi_routes(tree, router_vars, mount_prefixes):
    """mount_prefixes: {router var or dotted ref -> [(prefix, assumed, note), ...]}
    from include_router calls, possibly collected across files (one router can be
    included under two prefixes, which legitimately gives one function two paths)."""
    routes = []
    for owner, fn in _collect(tree)[0]:
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        for dec in fn.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            attr = dec.func.attr
            if attr not in HTTP_DECORATORS or not isinstance(dec.func.value, ast.Name):
                continue
            var = dec.func.value.id
            if var not in router_vars:
                continue                      # not a router we can see: handled below
            local = _literal_str(dec.args[0]) if dec.args else None
            notes, assumed = [], False
            if local is None:
                local, assumed = "", True
                notes.append("The path argument is not a string literal; "
                             "the local path could not be read.")
            own_prefix, pre_assumed, pre_note = router_vars[var]
            if pre_note:
                notes.append(pre_note)
            assumed = assumed or pre_assumed
            method = ("WEBSOCKET" if attr == "websocket"
                      else ",".join(m.upper() for m in _api_route_methods(dec)) if attr == "api_route"
                      else attr.upper())
            for mount, mount_assumed, mount_note in mount_prefixes.get(var, [("", True, None)]):
                if mount_note:
                    notes.append(mount_note)
                routes.append(ExtractedRoute(
                    method=method,
                    path=(mount.rstrip("/") + own_prefix + local) or "/",
                    handler=f"{owner + '.' if owner else ''}{fn.name}",
                    static_or_dynamic="dynamic" if "{" in local else "static",
                    routing_library="fastapi",
                    protected=_has_auth_dependency(dec, router_vars_deps, fn),
                    assumed=True,         # always, same stance as the Go extractor
                    note=" ".join(notes) or None,
                ))
    return routes
```

- `@app.api_route("/x", methods=["GET", "POST"])` carries its methods in a keyword; read `_kw(dec, "methods")` as a `List` of `Constant` strings, else mark assumed.
- `include_router` collection: find every `Call` whose `func` is an `Attribute` with `attr == "include_router"`. `args[0]` is the router reference — a `Name` (`router`) or an `Attribute` (`users.router`); key on `ast.unparse(args[0])` so `users.router` and a bare `router` both work. `prefix=` keyword gives the mount; non-literal ⇒ `("", True, note)`. Nested `router.include_router(other)` composes by walking the same map, as `_resolve_group_prefix` does.
- **Cross-file**: `include_router` calls normally live in `main.py` while the decorators live in `app/routers/*.py`. A per-chunk extractor only sees one file, so the mount prefix must be passed in by the orchestrator. Design: `extract_repo`/`run_reuse_pipeline` do a cheap pre-pass that parses every `.py` file under the Python marker directories, collects `{router_ref: [(prefix, assumed, note)]}` and `{var: own_prefix}`, and passes the merged map to `build_backend_python_chunk_record` — exactly how `module_path`/`uses_fiber` and `base_url` are resolved up front today in `extractor.py:extract_repo`. Where a file's router is never found in any `include_router` call, emit the router-local path with `assumed=True` and the note "This router was not found in any `include_router(...)` call in the files scanned, so the mount prefix is unknown and the path shown is router-local."
- Also recognise, as side effects / app wiring rather than routes: `@app.middleware("http")`, `@app.exception_handler(ExcType)`, `@app.on_event("startup")`, `lifespan=`, `app.mount("/static", StaticFiles(...))`, `app.add_middleware(CORSMiddleware, ...)`.

**Flask.**

```python
def _flask_blueprint_vars(tree):
    """var -> declared name, plus `app = Flask(__name__)` roots.
    Blueprint(..., url_prefix=...) can carry a prefix at construction too."""
    bps, roots = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fname = getattr(node.value.func, "id", None) or getattr(node.value.func, "attr", None)
            for t in node.targets:
                if not isinstance(t, ast.Name):
                    continue
                if fname == "Blueprint":
                    pre = _kw(node.value, "url_prefix")
                    bps[t.id] = (_literal_str(pre) if pre is not None else "", pre is not None and _literal_str(pre) is None)
                elif fname == "Flask":
                    roots.add(t.id)
    return bps, roots
```

- Route sites: `decorator_list` entries that are `Call` with `func = Attribute(value=Name(var), attr="route")` where `var` is a blueprint or a Flask app. `args[0]` is the rule; methods come from `_kw(dec, "methods")` as a `List` of `Constant` strings, **defaulting to `["GET"]` when absent** (Flask's documented default) — this is the opposite of FastAPI, where the method is the decorator name.
- **Stacked decorators are normal and mean several URL rules for one function.** Emit one `ExtractedRoute` per `@route` decorator, not one per function. A "one route per function" data model is wrong for Flask; the existing `routes[]` list already allows many entries per record, so no schema change is needed.
- `url_prefix` composition: scan for `Call` with `attr == "register_blueprint"`; `args[0]` is the blueprint ref, `url_prefix=` keyword is the mount. Nesting (`parent.register_blueprint(child)`) composes. Non-literal ⇒ assumed with a note naming the expression.
- Two shapes a decorator-only scan misses, both of which must be emitted rather than dropped: `app.add_url_rule("/x", "endpoint", view_func)` — a `Call` with `attr == "add_url_rule"`, path from `args[0]`, handler from `args[2]` or `view_func=`; and `MethodView` subclasses registered with `SomeView.as_view("name")`, where the HTTP methods are the class's `get`/`post`/… method names. For `MethodView`, emit one route per HTTP-named method with `assumed=True` and the note "Methods inferred from the MethodView subclass's method names; the URL rule is applied at `add_url_rule`/`as_view` registration time."
- **`app` often does not exist at module scope** in a well-structured Flask project (the `create_app()` factory defers it). So: never anchor on a module-level `app = Flask(`; also scan inside `FunctionDef` bodies whose name is `create_app` or which return a `Flask(...)`-assigned name. If a file has blueprints and no visible registration anywhere in the scanned set, that is the "router-local path" note again.

**Django.**

```python
DJANGO_ROUTE_FUNCS = {"path", "re_path", "url"}

def extract_django_routes(tree, lines):
    routes, prefix = [], ""        # prefix is non-empty only for include([...]) inline lists
    for node in tree.body:
        targets = ([t.id for t in node.targets if isinstance(t, ast.Name)]
                   if isinstance(node, ast.Assign)
                   else [node.target.id] if isinstance(node, ast.AnnAssign)
                        and isinstance(node.target, ast.Name) else [])
        if "urlpatterns" not in targets:
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            routes.append(_unreadable_urlpatterns(node))     # built by a loop/comprehension
            continue
        for elt in value.elts:                                # ORDER MATTERS: first match wins
            if not isinstance(elt, ast.Call):
                continue
            fname = getattr(elt.func, "id", None) or getattr(elt.func, "attr", None)
            if fname not in DJANGO_ROUTE_FUNCS or not elt.args:
                continue
            route = _literal_str(elt.args[0])
            target = elt.args[1] if len(elt.args) > 1 else None
            if target is not None and isinstance(target, ast.Call) and \
               (getattr(target.func, "id", None) or getattr(target.func, "attr", None)) == "include":
                included = _literal_str(target.args[0]) if target.args else None
                routes.append(ExtractedRoute(
                    method="UNKNOWN", path="/" + (route or ""),
                    handler=f"include({included!r})" if included else "include(<list>)",
                    static_or_dynamic="static", routing_library="django",
                    protected=False, assumed=True,
                    note=("This entry delegates the rest of the URL to another URLconf via "
                          "include(); the sub-paths live in that module and were not joined "
                          f"here. Resolve {included!r} as a package path to continue."
                          if included else
                          "This entry includes an inline pattern list; nested paths are "
                          "listed separately and must be read with this prefix."),
                ))
                continue
            handler = (ast.unparse(target) if target is not None else "<missing>")
            notes = ["Django URL patterns carry no HTTP method; the method lives in the view "
                     "(request.method, @require_POST, a CBV's get/post, or DRF's @api_view). "
                     "Reported as UNKNOWN rather than guessed."]
            if route is None:
                notes.append("The route argument is not a string literal, so the path "
                             "could not be read.")
            routes.append(ExtractedRoute(
                method="UNKNOWN", path="/" + (route or ""), handler=handler,
                static_or_dynamic="dynamic" if (route and ("<" in route or "(?P<" in route)) else "static",
                routing_library="django", protected=False, assumed=True,
                note=" ".join(notes),
            ))
    return routes
```

- `method="UNKNOWN"` is the honest value and is why Django needs a second pass on the view to say anything about methods: `@require_POST`/`@require_http_methods([...])`, `@api_view(["GET","POST"])`, a CBV's `get`/`post`/`put` method names, or a `ModelViewSet`. Emit those as a `methodsFromView` note on the route when the view is in the same chunk; otherwise leave UNKNOWN and say so. **Never** infer a method from the URL shape.
- Parameter normalisation for slides: Django `<int:year>`, Django-regex `(?P<year>[0-9]{4})`, FastAPI/Starlette `{item_id}`, Flask/Werkzeug `<int:page>`. Normalise all four to a single display form (`:year`) in a `displayPath` field, keeping the verbatim `path` as read from source.
- `app_name = "polls"` (module-level `Assign`) and `namespace=` on `include()` feed a `namespace` note, not the path. `handler400/403/404/500` module-level assignments are root-URLconf-only error handlers — emit as routes with `method="ERROR_HANDLER"` or as side-effect-style wiring entries, never as normal paths.
- `migrations/` must be excluded before parsing (highest line count, lowest explanatory value in a Django repo). That belongs in the chunker's ignore list, not here, but the extractor should also short-circuit on a path containing `/migrations/` and emit a one-line note.

**Protection.** Copy the Go extractor's narrow stance exactly: never scan the whole file for "auth". For FastAPI, `protected=True` only when a `Depends(...)` on the decorator's `dependencies=` list, the router's `dependencies=`, or a parameter's `Depends` names a function whose name matches `auth|token|current_user|permission|security` — and `assumed=True` always, with a note saying it is name-based and file-local. For Flask, only a decorator named `login_required`/`jwt_required`/`requires_auth` on the same function. For Django, only `@login_required`/`@permission_required`/`permission_classes` on the view. The Go module's own docstring records a real false positive from a whole-file substring match; do not repeat it.

### Gaps
- `response_model` semantics are not covered by the FastAPI page cited (it appears only as a navigation link there); if the record is to explain `response_model`, cite the dedicated FastAPI response-model tutorial.
- Django's dotted-string view references (`handler404 = "mysite.views.custom_404"`) are documented as valid, but I found no doc statement on how documentation tools resolve them; v1 should emit the string verbatim with `assumed=True`.

## Q6. Data models: Pydantic, dataclass, SQLAlchemy, Django, TypedDict, NamedTuple

### Takeaway
Two rules cover nearly every Python data model: "`ClassDef` with a known base or decorator ⇒ fields are the `AnnAssign` statements in its body" (Pydantic, dataclass, attrs, TypedDict, NamedTuple, SQLAlchemy 2.0) and "fields are `Assign` statements whose value is a `Call`" (Django models, SQLAlchemy 1.x) — and both map onto the existing `ExtractedDataModel`/`ExtractedField` shape unchanged.

### Cited Findings
- `AnnAssign` carries `target`, `annotation`, `value`, `simple` (`simple` is 1 only for a bare, unparenthesized name); `ClassDef` carries `bases`, `keywords`, `decorator_list`, `body` — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Django: a model is a `ClassDef` whose bases include `models.Model`; fields are class-body `Assign` statements whose `value` is a `Call` to `models.<X>Field`; relations (`ForeignKey`, `OneToOneField`, `ManyToManyField`) take a target that may be a `Name`, an `Attribute`, **or a string** like `"app.Model"` for lazy references — [Django URL dispatcher docs](https://docs.djangoproject.com/en/5.2/topics/http/urls/) for the URLconf parts; the model-shape detail is inference recorded in the prior research round (`documentation/research/pipeline-support-across-six-stacks/python.md`, Q4/Q8)
- Verified locally: `class Alumni(models.Model): full_name = models.CharField(max_length=120, null=True)` ⇒ `bases=['models.Model']`, body `Assign(targets=['full_name'], value=Call)`; `class Item(BaseModel): name: str; price: float = Field(default=0)` ⇒ `AnnAssign(simple=1)` with `value=None` and `value=Field(default=0)`; `@dataclass(frozen=True)` appears in `decorator_list` as `dataclass(frozen=True)`; `class User(Base): id: Mapped[int] = mapped_column(primary_key=True)` ⇒ `AnnAssign(annotation='Mapped[int]', value='mapped_column(primary_key=True)')`.
- The existing shape is `ExtractedField(name, type, description)` and `ExtractedDataModel(name, fields, line_range, snippet)`, serialised as `{name, fields:[{name,type}], file, codeSnippet, truncated, continuationNote, secretsRedacted}` — `src/extract/ts_extractor.py`, `src/extract/json_builder.py`.

### Inferences

Detection, by base name and decorator name only (never by import resolution — a project base class named `Base` is indistinguishable from SQLAlchemy's without it, which is why the kind carries `assumed`):

```python
def classify_model(cls: ast.ClassDef) -> tuple[str | None, bool, str | None]:
    """(kind, assumed, note). Matching is on the LAST dotted segment of each
    base and each decorator, so `models.Model`, `django.db.models.Model` and a
    re-exported `Model` all match."""
    bases = {(b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", None)) for b in cls.bases}
    # Subscripted bases: class X(Generic[T]) / class X(BaseModel, Generic[T])
    bases |= {_base_name(b.value) for b in cls.bases if isinstance(b, ast.Subscript)}
    decs = {(d.func.attr if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
             else d.func.id if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
             else d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", None))
            for d in cls.decorator_list}

    if "BaseModel" in bases:        return "pydantic_model", False, None
    if "BaseSettings" in bases:     return "pydantic_settings", False, None
    if {"Serializer", "ModelSerializer"} & bases: return "drf_serializer", False, None
    if "Model" in bases:            return "django_model", False, None
    if "TypedDict" in bases:        return "typed_dict", False, None
    if "NamedTuple" in bases:       return "named_tuple", False, None
    if "Enum" in bases or "IntEnum" in bases or "StrEnum" in bases: return "enum", False, None
    if "Protocol" in bases:         return "protocol", False, None
    if "dataclass" in decs:         return "dataclass", False, None
    if {"define", "s", "attrs", "attr"} & decs:  return "attrs_class", True, (
        "Classified as an attrs class from the decorator name alone; verify the import.")
    if "DeclarativeBase" in bases or any(
            isinstance(s, ast.Assign) and any(getattr(t, "id", None) == "__tablename__" for t in s.targets)
            for s in cls.body):
        return "sqlalchemy_model", True, (
            "Classified as a SQLAlchemy model from __tablename__ / a DeclarativeBase-shaped "
            "base name, not from a resolved import; verify the declarative base.")
    return None, False, None
```

Field extraction, one function covering both rules:

```python
NON_FIELD_ANNOTATIONS = ("ClassVar", "InitVar")

def model_fields(cls: ast.ClassDef, kind: str) -> list[ExtractedField]:
    fields = []
    for st in cls.body:
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            ann = ast.unparse(st.annotation)
            if ann.split("[")[0] in NON_FIELD_ANNOTATIONS:
                continue                       # ClassVar/InitVar are not fields
            if kind == "sqlalchemy_model" and ann.startswith("Mapped["):
                ann = ann[len("Mapped["):-1]    # report the column type, note the wrapper
            fields.append(ExtractedField(
                name=st.target.id, type=ann,
                description=_field_kwargs_summary(st.value)))   # Field(...)/mapped_column(...)
        elif isinstance(st, ast.Assign) and isinstance(st.value, ast.Call):
            # Django models + SQLAlchemy 1.x: the TYPE is the call, not an annotation.
            callee = st.value.func
            tname = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            if not (tname.endswith("Field") or tname in {"Column", "relationship", "mapped_column"}):
                continue
            for t in st.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("__"):
                    fields.append(ExtractedField(
                        name=t.id, type=tname,
                        description=_field_kwargs_summary(st.value)))
    return fields
```

- `_field_kwargs_summary` renders the keywords that are the actual explanatory content — Django's `null`, `blank`, `max_length`, `choices`, `related_name`, `on_delete`; Pydantic's `Field(default=..., ge=..., description=...)`; SQLAlchemy's `primary_key`, `nullable`, `ForeignKey("x.id")` — as `"max_length=120, null=True"` using `ast.unparse` on each keyword value. This fills `ExtractedField.description`, which the TS extractor leaves `None`; the serialiser in `json_builder` currently emits only `{name, type}`, so adding `description` there is an additive change (and part of the `EXTRACTOR_VERSION` 5 bump).
- Relations are the graph edges worth drawing: for a `ForeignKey`/`OneToOneField`/`ManyToManyField`/`relationship` call, `args[0]` may be a `Name`, an `Attribute`, or a **string** (`"app.Model"`, `"self"`). Emit `relations: [{field, kind, target, targetIsString}]` as an additive field; a string target is why an import-graph-based model graph misses most Django relations, so `targetIsString: True` carries `assumed=True` and the note "Lazy string reference; the target model was not resolved to a class in this chunk."
- `class Meta:` nested in a Django model or a DRF serializer, and `model_config = ConfigDict(...)` / nested `class Config:` in Pydantic, are the highest-value non-field members. Extract `Meta`'s `Assign` statements (`ordering`, `db_table`, `unique_together`, `constraints`, `abstract`, and for DRF `model`/`fields`) into a `meta: {}` dict. For DRF, `Meta.fields = "__all__"` must be reported verbatim — not expanded into a field list the extractor cannot see.
- Pydantic v1-vs-v2 fingerprint, worth one narration sentence and free to compute: `@field_validator`/`@model_validator`/`model_config` ⇒ v2; `@validator`/`@root_validator`/nested `class Config` ⇒ v1. Report as `modelLibraryVersionHint` with `assumed=True`.
- Python has no `interface`/`type` declaration to mirror TS, so the `dataModels[]` bucket should also take `TypeAlias` assignments (`X: TypeAlias = ...`) and 3.12 `type X = ...` (`ast.TypeAlias`, fields `name`, `type_params`, `value`) — fields empty, snippet one line. Better than an empty bucket, and honest.
- A `ClassDef` that matches no rule is still worth emitting as a plain `class` with its methods in `importantFunctions` (qualified `Class.method`) and no `dataModels` entry. Do not force it into `dataModels` to make the list look full — an empty list is what `confidence_from_flags` is designed to score low.

### Gaps
- Pydantic and dataclasses primary docs were not fetched in the prior round or this one (the v1/v2 decorator names and `model_config` details come from working knowledge). Before stating the version fingerprint as fact in output, confirm against https://docs.pydantic.dev/latest/concepts/models/ and https://docs.python.org/3/library/dataclasses.html.
- attrs' `@attr.s`/`@attrs.define` behaviour is likewise uncited; hence `assumed=True` on that branch.

## Q7. Dependency injection: the FastAPI `Depends` graph

### Takeaway
Two exact shapes carry every `Depends` edge — `Annotated[T, Depends(fn)]` in a parameter annotation and `param = Depends(fn)` as a default value — plus `dependencies=[Depends(fn)]` on the router constructor and on the path-operation decorator; all four are literal `Call` nodes naming a project function, so the graph is genuinely extractable with no type inference.

### Cited Findings
- Shared dependencies are plain (often `async`) functions using `Annotated[...]` parameter metadata, e.g. `async def get_token_header(x_token: Annotated[str, Header()])`, raising `HTTPException` on failure — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- `APIRouter(..., dependencies=[Depends(get_token_header)])`, `app.include_router(admin.router, ..., dependencies=[Depends(get_token_header)])` and `app = FastAPI(dependencies=[Depends(get_query_token)])` are all documented forms; dependency execution order is router dependencies, then decorator `dependencies`, then normal parameter dependencies — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- `Query`, `Path`, `Body`, `Header`, `Cookie`, `Form`, `File`, `Security` inside `Annotated` tell you where each parameter comes from — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- `arguments.defaults` "covers the last *n* positional arguments"; `kw_defaults` pairs positionally with `kwonlyargs` and may contain `None` for a keyword-only arg with no default — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- Verified locally: `db: Annotated[Session, Depends(get_db)]` ⇒ `Subscript(value=Name('Annotated'), slice=Tuple(elts=[Name('Session'), Call(func=Name('Depends'), args=[Name('get_db')])]))`; `user=Depends(current_user)` ⇒ that `Call` is the last element of `args.defaults`.

### Inferences

```python
def _depends_target(call: ast.Call) -> tuple[str | None, bool]:
    """The dependency function named by a Depends(...)/Security(...) call.
    Returns (name, assumed). `Depends()` with no argument means "use the
    annotation type as the dependency" — unreadable here, so assumed."""
    fname = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", None)
    if fname not in {"Depends", "Security"}:
        return None, False
    if not call.args:
        return None, True
    target = call.args[0]
    if isinstance(target, (ast.Name, ast.Attribute)):
        return ast.unparse(target), False
    if isinstance(target, ast.Call):            # Depends(SomeClass()) — a callable class
        return ast.unparse(target.func), False
    if isinstance(target, ast.Lambda):
        return None, True
    return ast.unparse(target), True


def _iter_params(args: ast.arguments):
    """Every parameter paired with its default, honouring `defaults` covering
    only the LAST n positional args and `kw_defaults` aligning with kwonlyargs."""
    positional = list(args.posonlyargs) + list(args.args)
    pad = [None] * (len(positional) - len(args.defaults))
    for a, d in zip(positional, pad + list(args.defaults)):
        yield a, d
    if args.vararg:
        yield args.vararg, None
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        yield a, d
    if args.kwarg:
        yield args.kwarg, None


FASTAPI_PARAM_SOURCES = {"Query", "Path", "Body", "Header", "Cookie", "Form", "File"}

def extract_dependencies(fn, router_dependency_names: list[str]) -> dict:
    """The Depends graph for one path operation, in FastAPI's documented
    execution order: router dependencies, decorator dependencies, parameters."""
    edges, inputs, notes = [], [], []

    # 1. router-level (passed in, resolved from APIRouter(dependencies=[...]))
    edges += [{"name": n, "level": "router", "assumed": False} for n in router_dependency_names]

    # 2. decorator-level: @router.get("/x", dependencies=[Depends(fn)])
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call):
            deps = _kw(dec, "dependencies")
            if isinstance(deps, (ast.List, ast.Tuple)):
                for elt in deps.elts:
                    if isinstance(elt, ast.Call):
                        name, assumed = _depends_target(elt)
                        if name or assumed:
                            edges.append({"name": name, "level": "decorator", "assumed": assumed})
            elif deps is not None:
                notes.append("The decorator's dependencies= is not a literal list; "
                             "its dependencies were not read.")

    # 3. parameter-level, both forms
    for arg, default in _iter_params(fn.args):
        ann, source, dep = arg.annotation, None, None
        if isinstance(ann, ast.Subscript) and _base_name(ann.value) == "Annotated":
            # 3.9+: slice is the Tuple directly. On 3.8 it is ast.Index(value=Tuple).
            sl = ann.slice.value if isinstance(getattr(ann, "slice", None), ast.Index) else ann.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            declared_type = ast.unparse(elts[0]) if elts else None
            for extra in elts[1:]:
                if isinstance(extra, ast.Call):
                    name, assumed = _depends_target(extra)
                    if name or assumed:
                        dep = {"name": name, "level": "parameter", "via": "Annotated",
                               "assumed": assumed}
                    marker = (extra.func.attr if isinstance(extra.func, ast.Attribute)
                              else getattr(extra.func, "id", None))
                    if marker in FASTAPI_PARAM_SOURCES:
                        source = marker
        else:
            declared_type = ast.unparse(ann) if ann is not None else None

        if isinstance(default, ast.Call):                      # param = Depends(fn)
            name, assumed = _depends_target(default)
            if name or assumed:
                dep = {"name": name, "level": "parameter", "via": "default", "assumed": assumed}
            marker = (default.func.attr if isinstance(default.func, ast.Attribute)
                      else getattr(default.func, "id", None))
            if marker in FASTAPI_PARAM_SOURCES:
                source = marker

        if dep:
            edges.append(dep)
        else:
            inputs.append({"name": arg.arg, "type": declared_type,
                           "default": ast.unparse(default) if default is not None else None,
                           "source": source,          # Query/Path/Body/Header/... or None
                           "description": None})
    return {"dependencies": edges, "inputs": inputs, "notes": notes}
```

- **`Annotated` is the modern form and must come first.** An implementation that only inspects default values misses it entirely — that is the single most likely way a v1 Python extractor under-reports a real FastAPI codebase.
- The 3.8 `ast.Index` wrapper around `Subscript.slice` is handled defensively above; on 3.9+ `slice` is the expression itself. The pipeline runs on 3.13 (verified), so the `Index` branch is belt-and-braces for parsing with `feature_version`.
- Parameters that *are* dependencies go to the `dependencies[]` edge list; parameters that are not go to `inputs[]`, where `source` (`Query`/`Path`/`Body`/`Header`/`Cookie`/`Form`/`File`) is the richest accurate narration material about an endpoint and is invisible to any route regex. Note that the record's existing `dependencies[]` key currently means *imports* (`{"path": ..., "usedFor": "internal import"}` in both builders). Do **not** overload it. Emit the DI graph as a new `injectedDependencies[]` key and keep `dependencies[]` meaning imports, so no existing consumer changes meaning under it.
- `yield`-based dependencies (`def get_db(): yield session`) are ordinary functions to the extractor; note them as `teardown: True` when the dependency function's body contains a `Yield`, since "runs code after the response" is a genuinely explanation-worthy fact.
- Resolve each edge's name against the file's own symbol table and the import list, exactly as the project's accuracy rule requires ("restrict every named symbol to the extraction's symbol table; mark assumed otherwise"). A `Depends(get_db)` where `get_db` is neither defined nor imported in this file gets `assumed=True` and the note "The dependency function was not found in this file's definitions or imports; it may be injected from elsewhere."

### Gaps
- Class-based dependencies (`Depends(Paginator)` where `Paginator.__call__` does the work) are detectable as a `Name` but the *behaviour* lives in `__call__`; no cited source on how doc tools present this. v1 records the name and nothing more.

## Q8. Side effects, outbound HTTP, async

### Takeaway
Side effects come from `Call`/`With`/`Try` node shapes matched on the callee's last dotted segment and emitted with a line number (so `function_context`'s `in_range` scoping keeps working unchanged), and async is a *node type* (`AsyncFunctionDef`) plus `Await` nodes — not a substring scan, which is what `function_context._AWAIT_RE` does today.

### Cited Findings
- `Call` carries `func`, `args`, `keywords`; `With`/`AsyncWith` carry `items` (each `withitem` has `context_expr`, `optional_vars`); `Try` carries `body`, `handlers`, `orelse`, `finalbody`, and `ExceptHandler` carries `type`, `name`, `body`; `Raise` carries `exc`, `cause`; `Return` carries `value` — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- The existing extractors emit side effects as `(kind, line)` tuples (Go) or `ExtractedSideEffect(kind, line)` (TS), and `function_context` normalises both and filters by `start <= line <= end` — `src/extract/go_extractor.py`, `src/extract/ts_extractor.py`, `src/extract/function_context.py`.
- `function_context` detects async as `bool(_AWAIT_RE.search(body)) or "async" in signature` and raised-errors as `_THROW_RE` matching `throw new`/`errors.New(`/`fmt.Errorf(` — none of which appear in Python — `src/extract/function_context.py`.

### Inferences

```python
#  (callee last-segment match, receiver hint, kind)
SIDE_EFFECT_CALLS = {
    # outbound HTTP -> apiCalls, not sideEffects
    ("requests", {"get","post","put","patch","delete","head","request"}): "http_request",
    ("httpx",    {"get","post","put","patch","delete","head","request","stream"}): "http_request",
    ("aiohttp",  {"get","post","put","patch","delete","request"}): "http_request",
    # database
    (None, {"add","add_all","commit","flush","delete","execute","bulk_save_objects"}): "database_write",
    (None, {"query","scalar","scalars","get","first","all","filter","filter_by"}): "database_read",
    (None, {"save","create","update_or_create","get_or_create","bulk_create"}): "database_write",
    # logging / files / env / process
    (None, {"debug","info","warning","warn","error","exception","critical"}): "log",
    (None, {"open"}): "file_io",
    (None, {"getenv","environ"}): "env_read",
    (None, {"run","Popen","system","check_output"}): "subprocess",
}
```

Matching rules that keep this honest:

- Match the **last dotted segment** of `Call.func` (`Attribute.attr`, or `Name.id`) plus, where available, the **root receiver** (`requests.get` ⇒ root `requests`; `self.session.commit` ⇒ receiver hint `session`). Names like `.get`/`.query`/`.delete` are ambiguous (`dict.get`, `requests.get`, `session.get`) — so:
  - If the root is an imported module in `{requests, httpx, aiohttp, urllib, urllib3}` ⇒ `http_request`, `assumed=False`.
  - Else if the receiver name matches `session|db|conn|cursor|engine` or the file imports `sqlalchemy`/`django.db` ⇒ database, `assumed=False`.
  - Else `.get` is **not** emitted at all. Emitting a `dict.get` as a database read is exactly the kind of confidently wrong claim the project's stance forbids; silence is correct.
- `.save()` / `.delete()` with no recognisable receiver ⇒ emit `database_write` with `assumed=True` and the note "ORM-style `.save()`/`.delete()` matched by method name; the receiver was not resolved to a model instance, so verify this is a database write."
- Outbound HTTP goes to `apiCalls[]` (the record already has the key, and `function_context` scopes it by line), with `url` from `args[0]` when it is a `Constant` str, or from `_kw(call, "url")`. A `JoinedStr` (f-string) URL ⇒ `url = ast.unparse(node)`, `url_is_template = True`, `assumed = True` — mirroring `ExtractedApiCall.url_is_template` and the `urlPattern`/`assumed` serialisation already in `json_builder`. A `Name`/`Attribute`/`BinOp` URL ⇒ same, with the note naming the expression.
- `With`/`AsyncWith`: a `withitem.context_expr` that is a `Call` to `open` ⇒ `file_io`; to `transaction.atomic`/`session.begin` ⇒ `transaction`; to `httpx.AsyncClient`/`aiohttp.ClientSession` ⇒ `http_client_session` (and its body's `.get`/`.post` calls then resolve as HTTP without ambiguity, because the receiver is bound in `optional_vars`).
- `Try`: emit `handlesErrors: True` and the caught exception names (`ExceptHandler.type` unparsed, `None` for a bare `except:`) as a per-function fact — a bare `except:` or `except Exception:` with an empty/`pass` body is a genuinely useful risk note.
- `Raise`: `raisesError = True`; capture the exception type from `exc` (`Call.func` name or `Name.id`). FastAPI's `raise HTTPException(status_code=404, ...)` is a contract fact worth surfacing as `raises: [{"type": "HTTPException", "statusCode": 404}]` when `status_code` is a literal.
- `Return`: collect returned expression kinds to pair with `returns` annotation; mainly useful to flag "annotated `-> Item` but returns a dict" as a *note*, never as an assertion.
- Async, correctly: `is_async = isinstance(node, ast.AsyncFunctionDef)` (a fact, not a heuristic); `awaits = [n for n in ast.walk(node) if isinstance(n, ast.Await)]`; also `AsyncWith`, `AsyncFor`, and `Yield`/`YieldFrom` for generators. Pass `is_async` into `build_function_context` (Q3 parameter) so the substring heuristic never runs on Python — `"async" in signature` would also fire on a parameter named `async_mode`. One narration-worthy fact: FastAPI runs a `def` (non-async) handler in a threadpool, so `def` vs `async def` on a path operation is worth a sentence.

### Gaps
- No cited source for the receiver-name heuristics (`session|db|conn|cursor`); they are judgement calls, which is why each one that fires without an import-level confirmation carries `assumed=True`.

## Q9. What `py_extractor` cannot know statically

### Takeaway
Anything decided at import time or call time — dynamically built route tables, metaprogrammed classes, runtime registration, and anything behind a non-literal expression — must be emitted with `assumed: True` and a note naming the unresolved expression, or omitted entirely with a file-level note; it must never be guessed.

### Cited Findings
- `ast.parse()` "won't do any scoping checks" and performs no evaluation — [Python `ast` docs](https://docs.python.org/3/library/ast.html)
- code2flow, an AST-based call-graph tool for dynamic languages, documents exactly these limits: because variable types are unknown it matches calls to in-scope variables first then falls back to a single match among all other nodes; functions without definitions are skipped; same-named functions in different namespaces are skipped with a warning; imported functions from outside the project may be linked incorrectly to local functions with the same name; lambdas and factory-generated functions are skipped; functions renamed or passed around as parameters are skipped — [code2flow README](https://github.com/scottrogowski/code2flow)
- `pydoc`, Sphinx `autodoc` and `pdoc` are *import-based* (they execute the module), which is why Griffe offers `griffe.visit` (static) alongside `griffe.inspect` (dynamic) — [Griffe docs](https://mkdocstrings.github.io/griffe/)
- FastAPI's `app.openapi()` is the exact, authoritative route table — but only available if you import the app — [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- The repo's own stance: "restrict every named symbol to the extraction's symbol table; mark assumed otherwise", and the Go extractor marks `assumed=True` on **every** route regardless of how well the prefix resolved — `src/extract/go_extractor.py`, `src/extract/common.py`.

### Inferences

Enumerated, with the required output for each:

| Cannot know | Required output |
|---|---|
| Routes built in a loop/comprehension (`for r in ROUTES: app.add_api_route(**r)`) | No route entries; one file-level note: "Routes are registered from a data structure at runtime; no route table could be read statically." Pull confidence down via `assumed` count. |
| Non-literal prefix/path (`prefix=settings.API_PREFIX`, f-string path) | Local path only, `assumed=True`, note quoting the unparsed expression. |
| A router never seen in any `include_router` | Router-local path, `assumed=True`, note "mount prefix unknown". |
| Flask app built in `create_app()` and blueprints registered conditionally | Routes with `assumed=True`, note "registration happens inside a factory; the `url_prefix` applied at registration was not resolved." |
| Django `include("polls.urls")` | A route entry whose handler is `include('polls.urls')`, `assumed=True`; sub-paths are **not** joined. Resolving the module string to a file is a package lookup, not a parse. |
| Django HTTP methods | `method="UNKNOWN"` always from the URLconf; methods only ever reported from the view, with provenance. |
| `setattr`, `type()`-created classes, metaclass-generated fields, `__getattr__` façades | Omit; file-level note "this module builds attributes dynamically; the extracted surface is incomplete." |
| Decorators that rewrap or re-register (`functools.wraps`, a custom `@route` registry, Celery's `@shared_task` late binding) | Record the decorator name verbatim; do not infer what it does beyond the recognised framework set. |
| Call graph across files, duck-typed calls, functions passed as values | `calls`/`calledBy` stay file-local (which is already what `function_context.callers_of`/`calls_made` do — they search only the chunk). Never claim a cross-file caller. |
| Monkeypatching, conditional definitions under `if TYPE_CHECKING:` / `try: import X except ImportError:` | Extract both branches, note "defined conditionally; which definition is active depends on runtime imports." |
| Star imports (`from x import *`) | Cannot enumerate names; dependency entry with `assumed=True` and note. |
| Resolved *types* (`Optional[User]`, string forward refs, `from __future__ import annotations`) | Report the annotation **text** only. Never claim to know the type. |
| `__all__` computed or `+=`-extended | `visibility` per Q4 with `assumed=True`. |

Two hard rules for the implementation:

1. **Never import or execute the target repo.** `ast.parse` only. Importing an untrusted repo to call `app.openapi()` would be the most accurate route table available and is categorically out of bounds — this is the same argument Griffe encodes by separating `visit` from `inspect`.
2. **Parse failure is a first-class outcome.** `ast.parse` raises `SyntaxError` (a file written for a newer Python, or genuinely broken) and `ValueError` on a null byte. Catch both and emit a real record with empty lists, `confidence` from `confidence_from_flags(0, 0)` → `EMPTY_EXTRACTION_CONFIDENCE` (0.3), and the note "This file could not be parsed (`<SyntaxError message>` at line N); nothing was extracted." That is loud and schema-valid — the opposite of the Angular failure mode the validation doc singles out as the repo's worst ("schema-valid with every content list empty"). Optionally retry once with `ast.parse(src, feature_version=(3, 12))`? No — `feature_version` only lets you parse as an *earlier* Python, which cannot help with newer syntax. Report the failure.

### Gaps
- None material; every limit above is either cited or a direct consequence of "no evaluation".

## Q10. Test plan (following the existing `tests/` style)

### Takeaway
The existing style is plain `pytest` functions with inline triple-quoted source constants, asserting on dataclass fields (`tests/test_go_extractor.py`) plus a separate integration test that runs the builder over a fixture tree (`tests/test_extractor_integration.py`) — so the Python extractor needs one `tests/test_py_extractor.py` of unit tests over inline sources, additions to `tests/test_function_context.py`, and one fixture repo for an end-to-end record assertion.

### Cited Findings
- `tests/test_go_extractor.py` is function-per-behaviour with inline `text = """..."""` sources and assertions like `assert structs[0].fields == [("ID", "int64"), ("FullName", "string")]` and `assert get_route.path == "/api/v1/alumni"` — repo source.
- `tests/test_function_context.py` defines one module-level `TS_SOURCE` constant, a `lines_of` helper, and one test per behaviour including explicit negative cases (`test_function_with_no_comment_above_gets_none`, `test_blank_line_between_comment_and_function_breaks_the_link`) — repo source.
- `tests/test_schema_check.py:81-96` already locks in the current placeholder failure for an unimplemented stack — repo source (per `documentation/14-stack-support-validation.md`).
- Existing test files present: `test_common.py`, `test_go_extractor.py`, `test_ts_extractor.py`, `test_function_context.py`, `test_extractor_integration.py`, `test_reuse_pipeline.py`, `test_schema_check.py`, `test_secret_redaction_integration.py` — repo listing.

### Inferences

**`tests/test_py_extractor.py`** — inline sources, one test per behaviour:

| Test | Asserts |
|---|---|
| `test_line_range_includes_decorators` | For `@router.get("/x")\nasync def h(): ...`, `line_range[0]` is the decorator's line, not the `def` line; the snippet text's first line starts with `@router.get`. **This is the regression test for the central trap.** |
| `test_line_range_ends_at_last_body_line` | `end_lineno` excludes a trailing blank line and a trailing comment; two adjacent functions' ranges are not contiguous. |
| `test_missing_end_lineno_marks_assumed` | A node with `end_lineno = None` (set manually on a parsed node) yields `assumed=True` and a note mentioning "End line unavailable". |
| `test_async_function_is_detected_by_node_type` | `async def` ⇒ `is_async True`; a sync `def` with a parameter named `async_mode` ⇒ `is_async False` (guards against the substring heuristic). |
| `test_docstring_is_description_and_comment_above_is_ignored` | `# TODO: fix this\ndef f():\n    """Real doc."""` ⇒ `description == "Real doc."`, `descriptionSource == "docstring"`. |
| `test_fstring_docstring_is_treated_as_undocumented` | `description is None`, not a partial string. |
| `test_module_docstring_becomes_file_description` | `fileDescription` equals the cleaned module docstring. |
| `test_all_declares_public_surface` | `__all__ = ["a"]` with `def a(): ...` and `def b(): ...` ⇒ `a` is `declared_in_all`/`exported True`; `b` is `private_by_underscore`/`exported False` with a note mentioning `__all__`. |
| `test_underscore_convention_without_all` | `_helper` ⇒ `private_by_underscore`; `helper` ⇒ `public_by_convention`. |
| `test_dunder_is_protocol_not_private` | `__init__` ⇒ `visibility == "protocol_method"`, `exported True`. |
| `test_computed_all_marks_visibility_assumed` | `__all__ = mod.__all__` ⇒ every name assumed with a note. |
| `test_fastapi_route_composes_router_prefix` | `router = APIRouter(prefix="/items")` + `@router.get("/{item_id}")` ⇒ `path == "/items/{item_id}"`, `type == "dynamic"`, `routing_library == "fastapi"`, `assumed is True`. |
| `test_fastapi_route_composes_include_router_prefix` | With a mount map `{"router": [("/api/v1", False, None)]}` ⇒ `/api/v1/items/{item_id}`. |
| `test_fastapi_router_named_anything_is_resolved` | `gateway = APIRouter(prefix="/g")` + `@gateway.post("/x")` ⇒ `/g/x` (no hardcoded `app`/`router`). |
| `test_fastapi_non_literal_prefix_is_assumed_with_note` | `APIRouter(prefix=settings.PREFIX)` ⇒ path is `/x` only, note contains `settings.PREFIX`. |
| `test_fastapi_router_with_no_include_is_router_local` | Note mentions "mount prefix". |
| `test_depends_from_annotated` | `db: Annotated[Session, Depends(get_db)]` ⇒ one edge `{"name": "get_db", "level": "parameter", "via": "Annotated"}`; `db` is **not** in `inputs`. |
| `test_depends_from_default_value` | `user=Depends(current_user)` ⇒ edge with `via == "default"`. |
| `test_router_and_decorator_dependencies_are_both_captured` | Three edges in documented order: router, decorator, parameter. |
| `test_annotated_query_param_records_its_source` | `q: Annotated[str, Query(min_length=3)]` ⇒ `inputs[0]["source"] == "Query"`. |
| `test_depends_on_unknown_symbol_is_assumed` | Edge carries `assumed True` and a note about the symbol table. |
| `test_flask_route_defaults_to_get` | `@bp.route("/x")` ⇒ `method == "GET"`. |
| `test_flask_route_methods_keyword` | `methods=["GET","POST"]` ⇒ two routes (or one with both methods — pick one and lock it; recommend two entries, one per method, so `featureMapping`'s method matching keeps working). |
| `test_flask_stacked_route_decorators_give_two_routes` | Two entries for one function, paths `/` and `/<page>`. |
| `test_flask_register_blueprint_prefix` | `register_blueprint(bp, url_prefix="/pages")` ⇒ `/pages/<page>`. |
| `test_flask_add_url_rule_is_captured` | A route exists even with no decorator. |
| `test_django_urlpatterns_in_order` | Three entries in source order; `method == "UNKNOWN"` on all; `<int:year>` ⇒ `dynamic`. |
| `test_django_include_is_flagged_not_joined` | Handler is `include('aggregator.urls')`, `assumed True`, note mentions resolving the module. |
| `test_django_non_literal_urlpatterns_emits_note` | `urlpatterns = build()` ⇒ no routes, one note. |
| `test_pydantic_model_fields_with_types` | `[("name","str"),("price","float")]`, `kind == "pydantic_model"`. |
| `test_dataclass_detected_from_decorator_and_classvar_excluded` | `ClassVar[int]` is not a field. |
| `test_django_model_fields_from_assign_calls` | `full_name` ⇒ type `CharField`, description contains `max_length=120`. |
| `test_sqlalchemy_mapped_column_unwraps_mapped` | `id` ⇒ type `int`, kind `sqlalchemy_model`, `assumed True`. |
| `test_typeddict_and_namedtuple_are_data_models` | Both present with fields. |
| `test_unknown_class_is_not_forced_into_data_models` | `dataModels` empty; its methods appear in `importantFunctions` as `Class.method`. |
| `test_requests_call_is_an_api_call_not_a_side_effect` | `requests.post("https://x/y")` ⇒ one `apiCalls` entry, method `POST`. |
| `test_fstring_url_marks_assumed` | `url_is_template True`. |
| `test_dict_get_is_not_reported_as_database_read` | `cfg.get("k")` produces no side effect. **Negative test for the ambiguity rule.** |
| `test_session_commit_is_a_database_write` | kind `database_write`. |
| `test_orm_save_is_assumed` | `obj.save()` ⇒ `assumed True` with a note. |
| `test_open_in_with_statement_is_file_io` | kind `file_io`. |
| `test_raise_http_exception_records_status_code` | `raises[0] == {"type": "HTTPException", "statusCode": 404}`. |
| `test_syntax_error_yields_honest_record` | Confidence `0.3`, every list empty, note contains "could not be parsed" and the line number. |
| `test_secret_in_docstring_is_redacted` | `secretsRedacted` flagged and the literal secret absent from the record (mirrors `tests/test_secret_redaction_integration.py`). |
| `test_long_function_snippet_is_trimmed_with_continuation_note` | >120-line function ⇒ `truncated True`, `continuationNote` mentions the remaining source lines. |

**Additions to `tests/test_function_context.py`** (guard the new optional parameters):

- `test_supplied_description_overrides_comment_scan` — passing `description="From docstring"` beats `leading_doc_comment`.
- `test_ts_and_go_paths_unchanged_when_overrides_absent` — the existing TS assertions still pass (regression guard on the Q3 change).
- `test_python_file_without_overrides_gets_no_description` — proves the current upward scan yields `None` on Python, so the override is load-bearing rather than cosmetic.
- `test_visibility_key_is_present_and_null_for_ts` — the additive key exists for every language.

**Fixture repo** for the integration test, `tests/fixtures/py_fastapi_app/` (smallest tree that exercises the cross-file join):

```
pyproject.toml                 # marker file, so project_type detects "python"
app/main.py                    # app = FastAPI(); app.include_router(items.router, prefix="/api/v1")
app/routers/items.py           # router = APIRouter(prefix="/items"); two path operations, Depends
app/dependencies.py            # get_db (yield), current_user (raises HTTPException)
app/schemas.py                 # Pydantic Item, ItemCreate; __all__ = ["Item"]
app/models.py                  # SQLAlchemy 2.0 declarative User
app/broken.py                  # deliberate SyntaxError
```

`tests/test_py_extractor_integration.py` then asserts, in the style of `test_extractor_integration.py`: the record for `app/routers/items.py` has `routes[0]["path"] == "/api/v1/items/{item_id}"`; `language == "Python"` (which `common.detect_language` already returns for `.py`); `schema_check.validate_record(record) == []` for every record including `broken.py`; the `broken.py` record has `confidence == 0.3` and a parse note; `featureMapping` is populated between the router chunk and the schema chunk.

Plus `tests/test_schema_check.py`: replace/extend the test that locks in the Python placeholder failure, since Python records are now schema-valid. And `tests/test_reuse_pipeline.py`: one test that a stored record with `extractorVersion: 4` is treated as stale after the bump to 5.

### Gaps
- I did not read `tests/test_extractor_integration.py` or `tests/test_schema_check.py` in full (they were listed and partially quoted via the validation doc), so the exact fixture-construction idiom there — whether fixtures are committed files or built in a `tmp_path` — should be confirmed before writing the integration test. Both styles work; match whichever is already used.

## Q11. Acceptance criteria

### Takeaway
The extractor is correct when every record it emits is schema-valid, every claim in it is traceable to a node that was actually parsed, every unresolved expression is marked `assumed` with a note naming it, and the three specific failure modes the validation doc identified for this pipeline are provably absent.

### Cited Findings
- `schema_check.validate_record` returns an empty list for a valid record; the required set is the ten core fields plus three storage keys — `src/validate/schema_check.py`.
- `confidence_from_flags(0, 0)` returns `EMPTY_EXTRACTION_CONFIDENCE = 0.3`, because "'I have nothing to say about this file' is the least confident an extractor can be, not the most" — `src/extract/common.py`.
- The validation doc's verdict on the current Python branch: "Placeholder record, `confidence: 0`, 5 missing required fields, generic narration, video still renders"; and on Angular, "the single worst output in the repo: it is schema-valid with every content list empty, which means a rendered video that looks finished and says nothing true" — `documentation/14-stack-support-validation.md`.
- The same doc: "schema validation is currently report-only (`src/pilot/run_pilot.py:35-64`) ... A stack with no extractor should not produce an mp4" — `documentation/14-stack-support-validation.md`.

### Inferences

Ship criteria, each one checkable:

1. **Schema**: `validate_record()` returns `[]` for every record the Python path emits, including parse failures and empty files. The five fields the placeholder branch omitted (`language`, `lineRange`, `frameworkOrLibrary`, `lastUpdated`, `pullRequest`) are all present.
2. **Record shape parity**: the Python record's key set equals the Go record's key set, plus only the agreed additive keys (`visibility`, `injectedDependencies`, `relations`, `meta`, `bodyStartLine`, `reExports`, `displayPath`). A diff test over `set(go_record) ^ set(py_record)` makes this mechanical.
3. **The decorator trap is regression-tested**: for every route handler in the fixture, `snippet.text.splitlines()[0].lstrip().startswith("@")`.
4. **No silent emptiness**: a file that parses but yields nothing scores 0.3 and carries a note. A `confidence` of 0.95 with every list empty must be impossible — assert it on the fixture set.
5. **Every `assumed: True` carries a non-null note**, and every note names the specific unresolved expression or the specific thing to verify. Assert as an invariant over all fixture records: `all(e["notes"] for e in record["routes"] if e["assumed"])`.
6. **No claim without a node**: every name in `importantFunctions`, `dataModels`, `injectedDependencies` and `routes[].handler` is either defined in the file or present in its import list; otherwise `assumed: True`. Assert as an invariant.
7. **Negative assertions hold**: `dict.get` is not a database read; a comment above a `def` is never a description; a name absent from a *readable* `__all__` is not reported public; a Django route never carries a guessed HTTP method.
8. **Round-trip through storage**: with `EXTRACTOR_VERSION` bumped, `needs_reanalysis` returns `True` once for an existing store and `False` on the immediately following run (proves the gate fires exactly once and the new record is stable — same content ⇒ same `contentHash`).
9. **Determinism**: two runs over the same tree produce byte-identical records except `lastUpdated`. Ordering must come from source order, never from `ast.walk` or a set iteration — this is the concrete consequence of `ast.walk` yielding nodes "in no specified order".
10. **Safety**: no `import`, `exec`, `eval`, `importlib` or subprocess call anywhere in the extraction path; the target repo is parsed, never executed. Grep-assertable in CI.
11. **Secrets**: every snippet and every docstring passes through `redact_secrets`; a fixture with a hardcoded credential in a docstring produces `secretsRedacted: True`, confidence capped at 0.5 (matching the existing builders' behaviour), and no literal secret anywhere in the output JSON.
12. **Pilot gate**: with a real Python repo, `pilot_report.json` shows `schemaValidation` all-valid for Python chunks and a confidence distribution with no 0.95-with-empty-lists records. Separately recommended (independent of this extractor, but the right moment to do it): make schema validation blocking in `run_pilot.py` so an unextractable stack cannot render an mp4.

### Gaps
- There is no gold-standard Python repo in the project to measure recall against, so "did we find every route" cannot be verified absolutely. The practical proxy is a FastAPI project where `app.openapi()` output is available *outside* the pipeline (generated once by hand, by a developer, on a repo they trust) and compared to the extracted route table — a one-off accuracy measurement, not a pipeline step, since the pipeline must never import the target repo.
