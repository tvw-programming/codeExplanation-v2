# 16 — Extractor implementation plan (Python, Spring Boot, Express)

Follows `documentation/14-stack-support-validation.md`, which concluded that regex plus brace
matching cannot express the facts these stacks are made of — balanced delimiters, lexical scope,
cross-file prefix composition — and that Python, Spring Boot and Express need real extractors.

The "how" lives in four blueprints under
`documentation/research/extractor-implementation-blueprint/`: `python_extractor.md`,
`java_spring_extractor.md`, `express_extractor.md`, `shared_infrastructure.md`. They were written in
parallel and **do not agree on everything**. This document is the sequenced plan and the record of
how those disagreements were settled. Where a claim is non-obvious it names the blueprint, so you can
go read the measurement behind it. Nothing here supersedes a blueprint's internals; it supersedes
their build order, their version numbers, their pins and their overlapping schema proposals.

---

## 1. Build order

| # | Work | Version bump | Depends on | Why here |
|---|---|---|---|---|
| 1 | **Render gate** (`src/validate/render_gate.py`) + `run_pilot` wiring + `run-local.sh` exit codes | none | — | No schema change, lands standalone, and it is the only thing that stops an unsupported stack shipping an mp4 *while* the extractors are in flight. On pre-v5 records it degrades to the content-emptiness and identity rules, which are the two that matter (shared §4). |
| 2 | **Express detection** — `"node"` marker class, `express` backend stack, one `package.json` able to produce a frontend hit, a backend hit or both | none | — | Express is currently *unrepresentable*, not mis-tuned: `MARKER_FILES` maps `package.json` to the single key `"react_or_angular"` (express Part A). No extractor work can land until a chunk can carry the right stack label. Five files, four of them a handful of lines. Fully parallel with 1, 3, 4. |
| 3 | **`fidelity` + `notAnalyzed`** + the narration hedge ladder | **5** | 1 | Lets narration hedge by substrate instead of asserting, and makes "nobody wrote an analyzer for this" representable, which `routes: []` currently cannot say (shared §1). |
| 4 | **tree-sitter wrapper** (`src/parse/tree_sitter_support.py`) + pins | none | — | No schema change of its own. Independent of 1–3; start it in parallel the moment someone is free. |
| 5 | **Shared route-prefix resolver** + move `ExtractedRoute` into `common.py` + refactor `go_extractor` onto the resolver, with a parity test | **6** | 3 | Must land *before* any new extractor, so Spring/Express/FastAPI route work is graph-building, not dataflow. The validation report calls this the largest correctness win per unit of work (14 §sequence item 6). |
| 6 | **Python extractor** (`src/extract/py_extractor.py`, stdlib `ast`) | **7** | 3, 5 | First extractor: zero new dependencies, same interpreter, and `ast` answers line ranges, decorators, docstrings, `__all__` and data models outright. |
| 7 | **Java/Spring extractor** (`src/extract/java_extractor.py`) | **8** | 3, 4, 5 | Highest breakage count removed per change (14: 12 of 14 catalogued Java breakages die with the substrate switch). Independent of 8 — can run in parallel with Express once 4 and 5 exist. |
| 8 | **Express extractor** (`src/extract/express_extractor.py` + `express_project.py` prepass) | **9** | 2, 4, 5 | Needs the project-level prepass (module type per directory, Express major, mount graph), which is why it is last: it is the only stack whose route facts are genuinely cross-file. |
| 9 | *(deferred)* move `ts_extractor`/`go_extractor` onto tree-sitter; `FIDELITY` `"regex"` → `"syntax"` | **10** | 4 | Highest-risk cache transition in the project: these are the records a user has actually seen a video from (shared §3). |

**Reconciling the two proposed orders.** The validation report put Python first; `shared_infrastructure.md`
put gate → fidelity → resolver → wrapper first. The shared order wins for items 1–5 and the validation
report wins inside the extractor block. Reason: the Python blueprint designs its own FastAPI/Flask
prefix model (python Q5, "mirror `_resolve_group_prefix`'s design"), and the shared resolver replaces
it. Writing Python first means writing prefix resolution twice and then deleting one. The resolver is
~120 lines with no parser dependency — cheaper to do first than to retrofit. Python still leads the
extractors because it adds no dependency and no new failure mode.

**Parallelisable:** (1) ‖ (2) ‖ (4) are mutually independent. (7) ‖ (8) once (4) and (5) are in. (3)
and (5) are strictly sequential because (5)'s render-gate consistency check reads a field (3) adds.

---

## 2. Do this first — cheap, and it unblocks everything

Four things, none of which needs a parser or a schema change. A day's work, in this order:

1. **Ship the render gate.** `gate(record)` returns ok / degraded / blocked. Exactly three things
   block: every content list empty (the Angular failure: schema-valid, renders, says nothing true);
   `fidelity == "none"` (the `reuse_pipeline` placeholder branch, which read nothing); broken
   identity or a self-contradicting claim (`pathResolved is False and not assumed`). Everything else
   — low confidence, every claim assumed, regex fidelity, `notAnalyzed`, trimmed snippets, parse
   holes — *degrades and renders*, hedged. That split is the whole design (shared §4).
2. **Wire the exit codes**: 0 normal/partial, 1 real failure, 2 nothing renderable, 3 blocked chunks
   with `--strict`. `run-local.sh` is `set -euo pipefail`, so the invocation must be wrapped in
   `set +e` / `case` or code 3 kills the script (shared §4).
3. **Fix Express detection** and add `group_node_features` to `feature_grouping.py`.
   `test_detects_express_backend_not_frontend` currently asserts the bug: `frontend_stack` is
   `"react_or_angular"` for a pure Express repo.
4. **Pin tree-sitter in `requirements.txt` and write the import-time assertion**, before anyone
   writes a query. Section 4 below.

After these, an unsupported stack stops producing video, Express chunks carry a real stack label, and
the parser substrate is pinned — which is the state the three extractors want to be written against.

---

## 3. Conflict 1 — EXTRACTOR_VERSION sequence

Both the Python blueprint (Q4) and the shared blueprint (§1) claim `4 → 5`. They cannot both have
it. The shared blueprint also argues the general rule, and that rule decides the conflict: **one bump
per shipped change**, because a single number covering two independent changes makes "which extractor
wrote this record" unanswerable when a regression surfaces in a user's store (shared §1, migration
note). So 5 goes to whichever lands first, and that is `fidelity` — it is ordered before the Python
extractor because every extractor must emit it.

| Version | Change | Fields introduced | Lands with |
|---|---|---|---|
| 4 | *(current)* file header comment | — | shipped |
| **5** | `fidelity` + `notAnalyzed`; narration hedge ladder | `fidelity`, `notAnalyzed` | build step 3 |
| **6** | shared route-prefix resolver; `ExtractedRoute` moved to `common.py`; `go_extractor` refactored onto the resolver | `routes[].pathResolved`, `routes[].prefixChain` | build step 5 |
| **7** | Python extractor on stdlib `ast` | `visibility`, `visibilitySource`, `injectedDependencies`, `reExports`, `displayPath`, `dataModels[].fields[].description` | build step 6 |
| **8** | Java/Spring extractor on tree-sitter | `importantFunctions[].{isFrameworkEntryPoint,hasBody,enclosingType,nestingDepth,overloadKey,invokedBy}`, `diGraph`, `generatedMembers` | build step 7 |
| **9** | Express extractor on tree-sitter | `middleware`, `mountGraphHash` | build step 8 |
| **10** | `ts_extractor`/`go_extractor` onto tree-sitter | none (values change, not keys) | deferred |

**The cost, stated plainly.** `needs_reanalysis` compares `stored["extractorVersion"]` to
`EXTRACTOR_VERSION`, so every bump invalidates the entire store: six bumps means six cold runs. That
is the price of provenance and it is the right price — but if 7, 8 and 9 ship in one release, collapse
them to a single bump and say so in the history line. Do **not** collapse 5 and 6: they are the two
most likely to produce a field-level regression, and they are the two you will most want to tell
apart. The reuse loop writes stored records for *reused* chunks too, so a new field written without a
bump would silently serve mixed-vintage records (shared §1).

Backward compatibility is free and, unusually, *correct*: every record written by versions 1–4 came
from `ts_extractor` or `go_extractor`, both regex, so `record.get("fidelity", "regex")` is the true
value rather than a defensive default. One exception to read carefully — `route.get("pathResolved")`
is `None` on pre-v6 records and narration must treat `None` as "unknown", never as False. Write
`if resolved is False:`, never `if not resolved:` (shared §2).

---

## 4. Conflict 2 — the tree-sitter pin

The two proposals are **compatible, not contradictory**: Express pins `tree-sitter==0.25.2`, shared
measured 0.26.1 and recommends `>=0.25,<0.27`, and 0.25.2 sits inside that range. Both measured the
same API break from opposite directions, and the two measurements corroborate each other:

| runtime | `QueryCursor` | `Query.captures` |
|---|---|---|
| 0.24.0 | absent | present |
| 0.25.2 | present | **removed** |
| 0.26.1 | present | **removed** |

Express measured that `tree-sitter==0.24.0` *refuses to load* `tree-sitter-javascript==0.25.0`
(`ValueError: Incompatible Language version 15. Must be between 13 and 14`), so the grammar's own
declared `tree-sitter~=0.24` lower bound is wrong in practice — **≥0.25 is the real floor** (express
B.1). Shared measured that 0.26.1's runtime accepts grammar ABI 13–15, so the ABI-14 Java and
TypeScript grammars load fine alongside the ABI-15 ones (shared §3).

**One pin set for the whole project:**

```
# Parser substrate. All ship prebuilt abi3 wheels -- no C toolchain, no Node, no JVM, no Go sidecar.
# Runtime range, grammars exact: QueryCursor replaced Query.captures() in 0.25 and the old method is
# GONE, not deprecated, so <0.25 cannot run our queries at all.
tree-sitter>=0.25,<0.27
tree-sitter-java==0.23.5
tree-sitter-javascript==0.25.0
tree-sitter-typescript==0.23.2    # ONE package, TWO grammars: typescript and tsx
tree-sitter-go==0.25.0
```

The runtime gets a range rather than `==0.25.2` because the wrapper asserts the capability it needs
rather than trusting a number: `_runtime()` raises `ParserUnavailable` at import if
`tree_sitter.QueryCursor` is missing, naming the pin. No compatibility shim — a shim that tries
`Query.captures` and falls back makes behaviour depend on which runtime resolved, and the two eras'
return shapes differ (shared §3).

**Grammars are pinned exactly and this is not stylistic.** Node type names and field names are not
stable across grammar releases, so a floated grammar **returns zero captures rather than erroring** —
the same silent-empty failure class as the Angular record, which is the one failure class this
project has decided it will not tolerate. A grammar bump is a reviewed change behind a version bump.

**One module, not two.** The Express blueprint sketches `src/extract/ts_runtime.py`; the shared
blueprint sketches `src/parse/tree_sitter_support.py`. Build the shared one and delete the sketch.
It owns four things and nothing else: grammar loading, query execution, the 0-indexed-byte →
1-indexed-line translation, and the rule that a syntax error in one file never fails a run.

Two rules from the wrapper that every extractor must obey:
- **`matches()`, not `captures()`, whenever two captures must belong to the same pattern instance**
  — an annotation with *its* argument list, a route method with *its* path. `captures()` flattens
  across the subtree, so `@GetMapping` from one method and `("/x")` from another collapse into
  parallel lists that line up by accident. This is the single most likely source of a silent wrong
  attribution, and 14 ranks wrong attribution as the worst failure class for a narration product.
- **Every snippet goes through `snippet_for`/`trim_snippet`.** That function is the only
  `redact_secrets()` choke point and the only place the 120-line cap and continuation note are
  applied. A hand-built `CodeSnippet` is a secret leak waiting to happen.

---

## 5. Conflict 3 — route prefix resolution

**`src/extract/route_prefix.py` is authoritative for all five stacks.** The per-stack prefix designs
in the Python and Express blueprints are superseded; what survives from them is the *edge
production*, which is the only part that is stack-specific. The module never returns a bare string —
it returns the path it could build plus whether that path is complete, because a confidently wrong URL
is the worst output this pipeline can produce: a viewer cannot falsify it (shared §2).

Interface, verbatim, because every extractor codes against it:

```python
PrefixEdge(child, parent, segment, declared_at=None, expression=None)
    # segment is None  == "there is a prefix here and I could not read it"
    # segment is ""    == "the prefix is empty"   <- a different, stronger claim
Resolution(path, resolved, note, chain, unresolved_reason)
    # unresolved_reason in {"unknown_parent", "non_literal", "cycle", "depth"}

graph.add_child_edge(child, parent, segment, ...)  # Fiber groups, FastAPI nested routers
graph.add_mount(parent, child, segment, ...)       # Express app.use, Flask register_blueprint,
                                                   # FastAPI include_router -- normalised to the
                                                   # same edge, so the resolver sees one direction
graph.add_root(symbol, segment=None, ...)          # fiber.New(), the Express app, a Spring class
full_route_path(graph, symbol, route_path) -> Resolution
```

What each stack hands it:

| Stack | Roots | Edges | SymbolId |
|---|---|---|---|
| Spring | the class itself, with class-level `@RequestMapping` as its own prefix; `server.servlet.context-path` above it when readable | one edge per handler method (containment, one level) | class simple name within the file |
| Express | the `app` (`express()` call site), per file | `app.use(path, router)` as `add_mount`, transitively across files | **file-qualified**, e.g. `("src/routes/birds.js", "<module>")` — two files both calling their router `router` must not collide |
| Fiber (Go) | `fiber.New()` assignment targets; `"app"` as a *named, testable* conventional assumption | `app.Group("/api")` chains as `add_child_edge` | local variable name |
| FastAPI | `FastAPI()` instances (`root_path` as a root segment) | `APIRouter(prefix=)` as a child edge; `include_router(r, prefix=)` as `add_mount` | file-qualified router variable |
| Flask | the `Flask()` instance, which may live inside `create_app()` rather than at module scope | `register_blueprint(bp, url_prefix=)` as `add_mount`, nesting composes | file-qualified blueprint variable |

Hard rules the test plan locks:
- **`pathResolved is False` ⇒ `assumed is True`.** Never the reverse; a resolved path can still be
  assumed for other reasons. An extractor that sets one without the other is a bug and the render
  gate blocks the record.
- **When no route in a file resolves** — the common Express case, where the prefixes live in a file
  the chunker never opened — add one `notAnalyzed` entry for `routes` rather than hedging twenty
  sentences individually.
- A **double mount** (the same router mounted at two prefixes, a real Express pattern) is reported as
  ambiguous, never silently last-wins.

**`go_extractor` is refactored onto the resolver in the same PR, with its existing route assertions
as the parity test.** This is not tidying. `go_extractor.py` does `roots.add("app")`
unconditionally, so a function that takes `app *fiber.App` as a **parameter**, with the real prefix
applied at the call site, reports its chain as **fully resolved with `prefix_assumed = False`** — a
confidently wrong URL carrying no flag, which is exactly the unfalsifiable failure 14 names as worst
(shared §2). Three further defects die with the refactor: a non-literal prefix (`app.Group(basePath)`)
produces *no edge at all* and the path silently omits the prefix; the cycle branch returns a partial
prefix with no explanation; and slash normalisation is spread across two functions. Write
`test_app_passed_as_a_parameter_is_not_treated_as_a_resolved_root` as a **failing-first** test — it
documents the one behavioural change the refactor should make.

---

## 6. Conflict 4 — `ExtractedRoute` lives in `common.py`

Confirmed, and folded into build step 5. The dataclass is currently defined in `go_extractor.py`
(`method, path, handler, static_or_dynamic, routing_library, protected, assumed, note`); the Python
blueprint recommends moving it to `common.py` so one definition serves all (python Q5). This fits the
other two: the Java blueprint codes against the serialised route shape directly, and the Express
blueprint models its builder on `build_backend_go_chunk_record` field-for-field. Importing it from
`go_extractor` would couple four modules to the Go one for no reason.

Move it with the resolver PR, not before: the same PR adds `pathResolved` and `prefixChain` to the
serialised shape, so one touch of `json_builder` covers both. `routing_library` grows to
`"fiber" | "fastapi" | "flask" | "django" | "spring" | "express"`.

---

## 7. Consolidated schema changes

| Field | Type | Set by | Version | Required? |
|---|---|---|---|---|
| `fidelity` | `"regex" \| "syntax" \| "typed" \| "none"` | every extractor, from a module constant copied through a result object | 5 | **required**, enum-checked in `schema_check` |
| `notAnalyzed` | `list[{aspect, reason, verify}]` | every extractor | 5 | **required**, may be empty |
| `routes[].pathResolved` | bool | every extractor with routes, from `Resolution.resolved` | 6 | optional per-item; **render-gate** checks `False ⇒ assumed` |
| `routes[].prefixChain` | `list[str]` | same | 6 | optional, operator-facing |
| `importantFunctions[].visibility` | string, `null` for TS/Go | Python: `declared_in_all \| public_by_convention \| private_by_underscore \| protocol_method`; Java: `public \| protected \| package_private \| private` | 7 (Py), 8 (Java) | optional; **do not enum-check** — the vocabularies are per-language |
| `importantFunctions[].visibilitySource` | string | Python: `__all__ \| convention \| containing_namespace \| dunder \| name_mangling`; Java: `explicit_keyword \| implicit_interface \| implicit_record` | 7 / 8 | optional |
| `importantFunctions[].exported` | bool *(existing)* | all; Java redefined as "reachable from outside this type", Python derived from `visibility` | 7 / 8 | existing, stays boolean |
| `injectedDependencies` | `list[{name, kind, via, assumed, note}]` | Python (FastAPI `Depends`), Java (DI edges) | 7 / 8 | optional |
| `diGraph` | `{injectionPoints, edges, beanIndexSize, resolution}` | Java only | 8 | optional |
| `generatedMembers` | `list[{name, kind, assumed, note}]` | Java only (Lombok) | 8 | optional |
| `middleware` | `list[{name, kind, arity, order, lineRange, assumed}]` | Express only | 9 | optional, **but `schema_check` and `claude/json-structure-rules.md` must be updated in the same PR** |
| `mountGraphHash` | string | Express only | 9 | optional — see the staleness trap in §8 |
| `reExports` | `list[{name, fromModule}]` | Python only (package `__init__.py`) | 7 | optional |
| `displayPath` | string | Python only (normalised `<int:year>` / `{item_id}` / `<page>` → `:year`) | 7 | optional; verbatim `path` is always kept |
| `dataModels[].fields[].description` | string | Python (`max_length=120, null=True`), Java | 7 | optional; `json_builder` currently emits `{name, type}` only |

**Three overlaps resolved:**

1. **`fidelity` is used twice with different meanings.** Shared §1 defines it as a top-level
   record field over `regex|syntax|typed|none`; Java §10 puts `"fidelity": "syntax"` inside
   `diGraph`. Rename the nested one to **`diGraph.resolution: "name_match" | "type_resolved"`**. One
   enum, one meaning, per key — the nested one is answering a different question (was this edge
   type-resolved) and overloading the word makes both unreadable.
2. **`visibility` is one field with two vocabularies.** Keep one key; do not invent
   `pyVisibility`/`javaVisibility`. `visibilitySource` carries the provenance that makes the value
   interpretable, and `schema_check` must not enum-check it or Java records fail on Python's values.
   TS/Go emit `null` = "this language has no visibility declaration we model"; narration must treat
   `null` as "not modelled", never as private.
3. **`injectedDependencies` vs `diGraph`.** Both are DI. Use `injectedDependencies` as the shared
   edge list for Python *and* Java so a downstream consumer has one key to read, and keep `diGraph`
   as Java-only supplementary detail (bean index size, injection points, ambiguity). Merging them
   fully would force Python to invent a bean index it does not have.

---

## 8. Per-component notes: build it, decide it, traps

### Render gate (step 1)
Build `gate()` as a pure function of a record, `exit_code_for(report, strict)`, a `renderGate` section
in `pilot_report.json` beside `schemaValidation`, and a stderr block that names **file paths, not
chunk ids** (the operator's next action is to open a file) and states the consequence, not a status
word. Narration and render run over the renderable set only — which is also a reporting fix, since
`narration.chunkCount` currently averages in content-free chunks whose ~28s scripts drag the
distribution down (shared §4).

*Traps.* `set -euo pipefail` in `run-local.sh` turns exit code 3 into a dead script. Step 4's
"run the backend step first without `--no-render`" message becomes a misdiagnosis when the staging
dir is empty because every chunk was blocked — branch it on `renderGate.rendered`. And the stale
staging dir, below.

### Fidelity + notAnalyzed (step 3)
`FIDELITY` is one constant per extractor module. **A builder must not compute fidelity from the
data** — a Python file with zero decorators does not make the extractor less capable; fidelity
describes the tool, not the file. **An extractor that falls back mid-file degrades the whole
record**: if the tree-sitter wrapper raises `ParserUnavailable` and the Express extractor drops to
regex, that record is `"regex"`. The extractor returns its facts in a result object carrying
`fidelity` and the builder copies it through; it must not read the module constant (shared §1).

`_hedge` becomes a three-rung ladder: `PLAIN` / `TEXTUAL` ("Going by the text of the file,") /
`ASSUMED` ("It looks like"). **An explicitly assumed claim outranks a weak substrate** — stacking
both is worse prose and no more honest. Fidelity also gates which sentences exist at all: at regex
fidelity the function opener drops the end line (brace counting already measured 2 instead of 3 on a
raw string containing `}`), the export claim is omitted entirely for non-TS languages (`export` never
appears in Python or Java, so the claim is systematically false, not merely uncertain), and the
"nothing else calls it and it is not exported" sentence — an assertion of *absence* built on a
name-substring call graph — is never spoken.

*Trap.* `function_narration.build_function_narration(fn)` takes only the function dict and never sees
the record. Cheapest correct fix: `json_builder` stamps `fn["fidelity"]` onto each
`importantFunctions` entry in the pass that already mutates them. No signature changes.

*Judgement call to re-check:* `TEXTUAL_PHRASE` is unvalidated against TTS. A prefix clause recurring
on every sentence of a regex-fidelity chunk may grate at 130 wpm; "From the text," is a one-line
change (shared §1 gaps).

### Route-prefix resolver (step 5)
Covered in §5. Keep `MAX_DEPTH = 32` as a runaway guard; a real mount chain is 2–4 deep. `_join` is
the only place slash normalisation happens, and `""` stays `""` rather than becoming `"/"`, so a
rootless route is visibly rootless.

### tree-sitter wrapper (step 4)
`line_range()` is **the only place `+1` is allowed to appear** — every off-by-one in the old
brace-matching code came from inlining the conversion at each use site. It also handles
`end_point.column == 0`, which means the node ends at the very start of a line and naively reporting
that row over-reports by one.

*Traps.* Parse **bytes, not str** — tree-sitter offsets are byte offsets and a comment containing an
em dash or a non-ASCII identifier shifts every column, producing an off-by-n snippet rather than an
exception. `prefix_nodes` exists for the decorator/annotation problem, which bites all three stacks
identically: a Java `method_declaration` starts at `public`, *after* its `@GetMapping`; a Python
`FunctionDef.lineno` points at `def`, *after* its `@app.get(...)`. Clipping from the declaration loses
the one line that says what the thing is. Error tolerance is per-node, not per-file: a file with one
bad method keeps the other twelve, but a file where >25% of lines sit in `error_lines` is treated as
unparseable and blocked rather than narrated a tenth at a time.

### Python extractor (step 6)
One `ast.parse()` per file plus a **single source-ordered pass over `module.body`**. Never
`ast.walk` for ordering: the docs say it yields nodes "in no specified order", and narrative order is
a product fact.

*Traps, all measured on CPython 3.13.18 (python Q1–Q9).* The decorator trap is the central one and
gets a named regression test: `line_range[0]` must be `min(d.lineno for d in node.decorator_list)`.
`end_lineno` is typed optional — fall back and mark assumed. Docstrings come from
`ast.get_docstring(node, clean=True)`; the existing upward comment scan in `function_context.py`
understands only `//` and `/* */`, and a comment block above a Python `def` is usually a TODO, so
reporting it as documentation is actively misleading. An f-string docstring yields `None`, never a
partial string. `__all__` has four real forms (`Assign`, `AnnAssign`, `AugAssign` with `+=`, and
computed) and three of them mean "assumed": a name absent from an `__all__` **you could not read in
full** must not be reported private. Flask's `app` often does not exist at module scope at all —
anchoring on `app = Flask(` finds nothing in exactly the well-structured codebases worth explaining,
so also scan `create_app()`-shaped functions. Django URL patterns carry **no HTTP method**; emit
`UNKNOWN` and never infer one from the URL shape. Stacked Flask `@route` decorators mean several URL
rules for one function — one `ExtractedRoute` per decorator. Protection detection stays narrow and
name-based with `assumed=True`: the Go module's docstring records a real false positive from a
whole-file "auth" substring match; do not repeat it.

### Java/Spring extractor (step 7)
The chunk unit is the **annotated type**, grouped into feature slices. Queries are written as one
pattern per declaration form rather than an alternation, because each form has a different field set
and a different body node.

*Traps (java §2–§10, all probed).* Writing `body:` as an **optional** capture is the entire fix for
the brace-matcher bug that attached the following method's body to an abstract method — body-less
declarations must still MATCH. `@Controller` must never be matched as a literal string: the
stereotypes are meta-annotated, so `@RestController` is a `@Controller` specialisation and a
substring match gets `@ControllerAdvice` wrong too; an unrecognised annotation degrades to
`role="unknown"` with `assumed=True`, never to a plausible-looking layer. Javadoc extraction must not
read a `/* */` license header as the class description — this is grep-assertable at acceptance
(`fileDescription` matching `copyright|license|rights reserved` is a failure). Spring Data repository
interfaces **have no function bodies**, and the method name *is* the query: parse keywords
longest-first so `GreaterThanEqual` is not matched as `GreaterThan`, and let `@Query` win over the
method name. Lombok generates members that are not in the source — list them in `generatedMembers`
with `assumed=True`, never as read. `@Scheduled`/`@EventListener`/`@ExceptionHandler`/`@Bean`/handler
methods have zero in-project callers and **must be labelled `invokedBy: "spring-container"`, never
"unused"** — the same class of error as presenting `OrderServiceImpl` as dead code because nothing
imports it by name. Overloads collapse under any name-keyed map, which `function_context`'s
caller/callee matching is: keep `overloadKey`, and when a chunk holds two methods of the same name,
mark their `calledBy`/`calls` assumed with a note.

### Express extractor (step 8)
A **project-level prepass** (`express_project.py`) runs before any per-file parse, because a `.js`
file's module system is decided by the nearest `package.json` `"type"` and a route's full path is
decided by `app.use` calls in other files. Neither is answerable from the per-chunk loop.

*Traps (express B.3–B.9).* Middleware is classified by **arity, not name**: an error handler is the
4-argument one, and a 3-argument function called `errorHandler` is not one — there is a named test
for both directions. **Order is semantics** and nothing in the current schema can carry it, which is
the one place a new array (`middleware`) is justified; an error handler registered before routes
never fires, and that is a finding worth reporting. Async wrappers put the real handler one
call-expression deeper, so an extractor that does not unwrap them names the handler `asyncHandler`
and highlights the wrong lines — the unwrap is structural, and `WRAPPER_NAME_HINTS` may only *phrase*
a note, never decide structure. Node's extensionless resolution does **not** try `.mjs`/`.cjs` (the
express blueprint corrects the earlier brief on this, measured); the two trailing candidates in the
resolver are marked PRAGMATIC and must be reported `assumed=True`. `module.exports = router`
following an earlier `exports.helper` *drops* the helper — report it with a note. An arrow function
with one unparenthesised parameter uses the singular field `parameter:`, not `parameters:`.

*The staleness trap, and it is real.* `needs_reanalysis` compares file content only. A chunk whose own
content hash is unchanged can still have a **stale route path** because a parent file's mount prefix
changed. Mitigation: store a hash of the resolved mount graph on each Express record and treat a
mismatch as stale (`mountGraphHash` in §7). This needs a test and the Express blueprint does not have
one, because `mirror_store.py` was not read in that pass.

---

## 9. Test plan

| File | Count | Covers |
|---|---|---|
| `tests/test_render_gate.py` | ~11 | the three block rules and, more importantly, the *non*-block rules asserted explicitly: low confidence, all-assumed, `notAnalyzed`-with-other-content and missing non-identity fields all degrade rather than block. Plus a pre-v5 record gating on content alone. |
| `tests/test_fidelity.py` | ~9 | enum validation; `hedge_level` precedence (assumed outranks regex); exact-string equality on the two hedged sentence forms; regex fidelity omitting the end line and the export claim; `notAnalyzed` producing exactly one disclosure sentence, in the recap beat; old records narrating identically to `"regex"` ones. |
| `tests/test_route_prefix.py` | ~11 | nested composition in source order; `add_mount` and `add_child_edge` producing identical `Resolution`s for the same topology; each of the four unresolved reasons naming its cause; double mount as ambiguous; slash normalisation; and `pathResolved False ⇒ assumed True` asserted over a table. |
| `tests/test_go_extractor.py` (additions) | 2 + parity | existing route assertions unchanged as the refactor parity test, plus the variable-prefix case and the failing-first `app`-as-parameter test. |
| `tests/test_tree_sitter_support.py` | ~13 | `importorskip`-guarded. The pin assertion (`hasattr(tree_sitter, "QueryCursor")`), every registered grammar loading, 1-indexed-inclusive line ranges including the column-zero case, `prefix_nodes` putting the annotation first, non-ASCII byte slicing, syntax-error tolerance, `ParserUnavailable` over `ImportError`, `matches()` keeping an annotation with its own arguments, and — the one that matters most — a snippet with a secret coming back redacted, proving the new path cannot bypass `trim_snippet`. |
| `tests/test_py_extractor.py` | ~45 | inline-source units in `test_go_extractor.py` style: the decorator trap, docstring-not-comment, the four `__all__` forms, FastAPI prefix composition (including a router named anything and a non-literal prefix), `Depends` from both `Annotated` and defaults, Flask method defaults and stacked decorators, Django ordering and `include()`, five data-model flavours, and the negative cases — `dict.get` is not a database read, `async_mode` is not an async function, an unknown class is not forced into `dataModels`. |
| `tests/test_py_extractor_integration.py` + `tests/fixtures/py_fastapi_app/` | 1 fixture tree | the cross-file join a single string cannot test: `/api/v1/items/{item_id}` composed from `include_router` + `APIRouter(prefix=)`, plus a deliberately broken file asserting confidence 0.3 and a parse note. |
| `tests/test_java_extractor.py` | 27 | led by `test_grammar_contract_node_and_field_names_still_exist`, which asserts the node and field names the module depends on still exist so a grammar bump fails a test instead of silently emitting empty lists. Then: body-less interface method not stealing the next body, text blocks with braces, route concatenation and `{name:regex}` splitting on the first colon, `${...}` reported unresolved, stereotype resolution without substring matching, the visibility table's implicit-public row, Javadoc vs license header, derived queries, Lombok, DI resolution and ambiguity, container-invoked labelling, overloads, and secret redaction. |
| `tests/test_project_type.py` (additions) | ~8 | Express-only repo detecting no frontend (today it returns `"react_or_angular"` — the bug), monorepo and single-package full-stack both detecting two stacks, hint-deps-only marked assumed, and a regression test that a plain `package.json` still falls back as before. |
| `tests/test_express_extractor.py` + mount fixture | ~23 | arity classification in both directions, the seven route-registration forms, async unwrapping, module-system resolution and the `module.exports = router` drop, Mongoose/Sequelize/Zod object literals, and a multi-file fixture directory for the mount graph — which, like Python's, cannot be tested from inline strings. |
| `tests/test_run_pilot.py`, `test_schema_check.py`, `test_reuse_pipeline.py` (additions) | ~8 | blocked chunks not narrated or rendered; a Java-only repo returning exit code 2; `--strict` returning 3; blocked chunks named with reasons; the tests that currently *lock in* the placeholder failure for Python/Java/Express updated to assert validity; and a stored record at version N treated as stale after each bump. |

Roughly 160 tests. Every one is a plain `def test_*` with inline triple-quoted source and bare
asserts — no classes, no mocks, no fixtures module — matching `tests/test_go_extractor.py`.

---

## 10. Acceptance criteria

**Render gate.** A repo whose every chunk is blocked produces no mp4 and exits 2. A repo with one
good chunk and three blocked ones renders one section, exits 0, and names the three files with
reasons on stderr and in `pilot_report.json`. Low confidence never blocks.

**Fidelity.** Every record carries `fidelity` and `notAnalyzed`; `schema_check` enum-checks the
first. No sentence asserts an end line, an export status or an absence at regex fidelity. A record
that fell back mid-file reports `"regex"`, not `"syntax"`.

**Route prefix.** Every stack's routes come from `full_route_path`. `pathResolved is False` implies
`assumed is True` with a non-empty note naming the missing piece, over all fixture records.
`go_extractor`'s existing route tests pass unchanged, and `app`-as-a-parameter no longer reports a
resolved chain.

**tree-sitter.** `pip install -r requirements.txt` succeeds from wheels alone on linux/macOS/Windows
x86_64 and arm64 with Python ≥3.10 — no C toolchain. The grammar-contract test passes. Imports are
lazy, so a repo with no Java files never pays the import.

**Python.** `validate_record()` returns `[]` for every record including parse failures and empty
files. Record key set equals the Go record's plus only the agreed additive keys — assert mechanically
with a set-symmetric-difference test. Every route handler's snippet first line starts with `@`.
Confidence 0.95 with every list empty is impossible. Two runs produce byte-identical records except
`lastUpdated`. No `import`, `exec`, `eval`, `importlib` or subprocess anywhere in the extraction path
— the target repo is parsed, never executed, and this is grep-assertable in CI.

**Java.** No `.java` chunk reaches the placeholder branch. 100% schema-valid on the fixture repo and
on one real Spring Boot repository. Every route path is the full path; zero paths beginning `/{`
unless the source says so. No `fileDescription` matches `copyright|license|rights reserved`. No
`@Service`/`@Component` that is injected anywhere has zero inbound DI edges. Every container-invoked
method carries `invokedBy`. `src/test/java` contributes zero chunks. `root.has_error` adds a note and
caps confidence at 0.5.

**Express.** Detection returns `{'frontend': None, 'backend': ['express']}` for a pure Express repo
and both stacks for a monorepo. Zero records with `confidence: 0`. On the cross-file fixture,
`GET /api/v1/users/:id` is reported with `assumed=False`, and the same router mounted at `/api/v2`
produces its own routes — no path one prefix short. A 4-param function named `logger` is an error
handler; a 3-param `errorHandler` is not. Handler names are never the wrapper's name. A
syntactically invalid `.js` file produces a partial record and never aborts the run.

---

## 11. Open questions and risks

These are carried from the blueprints as the researchers stated them. None is resolved by this plan.

1. **`tree-sitter-java` 0.23.5 last shipped 2024-12-21 — roughly two years stale.** The shared
   blueprint found no statement that it covers Java 21+ records, sealed types or recent pattern
   matching, and says a Java 21+ repo must be probed before the Spring extractor relies on it
   (shared §3 gaps). The Java blueprint partially closes this: its probe parsed **records, text
   blocks, sealed-adjacent syntax and enum bodies cleanly**, but did **not** test Java 23/24/25-only
   syntax such as primitive patterns in `switch` or module import declarations (java §1 gaps).
   Neither researcher could confirm whether a newer grammar exists outside PyPI. **Probe a real
   Java 21+ repo before step 7.** The degradation is graceful (`has_error`, capped confidence) but
   unmeasured.
2. **Node-type names were verified for only a few Java constructs.** The shared probe confirmed
   `method_declaration`, `modifiers`, `annotation`, `annotation_argument_list`, `identifier` and the
   `name:` field for Java 0.23.5 by executing a query. Everything else is unverified. An unverified
   name does not error — the **query silently returns zero captures**, which looks exactly like an
   empty file. Every node and field name must be probed against the pinned grammar (or read from
   `node-types.json`) before a query ships. The grammar-contract test is the backstop, not a
   substitute.
3. **Pydantic and dataclass primary docs were never fetched**, in this round or the previous one.
   The v1/v2 decorator names and `model_config` details are working knowledge, and attrs is likewise
   uncited (hence `assumed=True` on that branch). Confirm against the Pydantic and `dataclasses`
   docs before stating a version fingerprint as fact in output (python Q6 gaps).
4. **A stale `render-app/public/chunks/<chunkId>/` from an earlier run could resurrect a blocked
   chunk into the video.** Whether `build_render_bundle` writes one manifest per chunk or one for
   the set determines whether a blocked chunk needs explicit removal from the previous run's staging
   directory — and the mirror store's whole purpose is persistence across runs, so a stale directory
   is the expected state, not the exceptional one. **Check this before the render gate lands**, or
   the gate blocks a chunk that still ships (shared §4 gaps).
5. **The Fiber path-parameter syntax list is still uncited.** `docs.gofiber.io/guide/routing` was
   unreachable for the validation report and was not re-attempted. The resolver is
   parameter-syntax-agnostic (it only joins segments), so this does not block it — but
   `static_or_dynamic`, which currently tests `":" in path`, is unverified against Fiber's full set
   (`:param?`, `+`, `*`, `:id<int>`) (shared §2 gaps).

Also carried, lower severity:
- `scripts/run_backend_pilot.py` and `src/narrate/pipeline.py` were never read; the exit-code plumbing
  and `generate_narration_for_repo`'s signature are assumed, not confirmed (shared §4 gaps).
- `src/validate/schema_check.py` and `claude/json-structure-rules.md` were not read in the Express
  pass; if `middleware` ships without updating both, Express records go invalid for a new reason
  (express Part A gaps).
- The Express mount-graph staleness interaction (§8) has no test designed for it, because
  `mirror_store.py` was not read in that pass.
- `@Qualifier`/`@Primary` precedence, `server.servlet.context-path`, the full Spring Data keyword
  table, JLS §6.6 access rules and Express 5's treatment of a 4-arity *route* handler are all
  uncited. Each is handled by emitting all candidates with `assumed=True` rather than picking a
  winner — which is the right response to an uncited rule, but it means those records will be hedged
  in narration until someone fetches the page.
- Nest, Koa and Fastify are detected but not extracted, so they still produce `confidence: 0`
  records. Deliberate — a loud placeholder beats Express semantics applied to Koa's `ctx` — but it
  means the render gate will block them, which is the intended outcome and should be stated in the
  release note so it does not read as a regression.
- No benchmark comparing tree-sitter extraction accuracy against regex, or against a compiler API,
  was found by any of the four researchers. The case for the substrate rests on the structural
  argument (balanced delimiters are not regular) and on the measured failures in 14, not on
  published error rates. There is also no gold-standard repo in the project to measure route recall
  against; the practical proxy is a hand-generated FastAPI `openapi()` dump compared outside the
  pipeline, as a one-off measurement — never a pipeline step, since the pipeline must never import
  the target repo.
