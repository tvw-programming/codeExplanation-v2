# Express/Node.js support in codeExplanation-v2 — implementation blueprint

Scope: this is a HOW document. Background (what matters and why) is in
`/home/claude/codeExplanation-v2/documentation/research/pipeline-support-across-six-stacks/express_node.md`
and `/home/claude/codeExplanation-v2/documentation/14-stack-support-validation.md`. Everything below is
written against the code as it exists on disk today, which I read: `src/detect/project_type.py`,
`src/chunk/chunker.py`, `src/chunk/feature_grouping.py`, `src/chunk/chunk_splitter.py`,
`src/extract/reuse_pipeline.py`, `src/extract/ts_extractor.py`, `src/extract/go_extractor.py`,
`src/extract/json_builder.py`, `src/extract/common.py`, `tests/test_go_extractor.py`,
`tests/test_project_type.py`, `requirements.txt`.

Package names, versions, the tree-sitter Python API and every S-expression query in Part B were
executed in a throwaway venv on this machine, not recalled. Where a result corrects the brief I say so
explicitly (one place: Node's extensionless resolution does **not** try `.mjs`/`.cjs`).

---

## Part A — Detection: what exactly changes in `project_type.py`, and what else must change for a chunk to carry the stack

### Takeaway
Express is currently *unrepresentable*, not mis-tuned: `MARKER_FILES` maps `package.json` to the single
key `"react_or_angular"` (`project_type.py:26-31`), so a `package.json` is only ever a frontend marker,
and `_detect_frontend_flavor` returns the literal string `"react_or_angular"` when neither `react` nor
`@angular/core` is a dependency (`project_type.py:97-108`). The fix is a new `"node"` marker class that
shares the same `package.json` marker file but is classified by dependency keys, a new `express` backend
stack string, and — crucially — the ability for one `package.json` to produce a frontend hit, a backend
hit, or both. Five files change; four of them by a handful of lines.

### Cited Findings
- `MARKER_FILES` is a flat `stack -> [filenames]` dict and `_find_marker_hits` walks directories to
  `max_depth=3`, appending a `MarkerHit(directory, marker_file)` per `(stack, filename)` pair that exists.
  Because `package.json` appears under exactly one key, a single file can produce at most one hit class
  today — the structural obstacle to full-stack monorepos. — read at `src/detect/project_type.py:26-31, 78-89`
- `detect_project_type` returns `ProjectType.to_dict()` shaped `{"frontend":…, "backend":[…],
  "architecture":…, "dockerized":…}` and the backend branch appends per-stack in a fixed order
  (`go`, `python`, java flavors), each also feeding `backend_service_roots`, which drives the
  monolith/microservice heuristic. — `src/detect/project_type.py:142-186`
- `chunk_repo` iterates `project_type.marker_hits` **by key name** — `"react_or_angular"`, `"go"`,
  `"python"`, `"spring_boot"` — and for the frontend key calls `_find_frontend_src_root` (`src`, `app`,
  `.`) and passes `project_type.frontend_stack or "react"` as the stack. A new marker key is simply
  never visited until a loop is added. — `src/chunk/chunker.py:44-62`
- `Feature.stack` is a free-form string carried verbatim into `ChunkPlan.stack`
  (`chunk_splitter.py:70-105`), and `reuse_pipeline.py` dispatches on it with
  `if chunk.stack in ("react","angular") … elif chunk.stack == "go" … else:` placeholder record with
  `confidence: 0`. — `src/extract/reuse_pipeline.py:85-94`
- `feature_grouping.py` has exactly four grouping entry points: `group_react_or_angular_features`,
  `group_go_features`, `group_spring_boot_features` (both via `_group_by_resource_pairing`) and
  `group_python_agent_features`. **There is no Node/Express grouping function.** `FRONTEND_SOURCE_EXTENSIONS`
  already contains `.js`/`.jsx` but not `.mjs`/`.cjs`. — `src/chunk/feature_grouping.py:31, 112-370`
- `RESOURCE_DIR_NAMES` already contains `controller(s)`, `service(s)`, `repository(ies)`, `handler(s)`, and
  `RESOURCE_SUFFIX_PATTERN` already strips `_controller`/`_service`/`Controller`/`Service` — so the Go/Spring
  pairing machinery is directly reusable for a `controllers/ + services/ + models/` Express layout. — `feature_grouping.py:38-46`
- Express prescribes no layout; practitioners report "very few of them follow the same organization"
  ([Project structure for an Express REST API](https://dev.to/ccleary00/project-structure-for-an-express-rest-api-when-there-is-no-standard-way-4gk3)),
  which is why grouping must not be the primary structural claim — the mount graph is.

### Inferences (the design)

**A1. New marker class + dependency-based classification.** Keep `package.json` under the existing
frontend key (nothing that reads `marker_hits["react_or_angular"]` breaks) and add a parallel `"node"`
key pointing at the same file, then let a single classifier decide which of the two hits survive.

```python
# src/detect/project_type.py

MARKER_FILES = {
    "react_or_angular": ["package.json"],
    "node": ["package.json"],            # NEW: same marker file, different classification
    "python": ["requirements.txt", "pyproject.toml", "setup.py"],
    "go": ["go.mod"],
    "spring_boot": ["pom.xml", "build.gradle", "build.gradle.kts"],
}

# Dependency keys that make a package.json a Node BACKEND. Order matters only
# for the returned stack string; any hit is sufficient for "is a backend".
NODE_BACKEND_DEPS = {
    "express": "express",
    "@nestjs/core": "nest",        # classified, not extracted (see Gaps)
    "koa": "koa",
    "fastify": "fastify",
    "@hapi/hapi": "hapi",
}
# Secondary, weaker evidence used only when no framework dep is present.
NODE_BACKEND_HINT_DEPS = {
    "mongoose", "sequelize", "typeorm", "prisma", "knex", "pg", "mysql2",
    "jsonwebtoken", "bcrypt", "bcryptjs", "cors", "helmet", "morgan",
    "body-parser", "multer", "dotenv", "socket.io", "nodemon",
}
FRONTEND_DEPS = {"react", "react-dom", "@angular/core", "vue", "svelte",
                 "next", "nuxt", "vite", "@remix-run/react"}

@dataclass
class NodePackage:
    directory: str
    is_backend: bool
    is_frontend: bool
    backend_framework: str | None     # "express" | "koa" | ... | None
    express_major: int | None         # 4 or 5, from the semver range; None if absent/unparseable
    module_type: str                  # "module" | "commonjs" (default per Node docs)
    assumed: bool                     # True when classification rested on hint deps only
    note: str | None
```

```python
def _classify_node_package(package_json_path: Path) -> NodePackage:
    """Decide whether one package.json describes a Node backend, a frontend,
    or both. Never guesses silently: a package with no framework dependency
    and only hint deps is reported is_backend=True with assumed=True and a
    note naming the evidence, so the narration can say 'looks like'."""
    directory = ""   # filled by caller
    try:
        data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return NodePackage(directory, False, True, None, None, "commonjs", True,
                           "package.json present but unreadable; treated as a frontend marker only, "
                           "as before. Verify by hand.")
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    scripts = " ".join(str(v) for v in data.get("scripts", {}).values())

    framework = next((name for key, name in NODE_BACKEND_DEPS.items() if key in deps), None)
    hint_hits = sorted(NODE_BACKEND_HINT_DEPS & set(deps))
    is_frontend = bool(FRONTEND_DEPS & set(deps))

    assumed = False
    note = None
    if framework:
        is_backend = True
    elif hint_hits or "node " in scripts or "nodemon" in scripts:
        is_backend, assumed = True, True
        note = ("No Express/Koa/Fastify/Nest dependency found; classified as a Node backend from "
                f"secondary evidence only ({', '.join(hint_hits) or 'start script runs node'}). "
                "Verify the entry point before trusting any route table.")
    else:
        is_backend = False

    express_major = None
    if framework == "express":
        m = re.search(r"(\d+)", deps.get("express", ""))
        express_major = int(m.group(1)) if m else None

    module_type = data.get("type") or "commonjs"   # Node: absent "type" means CommonJS
    return NodePackage(directory, is_backend, is_frontend, framework,
                       express_major, module_type, assumed, note)
```

**A2. Monorepo with both.** The rule that falls out of the classifier, and that handles every real layout:

| package.json has | frontend hit kept | node hit kept | effect |
|---|---|---|---|
| `react` only | yes | no | unchanged behaviour |
| `express` only | **no** | yes | backend `["express"]`, `frontend: None` — the current bug fixed |
| `express` + `react` (single-package full-stack) | yes | yes | both; two feature sets from one directory |
| neither, hint deps only | no | yes (`assumed=True`) | loud, not silent |
| neither, nothing | yes (`"react_or_angular"`) | no | unchanged fallback |

Separate `package.json` files in `client/` and `server/` are already handled: `_find_marker_hits` walks
to depth 3 and emits one hit per directory, so `client/package.json` classifies frontend and
`server/package.json` classifies backend, independently. The one change needed is that
`_detect_frontend_flavor`'s loop must skip directories whose package was classified backend-only —
otherwise `server/package.json` still sets `frontend_stack = "react_or_angular"`.

**A3. Minimal diff shape in `detect_project_type` (fits the existing `{'frontend':…, 'backend':[…]}` return).**

```python
     marker_hits = _find_marker_hits(root, max_depth)
+
+    # One classification pass over every package.json, reused by the frontend
+    # flavour loop, the backend list and (later) chunker/extractor.
+    node_packages: list[NodePackage] = []
+    for hit in marker_hits["node"]:
+        pkg = _classify_node_package(root / hit.directory / hit.marker_file)
+        pkg.directory = hit.directory
+        node_packages.append(pkg)
+    # Drop the frontend hit for any directory that is backend-only, so a
+    # server/package.json no longer reports frontend "react_or_angular".
+    backend_only_dirs = {p.directory for p in node_packages if p.is_backend and not p.is_frontend}
+    marker_hits["react_or_angular"] = [h for h in marker_hits["react_or_angular"]
+                                       if h.directory not in backend_only_dirs]
+    marker_hits["node"] = [h for h in marker_hits["node"]
+                           if any(p.directory == h.directory and p.is_backend for p in node_packages)]

     frontend_stack = None
     for hit in marker_hits["react_or_angular"]:
         ...                                     # unchanged

     backend_stacks: list[str] = []
     backend_service_roots: set[str] = set()

+    express_packages = [p for p in node_packages if p.is_backend]
+    if express_packages:
+        backend_stacks.extend(sorted({p.backend_framework or "node" for p in express_packages}))
+        backend_service_roots.update(p.directory for p in express_packages)
     if marker_hits["go"]:
         ...
```

and on `ProjectType`:

```python
+    node_packages: list[NodePackage] = field(default_factory=list)
```

`to_dict()` is left alone — it already serialises `backend` as a list, so a repo detects as
`{'frontend': 'react', 'backend': ['express'], ...}` with no schema change anywhere downstream.

**A4. The stack string.** Use **`"express"`** (not `"node"`, not `"js"`), for three reasons grounded in
the code: `reuse_pipeline` dispatch is a literal string compare, so the value must name the thing the
extractor actually understands; `go` sets the precedent of naming the language while `spring_boot`/`java`
sets the precedent of distinguishing framework from language, and Express route/middleware semantics are
the entire payload here; and `_resolve_frontend_framework_or_library` style resolution means a Koa or
Fastify repo must land on a *different* string so it hits the loud placeholder branch instead of being
narrated with Express semantics. `"node"` is reserved as the fallback for a backend classified from hint
deps with no recognised framework — it also hits the placeholder branch, by design.

**A5. `feature_grouping.py` — the Node grouping function.** There is none; add one. It should group by
**router module**, falling back to the existing resource pairing:

```python
NODE_SOURCE_EXTENSIONS = {".js", ".mjs", ".cjs"}       # NEW
NODE_ORGANIZING_DIR_NAMES = ["routes", "api", "controllers", "modules", "features"]

def group_node_features(root: Path, backend_root: Path, stack: str = "express") -> list[Feature]:
    """Group an Express source tree by ROUTER MODULE, because the mount graph
    is the architecture and folder names are only a labelling hint.

    Pass 1: every file under routes/ or api/ is a feature seed named after its
            stem (users.js -> "users"); its matching controllers/<name>*,
            services/<name>*, models/<name>* siblings join it by stem, reusing
            _resource_stem() so userController.js and user.controller.js both
            pair with routes/user.js.
    Pass 2: anything not claimed falls through to _group_by_resource_pairing()
            for a controllers/services split with no routes/ folder.
    Pass 3: remaining loose files (app.js, server.js, index.js) become one
            feature named after backend_root — this is the mount-graph entry
            point and must never be dropped, since every prefix starts there.
    """
```

Two details that matter and are easy to get wrong:
- `.mjs`/`.cjs` must be added (`FRONTEND_SOURCE_EXTENSIONS` has only `.js`/`.jsx`), or an ESM-by-extension
  repo chunks to nothing.
- the flat-file bug already fixed for React (`feature_grouping.py:140-150`, locked by
  `tests/test_feature_grouping.py:102,119,132`) is *exactly* the Express layout — `src/routes/*.js` flat —
  so the new function must claim flat files in the organizing folder, and a test must assert it.
  `documentation/14-stack-support-validation.md:149` names Express as the stack most likely to be erased
  by that class of bug.

**A6. `chunker.py`, `reuse_pipeline.py`, `json_builder.py`.**

```python
# src/chunk/chunker.py  — after the python/spring loops
+    for hit in project_type.marker_hits.get("node", []):
+        backend_root = root / hit.directory if hit.directory else root
+        pkg = next((p for p in project_type.node_packages if p.directory == hit.directory), None)
+        stack = (pkg.backend_framework if pkg and pkg.backend_framework else "node")
+        src_root = _find_backend_src_root(backend_root)   # "src", "server", "app", "."
+        features.extend(group_node_features(root, src_root, stack=stack))
```

```python
# src/extract/reuse_pipeline.py — one branch, plus a PROJECT-LEVEL prepass
+    # Express needs project-wide facts before any per-file parse: module type
+    # per directory, express major version, and the resolved mount graph. One
+    # pass over the whole node tree, cached and passed into every chunk.
+    express_project = None
+    if any(c.stack == "express" for c in result.chunks):
+        from .express_project import build_express_project
+        express_project = build_express_project(root, project_type)
...
         elif chunk.stack == "go":
             record = build_backend_go_chunk_record(...)
+        elif chunk.stack == "express":
+            record = build_backend_express_chunk_record(
+                root, chunk, project_type_dict, express_project)
         else:
             record = { ... placeholder ... }
```

The prepass is not optional convenience: a `.js` file's module system is decided by the nearest
`package.json` `"type"`, and a route's full path is decided by `app.use` calls in other files, so both
are unanswerable from the per-chunk loop. Note the reuse cache interacts here — a chunk whose own content
hash is unchanged can still have a *stale route path* if a parent file's mount prefix changed. Mitigation:
fold a hash of the resolved mount graph into `EXTRACTOR_VERSION`-adjacent invalidation, or store the
graph hash on each express record and treat a mismatch as stale (`needs_reanalysis` currently compares
file content only, `reuse_pipeline.py:75`).

`json_builder.py` gets `build_backend_express_chunk_record`, modelled on
`build_backend_go_chunk_record` field-for-field: same key set (`chunkId`, `filePath`, `featureName`,
`projectType`, `language`, `lineRange`, `fileDescription`, `frameworkOrLibrary`, `inputs`, `outputs`,
`eventHandlers`, `apiCalls`, `importantFunctions`, `sideEffects`, `featureMapping`, `dependencies`,
`dataModels`, `routes`, `confidence`, `confidenceLevel`, `notes`, `contentHash`, `extractorVersion`,
`lastUpdated`, `pullRequest`, `pullRequestNote`), same `confidence_from_flags(total_claims, assumed_claims)`
call, same `trim_snippet` path for every snippet (which is the single redaction choke point —
`common.py:71-100`). Express-specific content goes in existing slots, no schema change:
`routes` (mount-resolved, with `assumed`/`notes`), `dataModels` (Mongoose/Sequelize/Zod), `inputs`
(validation-schema-derived request body), `sideEffects` (db/log/fs), and `middleware` is the one place a
new optional array is justified — order is semantics and nothing in the current schema can carry it.
`detect_language` already maps `.js` → `JavaScript` and needs `.mjs`/`.cjs` added (`common.py:24-31`).

### Gaps
- `src/validate/schema_check.py` and `docs/json-structure-rules.md` were not read in this pass; if
  `middleware` is added as a new array the schema file must be updated in the same change or
  validation will report the Express records invalid for a new reason.
- Whether `Feature.stack`'s docstring enumeration (`feature_grouping.py:52`) is asserted anywhere was
  not checked; it is a comment, but grep before relying on that.
- Nest, Koa and Fastify are classified but not extracted. That is deliberate (loud placeholder beats
  Express semantics applied to Koa's `ctx`), but it means `backend: ["koa"]` reports `confidence: 0`.

---

## Part B.1 — tree-sitter in Python: exact packages, pinned versions, working setup

### Takeaway
Pin **`tree-sitter==0.25.2`** and **`tree-sitter-javascript==0.25.0`**, and target the **0.25+ API**
(`Query(language, src)` + `QueryCursor(query).captures(node)`). The grammar's own metadata understates
its requirement: `tree-sitter-javascript==0.25.0` declares `tree-sitter~=0.24` but its compiled grammar
is ABI 15, and `tree-sitter==0.24.0` **refuses to load it**. I measured this.

### Cited Findings
- PyPI, queried live: `tree-sitter` latest `0.26.1`, `requires_python >=3.10`; release history
  `… 0.23.2, 0.24.0, 0.25.0, 0.25.1, 0.25.2, 0.26.0, 0.26.1`. — [PyPI JSON API: tree-sitter](https://pypi.org/pypi/tree-sitter/json)
- PyPI, queried live: `tree-sitter-javascript` latest `0.25.0`, `requires_python >=3.10`,
  `requires_dist: ['tree-sitter~=0.24; extra == "core"']`, summary "JavaScript grammar for tree-sitter";
  releases `0.21.x, 0.23.0, 0.23.1, 0.25.0`. Prebuilt `cp310-abi3` wheels ship for macOS x86_64 and
  arm64, manylinux x86_64 and aarch64, musllinux, and Windows amd64/arm64 — **no C toolchain needed**,
  which matters for this repo (`requirements.txt` is PyYAML/pytest/piper-tts only). — [PyPI JSON API: tree-sitter-javascript](https://pypi.org/pypi/tree-sitter-javascript/json)
- Measured on this machine, python venv: with `tree-sitter==0.26.1`, `tree_sitter.LANGUAGE_VERSION == 15`,
  `MIN_COMPATIBLE_LANGUAGE_VERSION == 13`, and `Language(tree_sitter_javascript.language()).abi_version == 15`.
  Query execution works. With `tree-sitter==0.24.0` and the same grammar wheel:
  `ValueError: Incompatible Language version 15. Must be between 13 and 14`. So the declared
  `tree-sitter~=0.24` lower bound is wrong in practice; **≥0.25 is the real floor.** — measured, not cited
- Measured: `dir(tree_sitter)` at 0.25.2/0.26.1 exposes `Language, LogType, LookaheadIterator, Node,
  Parser, Point, Query, QueryCursor, QueryError, QueryPredicate, Range, Tree, TreeCursor`. At 0.24,
  `Language.query(...)` existed and `Query.captures()` was called on the query itself; at 0.25+ that
  moved to `QueryCursor`. The published docs index lists the same class set, with `QueryCursor` described
  as "A class for executing a `Query` on a syntax `Tree`", but shows no signatures. — [py-tree-sitter docs](https://tree-sitter.github.io/py-tree-sitter/) + measured
- `QueryCursor(...).captures(node)` returns `dict[str, list[Node]]` — capture name to list of nodes, not a
  list of pairs. This is the 0.25+ shape and is what the code below depends on. — measured

### Inferences (the design)

```
# requirements.txt additions
tree-sitter==0.25.2
tree-sitter-javascript==0.25.0
```

`0.26.1` also works (verified) but 0.25.2 is the conservative pin: it is the newest release in the line
whose API the code below is written against, and `0.26` is recent enough that a grammar/runtime ABI
surprise is cheaper to avoid than to debug. Do **not** use a floor-only spec: the audit already notes
"node names are not stable across releases"
(`documentation/14-stack-support-validation.md:134`), and an unpinned grammar bump silently changes
query results, which here means silently wrong route tables.

```python
# src/extract/ts_runtime.py  — shared parser substrate (also the seam for
# tree-sitter-typescript later; see documentation/14-stack-support-validation.md:134)
from __future__ import annotations
from functools import lru_cache
from tree_sitter import Language, Parser, Query, QueryCursor, Node
import tree_sitter_javascript as tsjs

@lru_cache(maxsize=1)
def js_language() -> Language:
    return Language(tsjs.language())

def parse(source: bytes) -> "tree_sitter.Tree":
    # One Parser per call is cheap and avoids any thread/reuse question;
    # tree-sitter is error-tolerant, so a syntactically broken file still
    # yields a usable tree with ERROR nodes rather than raising.
    return Parser(js_language()).parse(source)

@lru_cache(maxsize=256)
def compiled(query_src: str) -> Query:
    return Query(js_language(), query_src)

def captures(query_src: str, node: Node) -> dict[str, list[Node]]:
    """0.25+ API: Query is built from (language, source) and executed by a
    QueryCursor. In 0.24 and earlier this was Language.query(...).captures(...)
    — if a future bump moves it again, this function is the only edit site."""
    return QueryCursor(compiled(query_src)).captures(node)

def matches(query_src: str, node: Node) -> list[tuple[int, dict[str, list[Node]]]]:
    """Use matches(), not captures(), whenever two captures must be known to
    belong to the SAME pattern instance — e.g. a call's callee and its
    argument list. captures() flattens that relationship away and is the
    single most common source of cross-wired results."""
    return QueryCursor(compiled(query_src)).matches(node)

def text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")

def line_range(node: Node) -> tuple[int, int]:
    """1-indexed inclusive, matching ExtractedGoFunction.line_range and what
    trim_snippet()/visual cues expect. Byte-accurate — this is the whole point:
    it removes the brace-counting approximation in
    go_extractor._find_matching_brace_end_line and ts_extractor's equivalent."""
    return (node.start_point[0] + 1, node.end_point[0] + 1)
```

Reading the file: parse **bytes**, not `str`. `common.read_lines()` returns `list[str]` and the record
builders join them — keep that for snippets (so `trim_snippet` and redaction are unchanged) but hand the
parser `(root / path).read_bytes()`, because tree-sitter node offsets are byte offsets and a non-ASCII
identifier or a comment with an em dash shifts every column if you round-trip through `str`.

### Gaps
- The published py-tree-sitter docs index gives no signatures and no changelog note about `captures`
  moving to `QueryCursor`; the 0.24-vs-0.25 difference above is from measurement, so treat the exact
  version at which it moved as "0.25 or earlier within 0.25" rather than a cited boundary.
- No prebuilt wheel exists for a platform outside the list above (e.g. linux ppc64le); such a host needs a
  C compiler. Not checked whether CI runs anywhere exotic.

---

## Part B.2 — Node names and real S-expression queries

### Takeaway
Every query below was compiled and executed against a fixture containing the real Express forms; the
capture counts and sample texts are measured output, not illustration. Two gotchas: an arrow function with
a single unparenthesised parameter uses the field `parameter:` (singular, `(identifier)`), **not**
`parameters: (formal_parameters)`, so a one-pattern query silently misses `x => …`; and a string's text
lives in a child `(string_fragment)`, so matching `(string) @s` and reading `.text` gives you the quotes.

### Cited Findings (all measured — executed query, observed captures)
| purpose | query | measured result |
|---|---|---|
| function declaration | `(function_declaration name: (identifier) @name parameters: (formal_parameters) @params body: (statement_block) @body) @fn` | 4 caps; `name='helper'`, `params='(id)'` |
| arrow, parenthesised params | `(arrow_function parameters: (formal_parameters) @params) @fn` | matched `async (req, res) => {…}` |
| arrow, single bare param | `(arrow_function parameter: (identifier) @p) @fn` | matched `x => x + 1`, `p='x'` |
| function expression | `(function_expression parameters: (formal_parameters) @params) @fn` | matched both `function (req,res){}` and `function (err,req,res,next){…}` |
| method definition | `(method_definition name: (property_identifier) @name parameters: (formal_parameters) @params) @m` | matched `async index(req, res) {}` |
| class declaration | `(class_declaration name: (identifier) @name body: (class_body) @body) @cls` | `name='Ctrl'` |
| `require('literal')` only | `(call_expression function: (identifier) @f arguments: (arguments (string (string_fragment) @mod)) (#eq? @f "require")) @call` | matched `require('express')`; **did not** match `require(path.join(__dirname,'x'))` |
| any member call (`app.get`, `router.use`, `.route().get()`) | `(call_expression function: (member_expression object: (_) @obj property: (property_identifier) @prop) arguments: (arguments) @args) @call` | 48 caps on the fixture; `obj='express'`/`prop='Router'`, and `obj="router.route('/x')"` for the chained form |
| variable declarator | `(variable_declarator name: (identifier) @name value: (_) @value) @vd` | `name='UserSchema'`, `value='new Schema({…})'` |
| ESM import | `(import_statement source: (string (string_fragment) @src)) @imp` | `src='node-fetch'` |
| dynamic import | `(call_expression function: (import)) @dyn` | matched `import('./dyn.js')` |
| object literal pair | `(object (pair key: (_) @k value: (_) @v)) @obj` | 13 caps; nested `{ type: …, ref: 'User' }` captured as its own object |
| comment / JSDoc | `(comment) @c` | matched `/** @param {string} id */` |
| `new Schema({…})` | `(new_expression constructor: (_) @ctor arguments: (arguments) @args) @new` | `ctor='Schema'` |
| export statement | `(export_statement) @e` | matched `export default router;` and `export const thing = 2;` |
| re-export source | `(export_statement source: (string (string_fragment) @s)) @e` | matched `export { a, b } from './m'`, `s='./m'` |
| `module.exports = …` / `exports.foo = …` | `(assignment_expression left: (member_expression) @lhs right: (_) @rhs) @assign` | `lhs='module.exports'`, `lhs='exports.other'` |
| regex-literal route path | `(regex) @re` | matched `/.*fly$/` |
| template-literal argument | `(call_expression arguments: (arguments (template_string) @t)) @c` | matched `` app.use(`/api/${ver}`, r) `` |
| handler array | `(call_expression arguments: (arguments (array) @arr)) @c` | matched `app.get('/a', [cb0, cb1], final)` |
| `formal_parameters` arity | count `node.named_children` of the `formal_parameters` node | 2 / 3 / 4 as written; this is the middleware classifier |

- The chained form's structure, dumped from the real tree:
  `router.route('/books/:id').get(getBook).post(createBook).all(guard)` nests as
  `call_expression → member_expression → call_expression → member_expression → call_expression → member_expression(router.route) + arguments`,
  with each `property_identifier` (`get`, `post`, `all`) hanging off the member_expression at its own level.
  Measured. **So the chain is walked by descending `function:` → `object:` repeatedly, collecting
  `(property_identifier, arguments)` pairs, until the innermost `member_expression` whose property is
  `route` — whose `arguments` hold the path.**

### Inferences
- Use `matches()` for anything where callee and argument must stay paired (route registration, mounts);
  use `captures()` only for independent inventories (comments, classes).
- Do not try to express "is this a route method" in the query via `#match?` on the property name. Query
  once for *all* member calls, then filter in Python against a set — the set is also where Express 5's
  method list and `all` live, and it is testable.
- A `(string)` node with a template that has no substitution still parses as `template_string`, so the
  literal-path test is `node.type == "string"` **or** (`template_string` with zero
  `template_substitution` children). Anything else is non-literal → `assumed=True`.

### Gaps
- Node names for JSX/TSX are in `tree-sitter-typescript`, not this grammar. An Express repo with a
  React client in the same tree needs that second grammar for the client files; out of scope here.
- Flow/TypeScript annotations in `.js` files (`// @flow`) are not parsed by this grammar and will show up
  as ERROR nodes. Not measured how badly.

---

## Part B.3 — Module system resolution, imports, and exported-ness (including the real `module.exports = router` bug)

### Takeaway
A `.js` file's module system is a *project* fact, read from the nearest enclosing `package.json` `"type"`,
so the resolution table must be built before any file is parsed. And one correction to the brief:
**Node's CommonJS extensionless resolution does not try `.mjs` or `.cjs`** — only `X`, `X.js`, `X.json`,
`X.node`, then the directory's `package.json` `main`, then `X/index.js|.json|.node`. A `.cjs` or `.mjs`
target must be written with its extension.

### Cited Findings
- `LOAD_AS_FILE(X)`: "1. If X is a file, load X as its file extension format. STOP 2. If X.js is a file …
  3. If X.json is a file … 4. If X.node is a file …". `LOAD_INDEX(X)`: "1. If X/index.js is a file … 2. If
  X/index.json … 3. If X/index.node …". For a relative path the order is the exact name, `.js`, `.json`,
  `.node`, then `LOAD_AS_DIRECTORY` (which consults `X/package.json` `"main"` first, then `LOAD_INDEX`).
  The pseudocode "contains no `.mjs` or `.cjs` steps", and: "When loading a file that has a different
  extension (e.g. `.cjs`), its full name must be passed to `require()`, including its file extension". —
  [Node: modules (CommonJS)](https://nodejs.org/api/modules.html)
- The same page's `LOAD_AS_FILE` step 2 resolves the module *format* by finding "the closest package scope
  SCOPE to X" and reading its `"type"`: `"module"` → ESM, `"commonjs"` → CJS; with no scope or no `"type"`
  it is CommonJS "unless the file contains syntax that errors unless it is evaluated as an ES module".
  `.cjs` is always CommonJS; `.mjs` is "reserved for ECMAScript Modules". —
  [Node: modules](https://nodejs.org/api/modules.html)
- The background research recorded the same rule from a mirror of the packages page: "`.mjs` is always ES
  module and `.cjs` is always CommonJS. A `.js` file follows the package's `"type"` field"
  (`documentation/14-stack-support-validation.md:107`, citing
  [Node packages](https://www.mintlify.com/nodejs/node/api/packages)). Note that mirror is not nodejs.org;
  the primary page above says the same thing, so prefer it.
- Measured: the literal-only `require` query above matched `require('express')` and skipped
  `require(path.join(__dirname,'x'))` — i.e. non-literal specifiers are excluded structurally, which is
  exactly the behaviour the honesty stance wants (omit rather than guess).

### Inferences (the design)

**Module-type table (prepass, once per repo).**

```python
# src/extract/express_project.py
DEFAULT_TYPE = "commonjs"   # Node: absent "type" means CommonJS

def build_module_type_table(root: Path) -> dict[Path, str]:
    """directory -> declared "type", for every package.json in the tree.
    Sparse: only directories that HAVE a package.json appear."""
    table = {}
    for pj in root.rglob("package.json"):
        if any(part in IGNORED_DIR_NAMES for part in pj.relative_to(root).parts):
            continue
        try:
            table[pj.parent] = json.loads(pj.read_text(encoding="utf-8")).get("type") or DEFAULT_TYPE
        except (OSError, json.JSONDecodeError):
            table[pj.parent] = DEFAULT_TYPE
    return table

def module_system_for(path: Path, table: dict[Path, str], root: Path) -> str:
    """.mjs -> esm, .cjs -> cjs, otherwise the NEAREST enclosing package.json's
    "type", walking up and stopping at root. Not a content sniff: a file using
    only require() in a "type":"module" package is a crash, not CommonJS, and
    reporting it as CommonJS would hide a real defect."""
    if path.suffix == ".mjs":
        return "esm"
    if path.suffix == ".cjs":
        return "cjs"
    current = path.parent
    while True:
        if current in table:
            return "esm" if table[current] == "module" else "cjs"
        if current == root or current.parent == current:
            return "cjs"
        current = current.parent
```

**Extensionless specifier resolution (Node's order, reimplemented).**

```python
# Node modules.md LOAD_AS_FILE / LOAD_AS_DIRECTORY / LOAD_INDEX order.
# .mjs/.cjs are NOT in Node's extension list; they are only resolved when the
# specifier spells them out. The two trailing candidates marked PRAGMATIC are
# my addition for ESM-by-extension projects and MUST be reported assumed=True.
CJS_FILE_EXTS   = ["", ".js", ".json", ".node"]
INDEX_BASENAMES = ["index.js", "index.json", "index.node"]
PRAGMATIC_EXTS  = [".mjs", ".cjs"]

def resolve_specifier(from_file: Path, spec: str, root: Path) -> tuple[Path | None, bool, str | None]:
    """Resolve a relative/absolute specifier to a file on disk.
    Returns (path, assumed, note). assumed=True means the hit came from a
    candidate Node itself would not try, or nothing resolved."""
    if not spec.startswith("."):
        return None, False, None          # bare specifier: a package, not our code
    base = (from_file.parent / spec).resolve()

    for ext in CJS_FILE_EXTS:
        cand = base if ext == "" else base.with_name(base.name + ext)
        if cand.is_file():
            return cand, False, None
    if base.is_dir():
        pj = base / "package.json"
        if pj.is_file():
            try:
                main = json.loads(pj.read_text(encoding="utf-8")).get("main")
            except (OSError, json.JSONDecodeError):
                main = None
            if main and (base / main).is_file():
                return (base / main), False, None
        for name in INDEX_BASENAMES:
            if (base / name).is_file():
                return (base / name), False, None
    for ext in PRAGMATIC_EXTS:            # ESM-by-extension projects
        cand = base.with_name(base.name + ext)
        if cand.is_file():
            return cand, True, (f"Specifier {spec!r} resolved to {cand.name} by trying .mjs/.cjs, which "
                                "Node's CommonJS resolver does not do. Confirm the project's loader.")
    return None, True, (f"Specifier {spec!r} from {from_file.name} did not resolve to a file in this "
                        "repo; any route mounted through it has an unknown prefix.")
```

ESM note: bare `import './x'` without an extension is **not** resolvable by Node's ESM loader at all
(the CJS pseudocode above is the CommonJS algorithm). Treat an extensionless ESM specifier that only
resolves via `PRAGMATIC_EXTS` as `assumed=True` with the note above — it may mean a bundler is in play.

**Imports.** Three query families, one normalised record:

```python
Q_REQUIRE = """(variable_declarator
  name: (_) @binding
  value: (call_expression
            function: (identifier) @f
            arguments: (arguments (string (string_fragment) @spec))
            (#eq? @f "require"))) @decl"""

Q_REQUIRE_BARE = """(call_expression
  function: (identifier) @f
  arguments: (arguments (string (string_fragment) @spec))
  (#eq? @f "require")) @call"""          # covers inline app.use('/x', require('./y'))

Q_IMPORT = """(import_statement source: (string (string_fragment) @spec)) @imp"""
Q_DYNAMIC_IMPORT = """(call_expression
  function: (import)
  arguments: (arguments (string (string_fragment) @spec))) @dyn"""
```

`@binding` must accept `(identifier)` *and* `(object_pattern)` — `const { Schema, model } = require('mongoose')`
is the dominant Mongoose form and a query that only takes `(identifier)` drops it (hence `(_) @binding`).
For `Q_IMPORT`, read the `import_clause` children for the local names (`import express from 'express'`
vs `import { Router } from 'express'` vs `import * as e from 'express'`). A dynamic `import()` with a
non-literal specifier is omitted and recorded as a known-unknown note, never guessed.

**Exported-ness — and the real bug.** Build an **export map**, not a boolean:

```python
@dataclass
class ExportMap:
    default: str | None = None              # local name bound to the module's default export
    named: dict[str, str] = field(default_factory=dict)   # exported name -> local name
    star_from: list[str] = field(default_factory=list)    # export * from './x'
    kind: str = "none"                      # "cjs" | "esm" | "mixed" | "none"
    notes: list[str] = field(default_factory=list)

def record_cjs_assignment(em: ExportMap, lhs: str, rhs_local: str | None) -> None:
    """Handles module.exports = x / module.exports.foo = x / exports.foo = x.

    THE BUG: `module.exports = router` REPLACES the exports object, so a later
    `exports.helper = helper` writes to the ORPHANED original object and is not
    exported at runtime — `require(...).helper` is undefined. A naive extractor
    unions both and reports `helper` as part of the module's API, so the
    narration describes a symbol the consumer cannot reach. Model it as
    assignment order with a replacement marker, and when the orphan pattern is
    seen, DROP the orphaned names from `named` and emit a note. This is a real
    defect in the code being explained, and saying so is the most valuable
    sentence the narration can produce about that file."""
    if lhs == "module.exports":
        if em.named or em.default:
            em.notes.append(
                "`module.exports = …` here replaces the exports object. Any `exports.X = …` or "
                "`module.exports.X = …` that ran BEFORE this line is discarded at runtime and is "
                f"not importable (dropped: {sorted(em.named)}). Likely a bug in the source.")
        em.named.clear()
        em.default, em.kind = rhs_local, "cjs"
        em.replaced_at_line = ...           # keep the line; the narration should point at it
    elif lhs.startswith(("module.exports.", "exports.")):
        name = lhs.split(".")[-1]
        if em.default is not None and em.replaced_at_line is not None and line > em.replaced_at_line:
            em.named[name] = rhs_local      # AFTER the replacement: this DOES export (on the new object)
        elif em.default is not None:
            em.notes.append(f"`{lhs}` is assigned before `module.exports = …` and is therefore dropped.")
        else:
            em.named[name] = rhs_local
        em.kind = "cjs"
```

The ordering detail is what makes this correct and is worth stating plainly: `exports.foo = …` **after**
`module.exports = router` mutates the *router function object*, so `require(...).foo` does work (routers
are functions and take properties) — but `exports.foo = …` **before** it is lost. So the note must be
conditioned on line order, not on co-occurrence. Both directions deserve a narration sentence; only the
"before" case is a silent drop.

ESM side: `export default X` → `default`; `export const a = …` / `export function f(){}` → `named`
(local name == exported name); `export { a as b }` → `named["b"] = "a"`; `export * from './x'` →
`star_from` plus a note that the re-exported names are unknown without resolving `./x`
(resolve it when it is in-repo, mark assumed when not). `kind = "mixed"` if both CJS and ESM markers
appear in one file — that is a hard runtime error in a `"type":"module"` package and must be reported,
not reconciled.

### Gaps
- `nodejs.org/api/esm.html` was blocked in the earlier research round and I did not re-fetch it, so the
  precise ESM resolution algorithm (as opposed to the "no extensionless" rule) is uncited here.
- Conditional exports (`"exports"` maps with `import`/`require` conditions) are not handled by the
  resolver above. They matter for third-party packages, not for in-repo relative specifiers, which is
  all the mount graph needs.

---

## Part B.4 — Routes: the two-pass mount-graph design

### Takeaway
A route's full URL is the concatenation of every prefix on the chain of `app.use(prefix, router)` /
`router.use(prefix, sub)` calls, and those calls are almost always in different files from the route.
So: pass 1 builds a per-file symbol table (which identifier holds a Router, what the file exports, what
it imports and from where); pass 2 walks the mount graph from each `express()` instance, composing
prefixes transitively across files. Any link that cannot be resolved to a literal makes the whole path
`assumed=True` with a note naming the exact unresolved identifier — and the project's stance says
refusing to state a path beats stating a wrong one.

### Cited Findings
- "The app will now be able to handle requests to `/birds` and `/birds/about`" for
  `const birds = require('./birds'); app.use('/birds', birds);` where the route file writes `'/about'`. —
  [Express routing guide](https://expressjs.com/en/guide/routing.html)
- `app.route('/book').get(…).post(…).put(…)` is documented as "a chainable route handler for a route
  path"; `app.all('/secret', …)` matches every HTTP method; handler arrays and mixed forms
  (`app.get('/example/c', [cb0, cb1, cb2])`, `app.get('/example/d', [cb0, cb1], fn, fn)`) are documented,
  and "each callback except the last must call `next()`"; regex-literal paths `app.get(/a/, …)` and
  `app.get(/.*fly$/, …)` are valid. — [Express routing guide](https://expressjs.com/en/guide/routing.html)
- Express 5 path syntax: "The wildcard `*` must have a name … use `/*splat` instead of `/*`";
  "`*splat` matches any path without the root path. If you need to match the root path as well `/`, you
  can use `/{*splat}`, wrapping the wildcard in braces"; "The optional character `?` is no longer
  supported, use braces instead" (`'/:file{.:ext}'`); "Regexp characters are not supported"; reserved
  characters `()[]?+!` must be escaped; "Parameter names now support valid JavaScript identifiers, or
  quoted like `:"this"`". Applies to `app.all`, `app.use`, `app.METHOD`, `router.all`, `router.METHOD`,
  `router.use`. — [Express 5 migration guide](https://expressjs.com/en/guide/migrating-5.html)
- `next('route')`: "If you have a route handler with multiple callback functions, you can use the `route`
  parameter to skip to the next route handler", and "any remaining handlers in `app` for
  `/a_route_behind_paywall` would continue to be executed" — i.e. two declarations of the same path are
  both legitimate and both reachable. — [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- `Router({ mergeParams: true })` is required for a sub-route to see a parent route's path parameters. —
  [Express routing guide](https://expressjs.com/en/guide/routing.html)
- Nothing in the ecosystem does this statically: `express-list-endpoints` "needs a live app instance",
  warns "before call this script the router or app must have the endpoints registered", and is Express 4
  only. — [express-list-endpoints](https://github.com/AlbertoFdzM/express-list-endpoints)

### Inferences (the design)

**Pass 1 — per-file symbol table.** One parse per file, no cross-file knowledge used.

```python
@dataclass
class RouterBinding:
    local_name: str            # 'router'
    origin: str                # "express.Router" | "express()" | "imported" | "param" | "unknown"
    from_file: str | None      # set when origin == "imported"
    decl_line: int

@dataclass
class RouteDecl:
    method: str                # "GET" ... or "ALL"
    local_path: str | None     # the literal at the call site; None if non-literal
    path_is_literal: bool
    path_source: str           # verbatim source text of the path argument, for the note
    router_local: str          # which binding it was registered on
    handler_name: str | None   # after async-wrapper unwrap
    handler_line_range: tuple[int, int] | None
    middleware_names: list[str]        # positional, in registration order
    registration_line: int
    order_index: int           # statement index within the file: ORDER IS SEMANTICS

@dataclass
class MountDecl:
    parent_local: str          # 'app' or 'router'
    prefix: str | None         # literal prefix, or None
    prefix_is_literal: bool
    prefix_source: str
    child_expr: str            # 'usersRouter' | "require('./users')" | 'express.json()'
    child_kind: str            # "identifier" | "inline_require" | "call" | "function" | "unknown"
    child_local: str | None
    order_index: int
    line: int

@dataclass
class FileSymbols:
    path: str
    module_system: str                     # "cjs" | "esm"
    express_locals: list[str]              # identifiers holding an express() app
    routers: dict[str, RouterBinding]
    imports: dict[str, tuple[str, bool]]   # local name -> (resolved repo-relative path, assumed)
    exports: ExportMap
    routes: list[RouteDecl]
    mounts: list[MountDecl]
    middleware: list["MiddlewareDecl"]
```

Recognising a Router/app binding, from the verified `variable_declarator` + member-call queries:
`const app = express()` → `express_locals` (match a `call_expression` whose `function:` is the identifier
bound to the `express` package import — not the literal name `app`, exactly as `go_extractor`'s
`FIBER_APP_RE` learned to match `fiber.New()` rather than assume `app`); `const router = express.Router()`
or `Router()` (when `Router` was destructured from the express import) → `routers`;
`const r = require('./routes/users')` where the target's `ExportMap.default` is itself a router →
`origin="imported"`. A router bound to a function parameter (`module.exports = function(router){…}`)
→ `origin="param"`, which pass 2 must treat as unresolvable.

**Pass 2 — the mount-graph resolver.** This is the load-bearing code.

```python
# src/extract/express_routes.py
from dataclasses import dataclass

@dataclass
class ResolvedRoute:
    method: str
    path: str                  # full composed path, or the best-known partial
    handler: str | None
    static_or_dynamic: str     # "static" | "dynamic"
    routing_library: str       # "express"
    protected: bool
    assumed: bool
    note: str | None
    mount_chain: list[str]     # ["app.js:/api", "routes/index.js:/users"] — the evidence
    middleware_chain: list[str]
    file_path: str
    line: int

MOUNT_UNRESOLVED_NOTE = (
    "Mount prefix at {where} is not a string literal (source: `{src}`); the full URL of this route "
    "cannot be determined statically. The path shown is the route's own path with every prefix this "
    "pass COULD resolve. Verify against the running app (e.g. the output of a request log or an "
    "express-list-endpoints run on a live instance) before relying on it."
)

def resolve_routes(files: dict[str, FileSymbols], root) -> list[ResolvedRoute]:
    """Walk outward from every express() app, composing prefixes.

    Why a walk and not a lookup: a prefix is a property of the PATH THROUGH
    the graph, not of the router. The same router module mounted twice
    (app.use('/api/v1', users); app.use('/api/v2', users)) yields two distinct
    full paths for every route in it, and a one-prefix-per-router model reports
    one of them and silently loses the other. Mounting the same router twice is
    legal and is how versioned APIs are usually built, so this is not an edge
    case.

    Cycle safety: the visited key is (file, router_local, prefix) rather than
    the router alone, precisely because the same router is legitimately
    revisited under a different prefix. A repeated (file, router, prefix)
    triple is a real cycle (a router mounted on itself) and is cut with a note.
    """
    out: list[ResolvedRoute] = []

    def router_target(fs: FileSymbols, mount: MountDecl) -> tuple[FileSymbols | None, str | None, str | None]:
        """Follow a mount's child to the (file, router_local) it names.
        Returns (file_symbols, router_local, unresolved_reason)."""
        if mount.child_kind == "inline_require":
            # app.use('/api', require('./routes'))
            target, assumed, note = mount.resolved_child_path, mount.child_assumed, mount.child_note
            if target is None:
                return None, None, note
            tfs = files.get(target)
            if tfs is None:
                return None, None, f"{mount.child_expr} resolved to {target}, which was not parsed."
            return tfs, (tfs.exports.default or None), (None if tfs.exports.default else
                f"{target} does not export a router as its default export; its export map is "
                f"{tfs.exports.named or 'empty'}.")
        if mount.child_kind == "identifier":
            local = mount.child_local
            if local in fs.routers and fs.routers[local].origin != "imported":
                return fs, local, None                      # router defined in this same file
            if local in fs.imports:
                target, assumed = fs.imports[local]
                tfs = files.get(target)
                if tfs is None:
                    return None, None, f"`{local}` imports {target}, which was not parsed."
                if tfs.exports.default:
                    return tfs, tfs.exports.default, None
                return None, None, (f"`{local}` imports {target}, but that module's default export is "
                                    f"not a router (exports: {sorted(tfs.exports.named)}).")
            return None, None, f"`{local}` is not a router or import known in {fs.path}."
        return None, None, f"Mount child `{mount.child_expr}` is not a resolvable router reference."

    def join(prefix: str, local: str) -> str:
        """Express concatenates mount prefix + route path. Normalise exactly one
        slash at the seam and never emit a trailing slash except for root."""
        a = (prefix or "").rstrip("/")
        b = local or "/"
        if not b.startswith("/"):
            b = "/" + b
        joined = a + b
        return joined if joined != "" else "/"

    def walk(fs: FileSymbols, router_local: str, prefix: str, prefix_assumed: bool,
             chain: list[str], mw: list[str], notes: list[str], visited: set) -> None:
        key = (fs.path, router_local, prefix)
        if key in visited:
            notes = notes + [f"Mount cycle detected at {fs.path}:{router_local} under {prefix!r}; "
                             "this branch was cut and may be incomplete."]
            _emit_cut(out, fs, router_local, prefix, notes)
            return
        visited = visited | {key}

        # Middleware and routes in STATEMENT ORDER — order is Express semantics.
        timeline = sorted(fs.middleware + fs.routes + fs.mounts, key=lambda d: d.order_index)
        local_mw = list(mw)

        for decl in timeline:
            if isinstance(decl, MiddlewareDecl) and decl.router_local == router_local:
                local_mw.append(decl.name)
                continue
            if isinstance(decl, RouteDecl) and decl.router_local == router_local:
                full = join(prefix, decl.local_path or "")
                assumed = prefix_assumed or not decl.path_is_literal
                rn = list(notes)
                if not decl.path_is_literal:
                    rn.append(f"Route path at {fs.path}:{decl.registration_line} is not a string "
                              f"literal (source: `{decl.path_source}`); path reported as the prefix only.")
                out.append(ResolvedRoute(
                    method=decl.method,
                    path=full if decl.path_is_literal else (prefix or "/"),
                    handler=decl.handler_name,
                    static_or_dynamic=_classify_path(decl.local_path),
                    routing_library="express",
                    protected=_looks_protected(local_mw + decl.middleware_names),
                    assumed=assumed,
                    note=" ".join(rn) or None,
                    mount_chain=list(chain),
                    middleware_chain=local_mw + decl.middleware_names,
                    file_path=fs.path,
                    line=decl.registration_line))
                continue
            if isinstance(decl, MountDecl) and decl.parent_local == router_local:
                tfs, tlocal, reason = router_target(fs, decl)
                child_prefix = join(prefix, decl.prefix or "") if decl.prefix_is_literal else prefix
                child_assumed = prefix_assumed or not decl.prefix_is_literal
                child_notes = list(notes)
                if not decl.prefix_is_literal:
                    child_notes.append(MOUNT_UNRESOLVED_NOTE.format(
                        where=f"{fs.path}:{decl.line}", src=decl.prefix_source))
                if tfs is None or tlocal is None:
                    if reason:               # a mount we cannot follow: say so, mount nothing
                        _emit_unfollowable(out, fs, decl, child_prefix, child_notes + [reason])
                    continue                 # express.json() etc. land here with reason=None
                walk(tfs, tlocal, child_prefix, child_assumed,
                     chain + [f"{fs.path}:{decl.prefix if decl.prefix_is_literal else '<non-literal>'}"],
                     local_mw, child_notes, visited)

    for fs in files.values():
        for app_local in fs.express_locals:
            walk(fs, app_local, "", False, [f"{fs.path}:<app>"], [], [], set())
    return out
```

**Registration forms — what pass 1 must produce for each.**

| form | handling |
|---|---|
| `app.get/post/put/delete/patch/head/options('/p', …)` | the base case; method from the `property_identifier` |
| `app.all('/p', h)` | emit one `RouteDecl` per method in a documented set with `method="ALL"` and a note that it matches every method ([routing guide](https://expressjs.com/en/guide/routing.html)) |
| `router.route('/x').get(a).post(b)` | walk the chain structure measured in B.2: descend `function:`→`object:` collecting `(property, arguments)` pairs until the innermost member whose property is `route`; its argument is the shared path. Emit one `RouteDecl` per collected method, all with the same `local_path` |
| handler arrays `app.get('/a',[cb0,cb1],final)` | flatten the `(array)` into `middleware_names` in order; the **last** callable positional argument is the handler (documented: "each callback except the last must call `next()`") |
| regex-literal path `app.get(/.*fly$/, h)` | `path_is_literal=False`, `path="<regex>"`, `static_or_dynamic="dynamic"`, `assumed=True`, note carrying the regex source verbatim. Do **not** attempt to render it as a URL |
| array of paths `app.get(['/a/:s','/b/:s'], h)` | one `RouteDecl` per literal element (the Express 5 replacement for regexp characters in strings) |
| Express 5 `'/*splat'`, `'/{*splat}'`, `'/:file{.:ext}'`, `'/order{/:id}'` | literal strings: keep verbatim as the path; classify dynamic if it contains `:` or `*`; add a note naming the Express major (read from `package.json`) so the narration explains braces/splat correctly, since `'/*'` alone is an Express 4 form and an error in 5 |
| two declarations of the same path (`next('route')`) | emit **both**, in `order_index` order, and attach a note to the pair: both are reachable; the first may hand off with `next('route')`. Deduplicating them loses real behaviour ([error handling guide](https://expressjs.com/en/guide/error-handling.html)) |
| `Router({ mergeParams: true })` | record on the `RouterBinding`; when a parent mount prefix contains `:param`, note whether `mergeParams` is set — without it the child cannot read the parent's params ([routing guide](https://expressjs.com/en/guide/routing.html)) |
| non-literal prefix `app.use(\`/api/${ver}\`, r)` or `app.use(config.base, r)` | `prefix_is_literal=False`; children are still walked (so their own paths are known) but every route under them is `assumed=True` with `MOUNT_UNRESOLVED_NOTE` naming the file, line and the verbatim source of the prefix expression, and `path` is the resolved prefix only, never a fabricated full URL |

**What to emit when a prefix is non-literal** — concretely, the note text above:
"Mount prefix at `app.js:17` is not a string literal (source: `` `/api/${ver}` ``); the full URL of this
route cannot be determined statically. The path shown is the route's own path with every prefix this pass
COULD resolve. Verify against the running app before relying on it." Plus `assumed=True` and, per the
Go extractor's precedent (`go_extractor.py:265-295`, every route `assumed=True` unconditionally), a
record-level note. If a *majority* of routes in a record are assumed, the record's `notes` should say the
route table is not trustworthy as a whole — refusing to narrate a route table beats emitting a wrong one.

### Gaps
- `mergeParams` affects `req.params` visibility, not the URL, so its narration value is asserted here, not
  measured.
- Whether `app.all` should fan out to a fixed method list or stay a single `ALL` row is a presentation
  decision I cannot settle from the docs; the docs only say it matches all methods.
- `app.use(router)` with no prefix (mount at root) is covered by `join(prefix, "")`, but I did not verify
  Express's exact behaviour for a mount prefix of `''` vs `'/'`.

---

## Part B.5 — Middleware: arity classification and order

### Takeaway
Classify by **arity**, never by name: 2–3 declared parameters = request middleware, exactly 4 = error
handler, a call expression in the argument slot = a factory invocation (`express.json()`). Order is
semantics and must be preserved as statement order composed along the mount graph — and an error handler
registered *before* the routes it is meant to protect never fires, which is the single most narratable
defect in an Express codebase.

### Cited Findings
- "Define error-handling middleware functions in the same way as other middleware functions, except
  error-handling functions have four arguments instead of three: `(err, req, res, next)`." —
  [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- "You define error-handling middleware last, after other `app.use()` and routes calls". —
  [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- "If you pass anything to the `next()` function (except the string `'route'`), Express regards the
  current request as being an error and will skip any remaining non-error handling routing and middleware
  functions." — [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- The audit's reading of the middleware guide: "Error-handling middleware always takes *four* arguments.
  You must provide four arguments to identify it as an error-handling middleware function" —
  `documentation/14-stack-support-validation.md:107`, citing
  [Express middleware](https://expressjs.com/en/guide/using-middleware.html)
- Measured: `(function_expression parameters: (formal_parameters) @params)` captured both
  `function (req, res) {}` and `function (err, req, res, next) {…}` from the same file, with the
  parameter lists distinguishable by `named_children` count — so arity is a two-line check from the tree
  and, as the audit notes, "impossible from regex across a multi-line arrow with minified parameter names".

### Inferences (the design)

```python
@dataclass
class MiddlewareDecl:
    name: str                  # local identifier, or "<anonymous>"
    kind: str                  # "request" | "error" | "factory" | "router" | "unknown"
    arity: int | None          # declared parameter count; None when the callee is just a name
    router_local: str
    order_index: int           # statement index — THE field that makes this useful
    line_range: tuple[int, int]
    params: list[str]          # declared parameter names, for the narration
    assumed: bool
    note: str | None

ERROR_ARITY = 4

def classify_middleware_argument(arg_node) -> tuple[str, int | None, list[str], bool, str | None]:
    """Classify one argument of app.use(...) / a route's positional handlers.

    Arity, not name: a handler called `errorHandler` with three parameters is a
    request middleware and will never see an error, and a handler called
    `logger` with four IS an error handler and will not run on the happy path.
    Both are real bugs worth narrating, and both are invisible to a name match.
    """
    t = arg_node.type
    if t in ("function_expression", "arrow_function", "function_declaration"):
        params = _param_names(arg_node)          # [] for a bare `x =>` is handled by the `parameter:` field
        kind = "error" if len(params) == ERROR_ARITY else "request"
        return kind, len(params), params, False, None
    if t == "call_expression":
        # express.json(), cors(), morgan('dev'), rateLimit({...}) — a FACTORY:
        # the middleware's own arity lives in the library, not here.
        return "factory", None, [], True, (
            f"`{_text(arg_node)}` is a factory call; the middleware function it returns is defined in "
            "its package, so its arity (and therefore whether it is an error handler) is not visible "
            "in this repository.")
    if t == "identifier":
        return "unknown", None, [], True, (
            f"`{_text(arg_node)}` names a middleware defined elsewhere; arity resolved from its "
            "definition if that file is in this repo, otherwise unknown.")
    if t == "array":
        ...   # flatten, classify each element, preserve order
    return "unknown", None, [], True, f"Unrecognised middleware argument form: {t}."
```

For an `identifier` argument, do a second resolution step through pass 1's import map and export map:
if the name resolves to a function definition in the repo, take its real arity and replace
`kind="unknown"` with the arity-derived kind, `assumed=False`. That upgrade is where most real
`(err, req, res, next)` handlers are found, because they almost always live in `middleware/error.js`
rather than inline.

**Order.** `order_index` is the statement index of the registration within its file; the effective chain
for a route is `middleware registered on each router along the mount chain, in mount order, then that
route's own positional middleware`. That is what `ResolvedRoute.middleware_chain` in B.4 builds. Two
checks worth running and emitting as findings, because they are defects the viewer can act on:

```python
def audit_middleware_order(fs: FileSymbols) -> list[str]:
    findings = []
    first_route = min((r.order_index for r in fs.routes), default=None)
    last_mount  = max((m.order_index for m in fs.mounts), default=None)
    for mw in fs.middleware:
        if mw.kind != "error":
            continue
        later = [i for i in (first_route, last_mount) if i is not None and i > mw.order_index]
        if later:
            findings.append(
                f"The error handler at {fs.path}:{mw.line_range[0]} is registered BEFORE routes or "
                "sub-router mounts that appear later in this file. Express documents that error-handling "
                "middleware is defined last, after other app.use() and routes calls; registered here it "
                "will not catch errors from those later handlers.")
    body_parsers = [m for m in fs.middleware if m.kind == "factory"
                    and any(k in m.name for k in ("json", "urlencoded", "bodyParser"))]
    for bp in body_parsers:
        if first_route is not None and bp.order_index > first_route:
            findings.append(
                f"The body parser at {fs.path}:{bp.line_range[0]} is registered after a route; "
                "req.body will be undefined in the handlers declared above it.")
    return findings
```

These findings belong in the record's `notes` and are exactly the kind of thing the narration should say
out loud. The `middleware` array itself is the new optional field on the Express record (see A6), each
entry carrying `name`, `kind`, `arity`, `params`, `orderIndex`, `lineRange`, `assumed`, `notes`.

### Gaps
- The exact phrasing of the middleware guide's arity sentence is taken from the earlier research round's
  quotation of `https://expressjs.com/en/guide/using-middleware.html`; I verified the equivalent statement
  on the error-handling page directly but did not re-fetch the middleware page in this pass.
- Express 5's handling of a 4-arity function passed as a *route* handler (rather than via `use`) is not
  cited; I treat arity 4 as an error handler everywhere, which may over-report.

---

## Part B.6 — Async wrapper unwrapping, and the Express major version

### Takeaway
`asyncHandler(async (req,res) => …)` puts the real handler one `call_expression` deeper; without
unwrapping, the record names the handler `asyncHandler` and highlights the wrapper's line, so the
voiceover describes a function the viewer cannot find. Unwrap by descending through single-callback
call expressions until a function node is reached, keeping the wrapper names as evidence. Separately,
read Express's major version from `package.json`, because Express 5 auto-forwards async rejections and
Express 4 does not — the narration is materially different.

### Cited Findings
- Express 5, "Rejected promises handled from middleware and handlers": "Request middleware and handlers
  that return rejected promises are now handled by forwarding the rejected value as an `Error` to the
  error handling middleware… When an error is thrown in an `async` function or a rejected promise is
  `await`ed inside an async function, those errors will be passed to the error handler as if calling
  `next(err)`." The page shows the Express 4 `.then()/.catch(next)` idiom being replaced by bare
  `async`/`await`. — [Express 5 migration guide](https://expressjs.com/en/guide/migrating-5.html)
- Express (current docs) error handling: "Route handlers and middleware that return a Promise call
  `next(value)` automatically when they reject or throw an error, and `async` functions always return a
  Promise, so their errors reach Express with no extra work." But: "If the promise is not returned,
  Express does not know it exists, and you must route the error yourself by providing `next` as the final
  catch handler", and callback-API errors "are not thrown and are not part of any promise… you must pass
  them to the `next()` function yourself". — [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- "Errors that occur in synchronous code inside route handlers and middleware require no extra work." —
  [Express error handling](https://expressjs.com/en/guide/error-handling.html)
- Measured: in `router.get('/:id', auth, asyncHandler(async (req, res) => {…}))`, the arrow function is a
  child of the `arguments` of the `call_expression` whose callee is `asyncHandler`, which is itself the
  third argument of the `router.get` call — i.e. exactly one level of nesting, reachable structurally.

### Inferences (the design)

```python
WRAPPER_NAME_HINTS = ("asynchandler", "catchasync", "wrapasync", "trycatch",
                      "expressasynchandler", "ash", "handleasync")

def unwrap_handler(arg_node, max_depth: int = 4) -> tuple[object, list[str], bool, str | None]:
    """Descend through async-wrapper call expressions to the real handler.

    Returns (handler_node_or_None, wrapper_names, assumed, note).

    Algorithm, purely structural — it does NOT require the wrapper to be named
    asyncHandler, because the name varies by project and a name list is exactly
    the kind of guess this pipeline is supposed to refuse:
      1. If the node is already a function/arrow/function_expression, it is the
         handler. Done.
      2. If the node is a call_expression whose arguments contain EXACTLY ONE
         function-shaped argument, that argument is the handler one level down.
         Record the callee's name as a wrapper and recurse on it.
      3. If a call_expression's arguments contain NO function argument, it is a
         factory (express.json(), rateLimit({...})) — not a wrapper. Stop,
         return None, assumed=True, with a note naming the call.
      4. If it contains MORE THAN ONE function argument, stop and mark assumed:
         which one is the handler is a library-specific convention and guessing
         picks the wrong lines half the time.
      5. Depth cap: beyond max_depth, stop and mark assumed.
    """
    wrappers: list[str] = []
    node = arg_node
    for _ in range(max_depth):
        if node.type in ("arrow_function", "function_expression", "function_declaration"):
            return node, wrappers, False, None
        if node.type == "identifier":
            # A named handler: resolve through the import/export map elsewhere.
            return None, wrappers, False, None
        if node.type != "call_expression":
            return None, wrappers, True, f"Handler argument is a {node.type}, not a function or call."
        args = [a for a in node.child_by_field_name("arguments").named_children]
        fns = [a for a in args if a.type in ("arrow_function", "function_expression")]
        callee = _callee_name(node)
        if len(fns) == 1:
            wrappers.append(callee)
            node = fns[0]
            continue
        if not fns:
            return None, wrappers, True, (
                f"`{callee}(…)` takes no inline function, so it is a middleware factory rather than an "
                "async wrapper; the handler it returns is defined in another module.")
        return None, wrappers, True, (
            f"`{callee}(…)` takes {len(fns)} inline functions; which one is the request handler is a "
            "library-specific convention, so the handler was not identified. Verify by hand.")
    return None, wrappers, True, "Handler is nested deeper than the unwrap depth limit."
```

The handler's `name` then becomes the arrow's binding where there is one, else
`f"<anonymous handler wrapped in {wrappers[0]}>"`, and its `lineRange` is the **unwrapped function's**
`line_range`, which is what fixes the highlight. Keep `wrappers` in the record: "this handler is wrapped
in `asyncHandler`, which forwards rejections to the error middleware" is a genuinely useful sentence, and
on Express 5 the follow-up is "which Express 5 would do anyway".

**Express major version.** Read it in the detection prepass (`NodePackage.express_major`, A1) from the
semver range's leading digits, and pass it into the record so the narration branches:

- major 5 → async handlers need no wrapper; a rejected promise reaches the error middleware as if
  `next(err)` were called.
- major 4 → an unwrapped `async` handler that throws produces an **unhandled rejection**, not a 500 via
  the error middleware; this is a real defect to point out when an Express 4 repo has bare async handlers
  and no wrapper.
- unparseable or absent (`"express": "latest"`, a monorepo workspace range) → `assumed=True`, note the
  range verbatim, and say the async-error behaviour could not be determined rather than assuming either.

In both majors, state what is *not* automatic: a non-returned promise chain, and callback-style APIs,
whose errors never reach the error middleware without explicit `next(err)` — both cited above.

### Gaps
- Specific async-wrapper package names were uncited in the earlier round and remain so; the algorithm
  above is deliberately name-independent, and `WRAPPER_NAME_HINTS` should be used only to *phrase* a
  note, never to decide structure.
- Whether Express 5's rejection forwarding also covers a rejected promise returned from a 4-arity error
  handler is not cited.

---

## Part B.7 — Data models from object literals: Mongoose, Sequelize, Zod/Joi

### Takeaway
Plain JS has no types, so the request/response shapes have to come from object literals — and object
literals are precisely where a tree gains the most over regex, because the shapes nest. Three sources,
in descending reliability: Mongoose `new Schema({…})` with `ref`, Sequelize `define`/association calls,
and Zod/Joi validation schemas bound to a route, which **are** the request body contract.

### Cited Findings
- Mongoose `populate` and `ref` semantics (the relation edge an extractor should emit) —
  [Mongoose populate docs](https://github.com/automattic/mongoose/blob/master/docs/populate.md)
- Sequelize model definition and association surface (`define`, `hasMany`, `belongsTo`,
  `belongsToMany({ through })`) — [Sequelize model.js](https://github.com/sequelize/sequelize/blob/main/packages/core/src/model.js)
- The audit's conclusion on where the parser pays off most: request/response shapes "must be recovered
  from Mongoose `new Schema({…})` and `ref`, Sequelize `define`/`hasMany`/`belongsToMany` … and from
  Zod/Joi validation schemas bound to the route — all object literals, where the AST-over-regex gain is
  largest." — `documentation/14-stack-support-validation.md:107`
- Measured: `(new_expression constructor: (_) @ctor arguments: (arguments) @args)` captured
  `new Schema({ name: { type: String }, owner: { type: Schema.Types.ObjectId, ref: 'User' } })` with
  `ctor='Schema'`, and `(object (pair key: (_) @k value: (_) @v))` captured the nested
  `{ type: Schema.Types.ObjectId, ref: 'User' }` as its own object with `k='owner'` at the outer level —
  i.e. the nesting needed for `ref` extraction is directly addressable. 13 pair captures on the fixture.
- Mongoose's own documentation page (`mongoosejs.com/docs/guide.html`) was blocked in the earlier
  research round and was not re-fetched here, so the field-option vocabulary below (`type`, `required`,
  `default`, `enum`, `unique`) is from engineering knowledge, not cited.

### Inferences (the design)

```python
Q_NEW_SCHEMA = """(new_expression
  constructor: (_) @ctor
  arguments: (arguments (object) @body)) @new"""

Q_CALL_WITH_OBJECT = """(call_expression
  function: (member_expression property: (property_identifier) @prop)
  arguments: (arguments . (string (string_fragment) @name)? (object) @body)) @call"""
```

**Mongoose.** Match `Q_NEW_SCHEMA` where `@ctor` text is `Schema` or `mongoose.Schema` *and* `Schema`
traces back to the mongoose import (the destructured `const { Schema } = require('mongoose')` form, which
the `(_) @binding` choice in B.3 is what makes resolvable). For each top-level `pair` in `@body`:

- value is an identifier/member (`String`, `Date`, `Schema.Types.ObjectId`) → field type is that text.
- value is an `object` → read its own pairs: `type` → field type, `ref` (string literal) → **relation**
  `{from: <model>, field: <key>, to: <ref literal>, kind: "ref"}`, `required`/`default`/`enum`/`unique` →
  carry as field attributes.
- value is an `array` containing an object with `ref` → a one-to-many relation; mark `many=True`.
- value is anything non-literal → emit the field with `type=None`, `assumed=True`, note the source text.

The model **name** comes from the paired `mongoose.model('User', UserSchema)` call (`Q_CALL_WITH_OBJECT`'s
sibling: a `call_expression` with property `model` and a string first argument). If the schema is never
passed to `model()` in any parsed file, report the schema under its variable name with a note that the
collection name is unknown — do not infer it from the filename.

**Sequelize.** Two forms, both `Q_CALL_WITH_OBJECT`:
`sequelize.define('User', {attrs}, {options})` → model name from the string, fields from the attribute
object (`type`, `allowNull`, `defaultValue`, `primaryKey`); and `class User extends Model` with
`User.init({attrs}, {sequelize})` → model name from the class declaration, fields from `init`'s first
object. Associations are member calls on a model identifier:
`User.hasMany(Post, {foreignKey})`, `Post.belongsTo(User)`,
`User.belongsToMany(Project, { through: UserProject })` → emit
`{from, to, kind: "hasMany"|"belongsTo"|"belongsToMany", through: <identifier text or None>, foreignKey}`.
`through` is the field that makes a belongsToMany comprehensible and is a plain `pair` in the options
object.

**Zod/Joi → request body.** These bind to a route and therefore belong in the record's `inputs`, not only
`dataModels` — this is the one place an Express record can state a request contract as fact. Pattern:
a `variable_declarator` whose value is a chained member-call expression rooted at the local name bound to
the `zod`/`joi` import (`z.object({...})`, `Joi.object({...})`). Walk the chain the same way as
`router.route()` in B.4, collecting `(property, arguments)` pairs; the `object` argument's pairs are the
fields, each field's own chain giving the type (`z.string().email().optional()` → type `string`,
constraints `email`, optional). Then bind it to a route: a schema identifier appearing as an argument to a
validation middleware in a route's positional middleware (`validate(createUserSchema)`) links
`route -> schema`, and *that* is the route's request body. When a schema is defined but never bound,
report it as a data model only, with a note that no route reference was found.

A hard line: a Mongoose schema is the *database* shape and a Zod schema is the *request* shape, and they
differ (server-generated ids, timestamps, hashed passwords). Never present one as the other; label the
source on each entry.

### Gaps
- Zod and Joi API surfaces were uncited in the earlier round and remain uncited; the chain-walk is
  structural (it works whatever the method names are) but the mapping from method name to a type word is
  engineering knowledge.
- Prisma and TypeORM (both in `NODE_BACKEND_HINT_DEPS`) are not covered: Prisma's models live in a
  `.prisma` DSL file, not JS, and TypeORM's live in decorators. Both are out of scope for a JS-grammar
  extractor and should be reported as "schema defined outside the parsed JavaScript".

---

## Part B.8 — JSDoc, and what is simply unavailable

### Takeaway
A `(comment)` node starting `/**` immediately above a declaration is the only type information a plain-JS
repo offers, and it is optional and unverified. Read it where present; where absent, leave the field
`None` with a note — never synthesise a type from a parameter name.

### Cited Findings
- Measured: `(comment) @c` captured `/** @param {string} id */`; comments are ordinary named nodes, so
  "the JSDoc for declaration D" is "the previous named sibling of D, if it is a comment whose text starts
  with `/**` and whose `end_point.row` is `D.start_point.row - 1`". This is a structural adjacency test,
  which is strictly better than the existing upward text scan in
  `src/extract/function_context.py:45-99`.
- The TypeScript JSDoc reference page was blocked in the earlier research round, so the supported-tag list
  is not cited. — `documentation/research/.../express_node.md` header note

### Inferences
- Tags worth reading, in order of value to the narration: `@param {T} name - desc`, `@returns {T}`,
  `@typedef`/`@property` (a whole object shape, the JS equivalent of an interface), `@route`/`@desc`/
  `@access` (the Express community convention, often the only statement of what a route is for),
  `@deprecated`, `@throws`. Parse the brace-delimited type with a small balanced-brace reader, not a
  regex — `{Promise<Array<{id: string}>>}` nests.
- `function_context.py` currently infers export status with `signature.startswith("export")`
  (`:159-163`), which is wrong for every CommonJS file in an Express repo. Replace the call for
  `language="js"` with a lookup against the file's `ExportMap` from B.3 — tri-state
  (`default` / `named` / `not_exported`), plus the orphaned-export case as its own state.
- What is genuinely unavailable without types, and must be `None` + a note rather than guessed: the
  concrete type of any parameter without JSDoc; the response body shape (unless a Zod schema or a literal
  `res.json({...})` object is present, in which case report the literal and say it is one call site, not
  the contract); whether a handler can throw; nullability; and the relationship between `req.body` and any
  model, absent a validation schema. The honest record says "the request body shape is not stated in this
  file" — which, per the project stance, is a better sentence than a fabricated one.

### Gaps
- No cited list of JSDoc tags that type-checkers honour; the tag list above is engineering knowledge.

---

## Part B.9 — What the extractor cannot know statically

### Takeaway
Four classes of unknowable, all of which must be marked `assumed=True` with a specific note, or omitted
entirely. The precedent is already in the repo: `go_extractor.extract_routes` marks **every** route
`assumed=True` because its protection inference is file-local, and its docstring records a false positive
it caused (`go_extractor.py:265-295`).

### Cited Findings
- No static tool solves Express route extraction: `express-list-endpoints` requires a live app and is
  Express 4 only — "before call this script the router or app must have the endpoints registered". —
  [express-list-endpoints](https://github.com/AlbertoFdzM/express-list-endpoints)
- Express prescribes no project layout, so folder names carry no guaranteed meaning. —
  [Project structure for an Express REST API](https://dev.to/ccleary00/project-structure-for-an-express-rest-api-when-there-is-no-standard-way-4gk3)
- The repo's own stance, in code: "Always marked assumed=True regardless of the result, since this is
  still file-local and not real call-graph analysis." — `src/extract/go_extractor.py:265-295`

### Inferences
| unknowable | behaviour |
|---|---|
| dynamic registration in a loop — `routes.forEach(r => app[r.method](r.path, r.handler))`, `fs.readdirSync('./routes').forEach(...)` | **Omit** the routes (there is nothing literal to report) and emit a record-level note: "This file registers routes programmatically at `<file>:<line>`; the resulting route table is not statically determinable and is not included. The repository's real route table is larger than what is reported here." Pull the record's confidence down. Silence here would be worse than in any other case, because the route list *looks* complete |
| runtime-composed prefixes — `app.use(process.env.API_BASE, r)`, `app.use(config.prefix, r)` | walk children, `assumed=True`, `MOUNT_UNRESOLVED_NOTE` naming the expression verbatim (B.4) |
| handlers from a DI container / factory — `app.use('/x', container.get('UsersRouter'))`, `app.use('/x', makeRouter(deps))` | mount not followed; emit an "unfollowable mount" row carrying the prefix, `handler=None`, `assumed=True`, note naming the expression. Do **not** invent the sub-router's routes |
| conditional registration — `if (process.env.NODE_ENV !== 'production') app.use('/debug', r)` | emit the routes with a note that registration is conditional on the named expression; the route may not exist in production |
| `protected` / auth | same stance as Go: infer only from middleware names in the composed chain (`auth`, `jwt`, `requireAuth`, `passport.authenticate`), always `assumed=True`, note that it is name matching over the composed chain and not an authorisation analysis. The Go docstring's false-positive story (`AUTH_MODE` comments read as evidence auth was present) is the reason this must never be a whole-file substring scan |
| monkey-patched / re-exported app (`module.exports = app` then mounted elsewhere) | handled by the mount graph if the mounting file is parsed; if the app is exported and never mounted in-repo, note that the server entry point was not found |
| `.env`-driven base paths, reverse-proxy prefixes (nginx `location /api/`) | out of reach entirely; note once per record that any deployment-level prefix is not included, mirroring the `server.servlet.context-path` caveat flagged for Spring in `documentation/14-stack-support-validation.md:166` |

A record-level rule worth encoding: if `assumed` routes outnumber resolved ones, set the record note to
say the route table as a whole should not be trusted, and cap confidence (the existing pattern is
`confidence = min(confidence, 0.5)` for redaction in `json_builder.py`). Refusing to narrate a route
table beats emitting a wrong one.

### Gaps
- No measurement of how often each class occurs in real Express repos; the ordering above is by severity
  of a wrong answer, not by frequency.

---

## Part B.10 — Test plan (existing `tests/` style) and acceptance criteria

### Takeaway
The existing tests are plain `pytest` functions, no classes, `tmp_path` for detection
(`tests/test_project_type.py`) and inline source strings for extraction
(`tests/test_go_extractor.py`). Follow both shapes exactly, and add one multi-file fixture directory for
the cross-file mount graph, which cannot be tested from a single string.

### Cited Findings
- `tests/test_project_type.py` uses a `_write(path, content)` helper with `tmp_path`, one assertion-focused
  function per behaviour (`test_detects_react_frontend_only`, `test_two_sibling_backend_roots_is_microservice`),
  asserting on `result.frontend_stack`, `result.backend_stacks`, `result.architecture`. — read
- `tests/test_go_extractor.py` passes inline triple-quoted source to `go.extract_*` and asserts on
  dataclass fields and sets (`names == {"List","NewAlumniRepository"}`), including a dedicated
  `test_extract_routes_resolves_group_prefix`. — read
- `tests/test_feature_grouping.py:102,119,132` already locks the flat-files-in-organizing-folder fix,
  which is the Express layout. — `documentation/14-stack-support-validation.md:149`

### Inferences (the plan)

**`tests/test_project_type.py` — additions (same `_write` helper):**
```python
def test_detects_express_backend_not_frontend(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"express": "^4.18.2"}}))
    r = detect_project_type(tmp_path)
    assert r.backend_stacks == ["express"]
    assert r.frontend_stack is None          # the bug: today this is "react_or_angular"

def test_express_major_version_read_from_package_json(tmp_path): ...        # 4 vs ^5.0.0 vs "latest" -> None, assumed
def test_monorepo_client_and_server_detects_both(tmp_path): ...             # client/ react + server/ express
def test_single_package_fullstack_detects_both(tmp_path): ...               # react + express in one package.json
def test_node_backend_from_hint_deps_only_is_assumed(tmp_path): ...         # mongoose+jsonwebtoken, no express
def test_plain_package_json_still_react_or_angular(tmp_path): ...           # regression: unchanged fallback
def test_module_type_defaults_to_commonjs_when_absent(tmp_path): ...
def test_two_express_service_roots_is_microservice(tmp_path): ...
```

**`tests/test_express_extractor.py` — inline-source unit tests (Go-extractor style):**
```python
from src.extract import express_extractor as ex

def test_classifies_error_handler_by_arity_not_name():
    text = """
app.use(function logger(req, res, next) { next(); });
app.use(function (err, req, res, next) { res.status(500).end(); });
"""
    mw = ex.extract_middleware(text)
    kinds = [(m.name, m.kind, m.arity) for m in mw]
    assert ("logger", "request", 3) in kinds
    assert any(k == "error" and a == 4 for _, k, a in kinds)

def test_factory_middleware_arity_is_unknown_and_assumed():
    mw = ex.extract_middleware("app.use(express.json());")
    assert mw[0].kind == "factory" and mw[0].arity is None and mw[0].assumed is True

def test_module_exports_replacement_drops_earlier_exports():
    text = """
exports.helper = helper;
module.exports = router;
"""
    em = ex.extract_exports(text)
    assert em.default == "router"
    assert "helper" not in em.named           # the real bug: not importable at runtime
    assert any("replaces the exports object" in n for n in em.notes)

def test_exports_after_replacement_are_kept():
    text = """
module.exports = router;
module.exports.helper = helper;
"""
    em = ex.extract_exports(text)
    assert em.named == {"helper": "helper"} and em.default == "router"

def test_unwraps_async_handler_to_real_function_lines():
    text = """
router.get('/:id', asyncHandler(async (req, res) => {
  res.json(await find(req.params.id));
}));
"""
    routes = ex.extract_route_decls(text)
    assert routes[0].handler_name != "asyncHandler"
    assert routes[0].handler_line_range[0] == 2    # the arrow's line, not the wrapper's

def test_route_chain_emits_one_decl_per_method():
    routes = ex.extract_route_decls("router.route('/books/:id').get(getBook).post(createBook);")
    assert {(r.method, r.local_path) for r in routes} == {("GET", "/books/:id"), ("POST", "/books/:id")}

def test_regex_literal_path_is_assumed_and_not_rendered_as_url():
    r = ex.extract_route_decls("app.get(/.*fly$/, h);")[0]
    assert r.path_is_literal is False and "/.*fly$/" in r.path_source

def test_handler_array_order_preserved_and_last_is_handler():
    r = ex.extract_route_decls("app.get('/a', [cb0, cb1], final);")[0]
    assert r.middleware_names == ["cb0", "cb1"] and r.handler_name == "final"

def test_express5_splat_and_brace_paths_kept_verbatim():
    paths = [r.local_path for r in ex.extract_route_decls(
        "app.get('/{*splat}', h); app.get('/:file{.:ext}', h);")]
    assert paths == ["/{*splat}", "/:file{.:ext}"]

def test_two_declarations_of_same_path_both_emitted():
    routes = ex.extract_route_decls("app.get('/p', gate); app.get('/p', content);")
    assert len(routes) == 2 and [r.order_index for r in routes] == [0, 1]

def test_require_with_non_literal_specifier_is_omitted():
    imps = ex.extract_imports("const x = require(path.join(__dirname, 'y'));")
    assert imps == []            # omitted, not guessed

def test_destructured_require_binding_is_captured():
    imps = ex.extract_imports("const { Schema, model } = require('mongoose');")
    assert imps[0].spec == "mongoose" and set(imps[0].names) == {"Schema", "model"}

def test_mongoose_schema_fields_and_ref_relation():
    models = ex.extract_data_models(
        "const S = new Schema({ name: { type: String, required: true },"
        " owner: { type: Schema.Types.ObjectId, ref: 'User' } });")
    assert ("name", "String") in [(f.name, f.type) for f in models[0].fields]
    assert {"field": "owner", "to": "User", "kind": "ref"} in models[0].relations

def test_sequelize_belongs_to_many_through_captured():
    rels = ex.extract_relations("User.belongsToMany(Project, { through: UserProject });")
    assert rels[0].kind == "belongsToMany" and rels[0].through == "UserProject"

def test_jsdoc_attached_only_when_adjacent():
    doc = ex.jsdoc_for_declaration("/** @param {string} id */\nfunction f(id) {}")
    assert doc.params == [("id", "string")]

def test_error_handler_before_routes_is_reported():
    findings = ex.audit_middleware_order_text(
        "app.use(function (err, req, res, next) {});\napp.get('/a', h);")
    assert any("will not catch errors" in f for f in findings)

def test_syntactically_broken_file_does_not_raise():
    assert ex.extract_route_decls("app.get('/a', => {") is not None   # error-tolerant parse
```

**`tests/fixtures/express_mount_graph/` — the cross-file fixture (required; a string cannot express it):**
```
package.json                 {"dependencies":{"express":"^4.18.2"},"type":"commonjs"}
src/app.js                   const express=require('express'); const app=express();
                             app.use(express.json());
                             app.use('/api/v1', require('./routes'));
                             app.use('/api/v2', require('./routes'));     // same router, twice
                             app.use(process.env.ADMIN_BASE, require('./routes/admin'));
                             app.use(function (err,req,res,next){ res.status(500).end(); });
                             module.exports = app;
src/routes/index.js          const router=require('express').Router();
                             router.use('/users', require('./users'));
                             module.exports = router;
src/routes/users.js          const router=require('express').Router();
                             const auth=require('../middleware/auth');
                             router.get('/', listUsers);
                             router.route('/:id').get(getUser).put(auth, updateUser);
                             module.exports = router;
                             exports.listUsers = listUsers;              // orphaned: after replacement, kept
src/routes/admin/index.js    (a router reached only through a non-literal prefix)
src/middleware/auth.js       module.exports = function (req,res,next){ next(); };
src/models/user.js           new Schema({...ref:'Role'}) + mongoose.model('User', UserSchema)
```
Assertions:
```python
def test_mount_graph_resolves_full_paths_across_files(fixture_root):
    routes = resolve(fixture_root)
    paths = {(r.method, r.path) for r in routes if not r.assumed}
    assert ("GET", "/api/v1/users") in paths
    assert ("GET", "/api/v1/users/:id") in paths
    assert ("PUT", "/api/v1/users/:id") in paths

def test_router_mounted_twice_yields_both_version_prefixes(fixture_root):
    paths = {r.path for r in resolve(fixture_root)}
    assert "/api/v1/users" in paths and "/api/v2/users" in paths

def test_extensionless_require_resolves_to_index_js(fixture_root):
    # require('./routes') -> src/routes/index.js, per Node LOAD_INDEX
    assert any(r.mount_chain and "routes" in r.mount_chain[1] for r in resolve(fixture_root))

def test_non_literal_prefix_marks_routes_assumed_with_note(fixture_root):
    admin = [r for r in resolve(fixture_root) if "admin" in r.file_path]
    assert admin and all(r.assumed for r in admin)
    assert all("not a string literal" in (r.note or "") for r in admin)

def test_middleware_chain_composed_along_mount_graph(fixture_root):
    put = next(r for r in resolve(fixture_root) if r.method == "PUT")
    assert put.middleware_chain[0].startswith("express.json")   # app level, first
    assert "auth" in put.middleware_chain[-1]                   # route level, last

def test_no_fabricated_paths(fixture_root):
    assert all(r.path.startswith("/") for r in resolve(fixture_root))
    assert not any("undefined" in r.path or "${" in r.path for r in resolve(fixture_root))
```

**Integration, mirroring `tests/test_reuse_pipeline.py` / `test_extractor_integration.py`:** point
`extract_repo_with_reuse` at the fixture and assert the record has `language == "JavaScript"`,
non-empty `routes`, `confidence > 0`, no `"not yet implemented"` note, and that schema validation reports
1 valid / 1 — the inverse of the failure locked in at `tests/test_schema_check.py:81-96`.

### Acceptance criteria
1. `detect_project_type` on an Express repo returns `{'frontend': None, 'backend': ['express'], …}`;
   on a `client/`+`server/` monorepo, `{'frontend': 'react', 'backend': ['express'], …}`. No
   `"react_or_angular"` for any package.json carrying a backend framework dependency.
2. A chunk from an Express repo carries `stack == "express"` and reaches a real builder — zero records
   with `"Extraction for stack … is not yet implemented"` and zero with `confidence: 0`.
3. Every Express record validates against the schema (`0 valid / 1` → `1 valid / 1`), with `language`,
   `lineRange`, `frameworkOrLibrary`, `lastUpdated` and `pullRequest` present.
4. On the cross-file fixture, `GET /api/v1/users/:id` is reported with `assumed=False`, and the same
   router mounted at `/api/v2` produces its own routes — no path is reported one prefix short.
5. Every route whose prefix or path is non-literal has `assumed=True` and a note naming the file, line
   and the verbatim unresolved expression. **No route is ever emitted with a fabricated or
   partially-guessed path presented as fact.**
6. Programmatic route registration yields a record-level note saying the route table is incomplete, and
   lowers confidence; it never yields invented routes.
7. Middleware is classified by arity, with a passing test that a 4-param function named `logger` is an
   error handler and a 3-param function named `errorHandler` is not.
8. The ordered middleware chain per route is present and reflects mount order; an error handler
   registered before routes produces a finding.
9. Async wrappers are unwrapped: the handler name is never the wrapper's name, and the reported
   `lineRange` is the inner function's.
10. Line ranges are byte-accurate tree spans — a handler containing a template literal with `}` or a
    nested object is reported with correct start/end lines (the brace-counting failure class is gone).
11. Module system per file is resolved from the nearest `package.json` `"type"`, with `.mjs`/`.cjs`
    overriding; `module.exports = router` followed by an *earlier* `exports.helper` reports `helper` as
    dropped with a note.
12. `pip install -r requirements.txt` succeeds from wheels alone on linux/macOS/Windows x86_64 and
    arm64 with Python ≥3.10 — no C toolchain — with `tree-sitter==0.25.2` and
    `tree-sitter-javascript==0.25.0` pinned exactly.
13. A syntactically invalid `.js` file produces a partial record plus a note, and never aborts the run.
14. Existing tests all still pass, in particular `tests/test_project_type.py`'s
    `test_detects_react_frontend_only` and the feature-grouping flat-file tests.

### Gaps
- `tests/test_reuse_pipeline.py` and `tests/test_extractor_integration.py` were listed but not read, so
  the exact integration-test idiom (fixtures vs `tmp_path` repo construction) should be matched to those
  files when writing the integration test.
- The reuse-cache staleness interaction described in A6 (a chunk unchanged but its mount prefix changed in
  a parent file) needs a test of its own; I have not designed one, because
  `src/storage/mirror_store.py` was not read.
