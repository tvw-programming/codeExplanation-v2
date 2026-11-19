# Shared infrastructure for the Python / Java-Spring / Express extractors

Scope: the layer all three new extractors sit on. Nothing here designs a per-stack extractor.
Everything is designed against the code as it stands at `/home/claude/codeExplanation-v2`, read in
full for this note: `src/extract/common.py`, `src/extract/json_builder.py`,
`src/extract/reuse_pipeline.py`, `src/extract/go_extractor.py`, `src/storage/mirror_store.py`,
`src/validate/schema_check.py`, `src/pilot/run_pilot.py`, `src/narrate/script_builder.py`,
`src/narrate/function_narration.py`, `src/narrate/file_overview.py`, `run-local.sh`, `tests/`.

Current anchor facts (read, not assumed):
- `EXTRACTOR_VERSION = 4` in `/home/claude/codeExplanation-v2/src/storage/mirror_store.py`; a stored
  record is reused only when `contentHash` matches **and** `stored.get("extractorVersion", 1) ==
  EXTRACTOR_VERSION` (`needs_reanalysis`). So any new field is a version bump, and the bump alone
  invalidates every cached chunk.
- `schema_check.REQUIRED_CORE_FIELDS` is ten fields; an **empty list is a valid list**, which is why
  the Angular record validates clean with nothing in it.
- `run_pilot.run_pilot()` computes `schema_result = validate_records(records)` and then calls
  `generate_narration_for_repo(records)` and `build_render_bundle(...)` for **every** chunk
  unconditionally. `schemaValidation.invalid` is recorded into `pilot_report.json` and never read
  again. Report-only, confirmed.
- `script_builder._hedge(sentence, assumed)` prepends the single phrase `HEDGE_PHRASE = "It looks
  like"` and lowercases the first character. It is called at 7 sites, all gated on one per-item
  boolean: `route["assumed"]`, `handler["assumed"]`, `call["assumed"]`. There is no fidelity axis.
- `importantFunctions` sentences are **never** hedged — the comment at `script_builder.py:122-124`
  says so explicitly ("taken directly from the extracted code, so there is no `assumed` flag"). That
  comment is true of what the field carries and false of what the facts are worth: the line range in
  it comes from `go_extractor._find_matching_brace_end_line`, a raw character scan with no string or
  comment awareness.
- `function_narration.build_function_narration` opens with `f"Next is {name}, at lines
  {line_range[0]} to {line_range[1]}."` — it asserts an end line that regex extraction guesses.

---

## 1. The `fidelity` field, and the rule that refusing to narrate beats guessing

### Takeaway

`fidelity` is one new top-level string per record, set by the extractor module that produced the
record, and it earns its keep in exactly two places: it downgrades assertions about facts the
substrate cannot actually establish (end-of-definition line ranges, export status, resolved paths),
and it makes the companion concept — an aspect that was *not analyzed*, as distinct from an aspect
that was analyzed and found empty — representable. The second half is the more valuable one: today
`routes: []` means both "this file has no routes" and "nobody wrote a route analyzer for Spring", and
narration cannot tell them apart.

### Schema change

Two new top-level keys on every chunk record:

```jsonc
{
  "fidelity": "regex",            // "regex" | "syntax" | "typed"   (required, enum)
  "notAnalyzed": [                // required, list, may be empty
    {
      "aspect": "routes",         // one of the record's content field names
      "reason": "Route extraction for Spring MVC is not implemented in this version.",
      "verify": "Read the @RequestMapping/@GetMapping annotations on this class to get the real URLs."
    }
  ]
}
```

Rules, in order of importance:

1. **`fidelity` is the weakest substrate any *spoken* fact in the record came from**, not the best.
   A Python extractor that reads functions from `ast` but recovers a Flask blueprint prefix with a
   regex over `register_blueprint(` reports `"syntax"` only if that prefix fact is additionally
   marked `assumed: true` on the route entry; otherwise it reports `"regex"`. Per-item `assumed`
   stays the fine-grained channel (it already exists and already flows into `_hedge`); `fidelity` is
   the coarse, per-record substrate claim. They compose; neither replaces the other.
2. **`"typed"` means a type resolver answered a question the parse tree could not** — which
   interface a Spring field's declared type is implemented by, whether a Go type satisfies an
   interface. A parse tree alone is `"syntax"`, however good. Nothing in the repo is `"typed"` today
   and nothing in the three new extractors needs to be; the rung exists so the Spring DI work (item 7
   of the validation report's sequence) has somewhere to land without a second schema change.
3. **A placeholder record is not a fidelity level.** The `else` branch of
   `reuse_pipeline.extract_repo_with_reuse` (lines 85-94) must not acquire `"fidelity": "regex"` — it
   read nothing. It gets `"fidelity": "none"` as a fourth enum value and is always blocked from
   rendering (§4). Keeping it in the same enum, rather than omitting the key, means `schema_check`
   can require the key unconditionally.
4. **Three states per content aspect, not two.** For each of `routes`, `eventHandlers`, `apiCalls`,
   `dataModels`, `importantFunctions`, `sideEffects`, `inputs`:
   - items present → the list, as now;
   - analyzer ran, found nothing → `[]`, aspect absent from `notAnalyzed`;
   - no analyzer for this framework/aspect → `[]`, **and** an entry in `notAnalyzed`.
   An extractor that cannot distinguish (b) from (c) must report (c). That is the whole rule.

### Where it is set

One constant per extractor module, read by the record builder — not a literal sprinkled through
`json_builder.py`:

```python
# src/extract/ts_extractor.py
FIDELITY = "regex"
# src/extract/go_extractor.py
FIDELITY = "regex"            # -> "syntax" in the same PR that moves it onto tree-sitter
# src/extract/py_extractor.py (new)
FIDELITY = "syntax"           # stdlib ast
# src/extract/java_extractor.py (new)
FIDELITY = "syntax"           # tree-sitter-java
# src/extract/js_extractor.py (new, Express)
FIDELITY = "syntax"           # tree-sitter-javascript
```

`json_builder.build_frontend_chunk_record` / `build_backend_go_chunk_record` and every new builder
take `fidelity: str` and `not_analyzed: list[dict]` and emit them beside `confidence`. Two
consequences worth stating because they are easy to get wrong:

- **A builder must not compute `fidelity` from the data.** A Python file with zero decorators does
  not make the extractor less capable. Fidelity describes the tool, not the file.
- **An extractor that falls back mid-file degrades the whole record.** If the tree-sitter wrapper
  raises `ParserUnavailable` (§3) and the Express extractor falls back to regex for that file, the
  record is `"regex"`, not `"syntax"`. The wrapper returns which path it took; the builder must not
  hardcode the optimistic value. Concretely: the extractor returns its facts in a small result object
  carrying `fidelity`, and the builder copies it through rather than reading the module constant.

`confidence_from_flags` is **not** changed to incorporate fidelity. Confidence already means "how
many of my claims did I have to mark assumed", it is documented as such in `common.py:109-122`, and
overloading it would make the existing 0.85 threshold and `EMPTY_EXTRACTION_CONFIDENCE = 0.3`
mean two things at once. Fidelity is a separate, orthogonal axis and the file card should show both.

### How it flows into narration

`_hedge` becomes a three-rung ladder in `script_builder.py`, replacing the current boolean:

```python
# src/narrate/script_builder.py

HEDGE_PHRASE = "It looks like"                      # unchanged, rung 2
TEXTUAL_PHRASE = "Going by the text of the file,"    # new, rung 1

PLAIN, TEXTUAL, ASSUMED = 0, 1, 2

def hedge_level(record: dict, item_assumed: bool) -> int:
    """One idea per sentence, so at most ONE hedge phrase is ever applied.
    An explicitly assumed claim outranks a weak substrate: 'it looks like'
    already tells the viewer not to trust the detail, and stacking
    'going by the text of the file, it looks like...' is both worse prose
    and no more honest."""
    if item_assumed:
        return ASSUMED
    if (record.get("fidelity") or "regex") == "regex":
        return TEXTUAL
    return PLAIN      # "syntax" and "typed" assert plainly


def _hedge(sentence: str, level: int) -> str:
    if level == PLAIN:
        return sentence
    phrase = TEXTUAL_PHRASE if level == TEXTUAL else HEDGE_PHRASE
    return f"{phrase} {sentence[0].lower()}{sentence[1:]}"
```

The existing call sites change from `_hedge(sentence, bool(route.get("assumed")))` to
`_hedge(sentence, hedge_level(record, bool(route.get("assumed"))))`. Keeping `_hedge`'s shape and
the fixed-phrase discipline matters: the narrator rules in the module docstring call for "a single
fixed phrase", and this keeps it to two fixed phrases with a documented precedence rather than
generated prose.

**Fidelity also gates which sentences exist at all.** This is the half that buys more than wording:

| Sentence | regex | syntax / typed | Why |
|---|---|---|---|
| Function opener | `"Next is loadUsers, starting at line 12."` | `"Next is loadUsers, at lines 12 to 40."` | The end line is `_find_matching_brace_end_line`'s guess; a backtick raw string containing `}` already measured 2 instead of 3. Don't speak a number the substrate gets wrong — omit the clause, keep the one it gets right. |
| Export role | omitted for any language other than TypeScript/JavaScript | spoken | `function_context.is_exported` falls back to `signature.startswith("export")`; `export` never appears in Python or Java, so at regex fidelity the claim is not merely uncertain, it is systematically false. Omission beats hedging a known-wrong fact. |
| `"Nothing else in this chunk calls it and it is not exported, so it is used only where it is defined."` | **never spoken at regex fidelity** | spoken | This is an assertion of *absence* built on a name-substring call graph. At regex fidelity the honest version is silence. |

Concrete before/after pairs, in the sentence shapes the code produces today:

**Route (`routes` entry, `method: "GET"`, `path: "/api/v1/users"`, `assumed: false`)**
- fidelity `regex` → `"Going by the text of the file, a GET request to /api/v1/users is handled here."`
- fidelity `syntax` → `"A GET request to /api/v1/users is handled here."`
- `assumed: true`, any fidelity → `"It looks like a GET request to /api/v1/users is handled here."`
  (unchanged from today — this is the existing behaviour, and the point is that it stays put.)

**Event handler (`name: "handleSubmit"`, `eventType: "submit"`, `assumed: false`)**
- `regex` → `"Going by the text of the file, the handleSubmit handler responds to a submit event."`
- `syntax` → `"The handleSubmit handler responds to a submit event."`

**Function (`name: "loadUsers"`, `lineRange: [12, 40]`, `exported: true`, `calledBy: []`)**
- today, all fidelities → `"Next is loadUsers, at lines 12 to 40. It is exported, so other files can use it too. Which ones is not visible from this chunk alone."`
- `regex` → `"Next is loadUsers, starting at line 12."` (export sentence dropped for non-TS; range truncated to its reliable half)
- `syntax` → `"Next is loadUsers, at lines 12 to 40. It is exported, so other files can use it too. Which ones is not visible from this chunk alone."`

**Data model (`dataModels` entry, `name: "Alumni"`, 2 fields)** — `build_purpose_beat` /
`file_overview` currently count these plainly.
- `regex` → `"Going by the text of the file, it defines the Alumni shape, with 2 fields."`
- `syntax` → `"It defines the Alumni shape, with 2 fields."`

`function_narration.py` needs the record's fidelity, which it does not currently receive —
`build_function_narration(fn)` takes only the function dict. Cheapest correct change: `json_builder`
stamps `fn["fidelity"]` onto each `importantFunctions` entry as it builds it (the second pass at
`json_builder.py:138-148` already mutates each entry via `build_function_context`), so
`function_narration` reads `fn.get("fidelity", "regex")` and no signature changes. That also makes
per-item fidelity possible later without another plumbing pass.

### The companion rule: refusing to narrate

**When to refuse.** The pipeline emits a `notAnalyzed` entry, and says so, when **all three** hold:

1. the aspect is one the detected framework demonstrably has (Spring MVC has routes; Express has a
   middleware chain; FastAPI has routers) — detection, not the file's contents, decides this;
2. no analyzer for that aspect ran over this file;
3. the record's list for that aspect is therefore empty **for a reason that is not the file's**.

**What is said.** One disclosure sentence, appended to the **recap** beat, not the flow beat —
putting it in the flow would interleave a meta-statement with the walkthrough and steal a VISUAL cue
slot it has no lines to highlight:

> `"Routes for Spring Boot are not analyzed by this version of the pipeline, so this walkthrough does not cover the URLs this controller serves."`

Template: `"{Aspect} for {framework} {is|are} not analyzed by this version of the pipeline, so this
walkthrough does not cover {consequence}."` Fixed per aspect, mechanically generated from the
`notAnalyzed` entry — consistent with `script_builder`'s template-not-LLM stance. The `reason`/
`verify` strings are for the operator and the file card, **not** spoken: `notes` is never spoken
(stated in `script_builder`'s docstring) and these are the same kind of field.

**What must be suppressed.** A `notAnalyzed` aspect must suppress every sentence that implies
absence. `build_purpose_beat` currently reads `if routes: ... elif handlers: ...` — benign. But
`build_connections_beat`'s `"{feature} stands on its own here, with no links to chunks covered
elsewhere."` is an assertion of absence, and `file_overview`'s caller/callee card is another. Rule:
if `dependencies`/`featureMapping` is in `notAnalyzed`, that sentence is replaced by the disclosure
form, never spoken as-is.

**And the stronger case:** when *every* content aspect of a record is empty and the reason is
`notAnalyzed`, the right answer is not a 28-second section that says only "not analyzed". It is to
**not render that section at all** and move the disclosure up to the run summary — "3 files in this
repository are not analyzed by this version of the pipeline" — which is §4's render gate. The
refusal rule and the enforcing-validation rule are the same rule seen from two ends.

### Migration note

- **`EXTRACTOR_VERSION: 4 → 5`**, history entry: `5 - records carry fidelity ("regex"|"syntax"|
  "typed"|"none") and notAnalyzed, so narration can hedge by substrate and disclose unanalyzed
  aspects instead of emitting an empty list.`
- **Backward compatibility is free and, unusually, *correct* rather than merely tolerable.** Every
  record written by versions 1-4 came from `ts_extractor` or `go_extractor`, both regex. So
  `record.get("fidelity", "regex")` is not a defensive default, it is the true value, and
  `record.get("notAnalyzed") or []` is likewise accurate (nothing was ever disclosed). Narration code
  therefore reads both through `.get` with those defaults and needs no migration script.
- **Cost of the bump: one full re-extract of every stored chunk.** `needs_reanalysis` returns True
  for every record on the next run. That is the intended behaviour and the reason the field exists
  (`mirror_store.py:24-33`), so no store rewrite is needed — but say it in the release note, because
  on a large repo the first run after this PR is a cold run.
- **`schema_check`:** add `"fidelity"` to `REQUIRED_CORE_FIELDS`, add `VALID_FIDELITY = {"regex",
  "syntax", "typed", "none"}` with an enum check mirroring `VALID_CONFIDENCE_LEVELS`, and require
  `notAnalyzed` to be a list (may be empty) exactly as `featureMapping` is. Adding `fidelity` to the
  required list means every pre-version-5 stored record is schema-invalid if it is ever re-validated
  — acceptable precisely because the version gate guarantees it will be re-extracted before it is
  re-validated. Do not special-case it.
- **One trap:** `reuse_pipeline` writes stored records for *reused* chunks too (the final
  `for record in records: write_stored(...)` loop). A reused record carries its stored
  `extractorVersion`, so if the field were ever written without bumping, the cache would silently
  serve mixed-vintage records. It won't here, because reuse is gated on the version — but this is why
  **one bump per shipped change**, not one bump per batch of changes, is the right discipline.

### Gaps

- No source was found, and none is likely to exist, on whether a spoken substrate qualifier
  (`"Going by the text of the file"`) measurably changes viewer trust calibration. The phrasing is
  reasoned from the project's own honesty stance, not from evidence about comprehension.
- The exact wording of `TEXTUAL_PHRASE` should be checked against TTS output before it is locked:
  `function_narration.speakable` strips em dashes and backticks for exactly this reason, and a
  prefix clause that recurs on every sentence in a regex-fidelity chunk may grate at 130 wpm. A
  shorter variant ("From the text,") is a one-line change if it does.

---

## 2. The shared route-prefix resolver

### Takeaway

One module, `src/extract/route_prefix.py`, ~120 lines, no parser dependency, that turns "which
symbol got its prefix from which other symbol" into a full path plus a resolved/assumed flag plus a
note. Every one of the five stacks hands it the same three things — edges, roots, and route
registrations — and differs only in the regex or query that produces them. `go_extractor` should be
refactored onto it: the refactor is small, it is a strict quality upgrade (the Go version cannot
represent a non-literal prefix at all, and silently returns a *partial* path on a cycle), and
leaving it alone guarantees two implementations of the one algorithm the validation report calls the
largest correctness win per unit of work.

### Cited problem statement (from the validation report, which cites the framework docs)

| Stack | Prefix source | Doc |
|---|---|---|
| Spring | class `@RequestMapping("/persons")` + method `@GetMapping("/{id}")` → "effectively /persons/{id}" | [Spring: Mapping Requests](https://docs.spring.io/spring-framework/reference/7.0/web/webflux/controller/ann-requestmapping.html) |
| Express | `app.use('/birds', birds)` in the parent file, transitively | [Express routing](https://expressjs.com/en/guide/routing.html) |
| Go Fiber | nested `Group` calls; `/api` → `/v1` → `.Get("/list")` = `/api/v1/list` | [Fiber grouping](https://docs.gofiber.io/guide/grouping) |
| FastAPI | `APIRouter(prefix="/items")` + `include_router(..., prefix="/admin")`; the router variable "can be named anything" | [FastAPI: Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) |
| Flask | `register_blueprint(bp, url_prefix='/pages')`; the decorator only "record[s] the intention of registering" | [Flask Blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) |

Three shapes the design must cover, because each of them appears in at least one of the five:

- **Chained child→parent** (Fiber groups, FastAPI nested routers): the child names its parent.
- **Parent→child mount** (Express `app.use`, Flask `register_blueprint`, FastAPI
  `include_router`): the *parent* names the child and supplies the prefix. Same graph, opposite
  declaration direction — the input interface must accept either and normalise.
- **Containment** (Spring class-level + method-level): the "parent" is a lexical container, not a
  variable. This is a one-edge chain whose root is the class, which is itself a root with the
  class-level mapping as its prefix.

### Input interface

```python
# src/extract/route_prefix.py
"""Shared route-prefix resolution.

One dataflow pass, five stacks. Every framework in this project composes a
route's real URL out of facts that are NOT on the route's own line: a Fiber
group chain, an Express app.use mount in another file, a Spring class-level
@RequestMapping, a FastAPI include_router prefix, a Flask url_prefix. The
shape of the problem is identical every time -- a directed graph of
(symbol -> parent symbol, literal prefix segment) edges whose roots carry no
prefix -- so it is solved once here and each extractor only has to produce
the edges.

The honesty contract: this module NEVER returns a bare string. It returns the
path it could build AND whether that path is complete, because a confidently
wrong URL is the worst output this pipeline can produce (a viewer cannot
falsify it) and a half-built path reported as complete is exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A symbol id is opaque to this module and chosen by the extractor. Within one
# file a bare local name is enough ("v1"). Across files -- Express -- it must
# be qualified, e.g. ("src/routes/birds.js", "<module>"), so two files that
# both call their router `router` do not collide. Any hashable value works.
SymbolId = object


@dataclass(frozen=True)
class PrefixEdge:
    """'`child` inherits `parent`'s prefix, and adds `segment` to it.'

    segment is None when the extractor saw a prefix it could not read as a
    literal -- app.Group(basePath), url_prefix=PREFIX, include_router(r,
    prefix=settings.API_V1) -- which is the single most common reason a real
    repo's path is unresolvable. Carrying None rather than "" is the whole
    point: "" is a claim that the prefix is empty, None is an admission that
    it is unknown.
    """
    child: SymbolId
    parent: SymbolId | None          # None == this symbol is itself a root
    segment: str | None              # literal path segment, or None if non-literal
    declared_at: int | None = None   # 1-indexed line, for the note and for cues
    expression: str | None = None    # verbatim source of a non-literal prefix


@dataclass(frozen=True)
class Resolution:
    """What came back. `path` is always safe to show; `resolved` says whether
    it is the whole truth."""
    path: str
    resolved: bool
    note: str | None
    chain: tuple[SymbolId, ...]          # child -> ... -> root, for debugging
    unresolved_reason: str | None = None  # "unknown_parent"|"non_literal"|"cycle"|"depth"


MAX_DEPTH = 32   # a real mount chain is 2-4 deep; this is a runaway guard
```

What each extractor must hand over — and nothing else:

```python
@dataclass
class PrefixGraph:
    edges: dict[SymbolId, PrefixEdge] = field(default_factory=dict)
    roots: set[SymbolId] = field(default_factory=set)

    def add_child_edge(self, child, parent, segment, *, declared_at=None, expression=None):
        """Fiber groups, FastAPI nested routers: the CHILD names its parent."""
        self.edges[child] = PrefixEdge(child, parent, segment, declared_at, expression)

    def add_mount(self, parent, child, segment, *, declared_at=None, expression=None):
        """Express app.use, Flask register_blueprint, FastAPI include_router:
        the PARENT names the child. Normalised to the same edge so the
        resolver only ever sees one direction. A second mount of the same
        child is a real Express pattern (the same router mounted at two
        prefixes) and is NOT representable here -- it is reported as
        ambiguous rather than silently last-wins."""
        existing = self.edges.get(child)
        if existing is not None and (existing.parent, existing.segment) != (parent, segment):
            self.edges[child] = PrefixEdge(child, parent, None, declared_at,
                                           expression="<mounted at more than one prefix>")
            return
        self.edges[child] = PrefixEdge(child, parent, segment, declared_at, expression)

    def add_root(self, symbol, segment=None, *, declared_at=None):
        """fiber.New(), the Express `app`, a Spring class whose class-level
        @RequestMapping is its own prefix, a FastAPI app with root_path."""
        self.roots.add(symbol)
        if segment:
            self.edges[symbol] = PrefixEdge(symbol, None, segment, declared_at)
```

### Core algorithm

```python
def resolve(graph: PrefixGraph, symbol: SymbolId) -> Resolution:
    """Walk `symbol` up to a root, collecting prefix segments.

    Terminates on four conditions, three of which mean "assumed":
      - reached a declared root            -> resolved
      - hit a symbol with no edge          -> unknown_parent (prefix lives in
                                              a file/call site not analysed)
      - hit an edge with segment is None   -> non_literal
      - revisited a symbol / exceeded      -> cycle / depth
        MAX_DEPTH
    In every unresolved case the segments gathered SO FAR are still returned,
    because a partial prefix is genuinely useful to a reviewer -- but
    `resolved` is False and the note names what is missing, so narration
    hedges and never asserts the URL.
    """
    segments: list[str] = []
    chain: list[SymbolId] = []
    seen: set[SymbolId] = set()
    current = symbol
    reason: str | None = None
    detail: str | None = None

    for _ in range(MAX_DEPTH):
        chain.append(current)
        if current in seen:
            reason, detail = "cycle", f"prefix chain revisits {current!r}"
            break
        seen.add(current)

        edge = graph.edges.get(current)
        if edge is None:
            # No edge at all. A declared root legitimately has none.
            if current in graph.roots:
                return Resolution(_join(segments), True, None, tuple(chain))
            reason = "unknown_parent"
            detail = (f"{current!r} is never given a prefix in the files that were "
                      f"analysed; its prefix is set at a call site elsewhere")
            break

        if edge.segment is None:
            reason = "non_literal"
            detail = (f"the prefix for {current!r} is {edge.expression or 'a non-literal expression'}"
                      f"{f' at line {edge.declared_at}' if edge.declared_at else ''}, "
                      f"which static analysis cannot evaluate")
            break

        segments.append(edge.segment)

        if edge.parent is None or edge.parent in graph.roots and edge.parent not in graph.edges:
            # Reached a root: either this edge declared itself rootless, or the
            # parent is a root carrying no prefix of its own.
            chain.append(edge.parent) if edge.parent is not None else None
            return Resolution(_join(segments), True, None, tuple(c for c in chain if c is not None))

        current = edge.parent
    else:
        reason = "depth"
        detail = f"prefix chain exceeded {MAX_DEPTH} levels"

    note = (f"Route prefix could not be fully resolved: {detail}. "
            f"The path shown is built from the {len(segments)} segment(s) that were resolvable "
            f"and may be missing a leading prefix -- verify against the application's "
            f"route registration before relying on it.")
    return Resolution(_join(segments), False, note, tuple(c for c in chain if c is not None),
                      unresolved_reason=reason)


def _join(segments_child_first: list[str]) -> str:
    """Segments arrive child-first (we walked upward), so reverse them, strip
    stray slashes, and rebuild one normalised path. '' stays '' rather than
    becoming '/', so a rootless route is visibly rootless."""
    parts = [s.strip("/") for s in reversed(segments_child_first)]
    parts = [p for p in parts if p]
    return ("/" + "/".join(parts)) if parts else ""


def full_route_path(graph: PrefixGraph, symbol: SymbolId, route_path: str) -> Resolution:
    """The call every extractor actually makes: resolve the registering
    symbol's prefix and append this one route's own path."""
    prefix = resolve(graph, symbol)
    tail = route_path.strip()
    if tail and not tail.startswith("/"):
        tail = "/" + tail
    path = (prefix.path + tail) or "/"
    # Fiber/Express both treat a trailing slash on a prefix as insignificant;
    # '/api' + '/' must not become '/api//'.
    path = path.replace("//", "/") if path != "//" else "/"
    return Resolution(path, prefix.resolved, prefix.note, prefix.chain, prefix.unresolved_reason)
```

### Output, and how an unresolvable prefix is reported

A `routes` entry in the record gains two keys and keeps its existing `assumed`/`notes` contract:

```jsonc
{
  "path": "/v1/users",
  "method": "GET",
  "pathResolved": false,              // NEW: did the prefix chain reach a root
  "prefixChain": ["v1", "api"],       // NEW: stringified chain, operator-facing
  "assumed": true,                    // existing: stays true whenever !pathResolved
  "notes": "Route prefix could not be fully resolved: 'api' is never given a prefix in the files that were analysed; its prefix is set at a call site elsewhere. The path shown is built from the 1 segment(s) that were resolvable and may be missing a leading prefix -- verify against the application's route registration before relying on it."
}
```

Mapping into the existing honesty machinery, all of which already works:

- `assumed: true` → `_hedge` → `"It looks like a GET request to /v1/users is handled here."`
- `assumed` count → `confidence_from_flags` → confidence down → `confidenceLevel` "medium"/"low"
- `confidenceLevel` in `{"low","medium"}` → `file_overview` risk line (`file_overview.py:419-420`)
- the assumed-claim count → `file_overview.py:418` `"N claim(s) could not be verified and are marked assumed"`

**Hard rule:** `pathResolved: false` ⇒ `assumed: true`. Never the reverse (a resolved path can still
be assumed for other reasons, e.g. Fiber's protection heuristic). An extractor that sets
`pathResolved` without setting `assumed` is a bug, and the test plan locks it.

**Unresolvable-prefix escalation.** When *no* route in a file resolves — the whole file's prefixes
come from another file the chunker never opened, which is the common Express case — the extractor
adds a `notAnalyzed` entry for `routes`' prefixes rather than only hedging 20 sentences:

```python
if routes and not any(r["pathResolved"] for r in routes):
    not_analyzed.append({
        "aspect": "routes",
        "reason": "No route in this file could be traced to a mounted root; the prefixes are "
                  "applied where this router is mounted, in a file outside this chunk.",
        "verify": "Find the app.use()/include_router()/register_blueprint() call that mounts this "
                  "router and prepend its prefix to every path listed here.",
    })
```

That is the difference between "incomplete but honest" and "empty and should not be narrated" (§4)
drawn at the aspect level: the routes *are* narratable, hedged, with one disclosure sentence.

### Should `go_extractor` be refactored onto it?

**Yes, in the same PR, with a behavioural-parity test.** `_resolve_group_prefix` is a correct
skeleton — it was just fixed to compose nested prefixes and it already returns a
`(prefix, fully_resolved)` pair, which is the right shape — but it has four properties the shared
version must not inherit, and keeping two copies means fixing each twice:

1. **It cannot represent a non-literal prefix.** `ROUTE_GROUP_RE` requires a quoted literal, so
   `api := app.Group(basePath)` produces *no edge at all*. The resolver then finds `api` in neither
   `group_parents` nor `roots`, falls to `prefix = None`, and `extract_routes` turns that into
   `prefix = prefix or ""` — a path that silently omits the prefix entirely with
   `prefix_assumed = True`. The flag saves it, but the `non_literal` and `unknown_parent` cases are
   conflated and the note cannot name the expression. The shared `PrefixEdge(segment=None,
   expression="basePath")` distinguishes them and the note becomes actionable.
2. **`roots.add("app")` is an unconditional guess.** `go_extractor.py` adds the literal name `"app"`
   to the root set "even when `fiber.New()` is elsewhere". If a handler-registration function takes
   `app *fiber.App` as a *parameter* and the real prefix is applied at the call site, this reports
   the chain as **fully resolved** and `prefix_assumed` as False — a confidently wrong URL, the
   exact failure mode the report calls unfalsifiable. In the shared module this becomes an explicit,
   per-extractor `graph.add_root("app")` the Go extractor can keep if it wants, but as a named
   conventional-name assumption that a test can assert against, not a constant buried in a function.
3. **The cycle branch returns a partial prefix with no note.** `return "".join(reversed(segments)),
   False` — correct behaviour, zero explanation. The shared version returns `unresolved_reason`
   and a sentence.
4. **It joins with bare `"".join` plus `rstrip("/")` at the call site**, so `/api/` + `/v1` + `/`
   normalisation is spread across two functions. `_join` centralises it, which matters more for
   Express (`app.use('/birds/', ...)`) than for Fiber.

Refactor shape: `extract_routes` keeps every regex and keeps `USE_CALL_RE`/protection logic
untouched; it replaces the `group_parents`/`roots`/`group_prefixes` triple with one `PrefixGraph` and
calls `full_route_path`. `_resolve_group_prefix` is deleted. `tests/test_go_extractor.py` keeps its
existing route assertions unchanged as the parity test — if the nested-prefix fix's behaviour
changes, the refactor is wrong.

### Migration note

- **`EXTRACTOR_VERSION: 5 → 6`**, history entry: `6 - route entries carry pathResolved and
  prefixChain from the shared prefix resolver; paths that could not be traced to a mounted root are
  marked assumed with a note naming what is missing.`
- Land it as its **own** bump, separate from §1. Both bumps force a full re-extract, so batching
  them saves one cold run — but a single version number that covers two independent changes makes
  "which extractor wrote this record" unanswerable when a regression shows up in a user's store.
- Backward compatibility: `route.get("pathResolved")` is `None` on pre-version-6 records. Narration
  must treat `None` as "unknown", **not** as False — a pre-6 Go record already carried
  `assumed: true` on every route (`go_extractor` sets it unconditionally), so `assumed` alone
  already produces the hedge and `pathResolved` adds nothing for old records. Concretely:
  `resolved = route.get("pathResolved"); if resolved is False: ...` — never `if not resolved`.
- `schema_check`: do **not** add `pathResolved` to the required list. Required-field checks in that
  module are top-level only, and adding per-item structural validation is a separate design. Add it
  instead as a render-gate consistency check (§4): `pathResolved is False and not assumed` is a
  blocking inconsistency, because it means an extractor is about to assert a path it could not build.

### Gaps

- **The Fiber path-parameter syntax list is still uncited** — `https://docs.gofiber.io/guide/routing`
  was unreachable for the validation report and I did not re-attempt it here. The resolver is
  parameter-syntax-agnostic by design (it only joins segments), so this does not block it, but
  `static_or_dynamic` classification, which currently tests `":" in path`, is unverified against
  Fiber's full set (`:param?`, `+`, `*`, `:id<int>`).
- **Express's extensionless module resolution** (`require('./birds')` → `birds.js`,
  `birds/index.js`, `.mjs`, `.cjs`) is what produces the cross-file `SymbolId`s, and it is not
  designed here — it belongs to the Express extractor, not the shared layer. The shared layer's only
  requirement is that the id be hashable and file-qualified.
- No source was found for whether any ecosystem tool resolves these prefixes statically;
  `express-list-endpoints` needs a live app instance and is Express 4 only
  ([express-list-endpoints](https://github.com/AlbertoFdzM/express-list-endpoints)), which is
  evidence that a static resolver is novel work rather than a port.

---

## 3. Tree-sitter as a shared substrate

### Takeaway

One wrapper module, `src/parse/tree_sitter_support.py`, targeting the **tree_sitter 0.25/0.26
API** — `Language(capsule)`, `Parser(language)`, `Query(language, src)` executed through
`QueryCursor(query).captures(node)`. All four grammar packages exist on PyPI under the names the
convention predicts, all ship prebuilt `abi3` wheels for Linux/macOS/Windows, and the previously
unconfirmed one (`tree-sitter-go`) is confirmed below. I installed all five packages and ran the API
live rather than reading docs about it.

### Verified packaging (PyPI, checked 2026-11-19)

| PyPI name | Latest version | Last upload | Wheels in latest release | Prebuilt? | Grammar ABI (measured) |
|---|---|---|---|---|---|
| [`tree-sitter`](https://pypi.org/project/tree-sitter/) (runtime) | **0.26.1** | 2026-11-09 | 40 bdist_wheel + 1 sdist | yes — cp310–cp314, macOS x86_64/arm64, manylinux x86_64/aarch64, Windows | runtime `LANGUAGE_VERSION = 15`, `MIN_COMPATIBLE_LANGUAGE_VERSION = 13` |
| [`tree-sitter-java`](https://pypi.org/project/tree-sitter-java/) | **0.23.5** | 2024-12-21 | 7 wheels (`cp39-abi3`) + sdist | yes | 14 |
| [`tree-sitter-javascript`](https://pypi.org/project/tree-sitter-javascript/) | **0.25.0** | 2025-09-01 | 8 wheels (`cp310-abi3`) + sdist | yes | 15 |
| [`tree-sitter-typescript`](https://pypi.org/project/tree-sitter-typescript/) | **0.23.2** | 2024-11-11 | 7 wheels (`cp39-abi3`) + sdist | yes | 14 |
| [`tree-sitter-go`](https://pypi.org/project/tree-sitter-go/) | **0.25.0** | 2025-08-29 | 8 wheels (`cp310-abi3`) + sdist | yes | 15 |
| [`tree-sitter-python`](https://pypi.org/project/tree-sitter-python/) | **0.25.0** | 2025-09-11 | 8 wheels (`cp310-abi3`) + sdist | yes | 15 | 

**`tree-sitter-go` is confirmed to exist under that exact name**, which closes the open item the
validation report flagged ("The `tree-sitter-go` PyPI package name is unconfirmed... Its PyPI page
was blocked"). Measured by installing it and loading the grammar, not inferred from the naming
convention.

Two packaging facts that matter for the pin:

- **Grammar ABI mismatch is a non-issue.** Java and TypeScript ship ABI 14 grammars; the 0.26.1
  runtime accepts 13-15. Verified by loading all four grammars under 0.26.1 in one process and
  parsing with each. Do not "upgrade" java/typescript for ABI reasons; there is nothing newer.
- **Each grammar declares `tree-sitter` only as an *extra*** (`tree-sitter~=0.22; extra == "core"`
  for java, `~=0.24` for javascript and go, `~=0.23` for typescript — read from the installed
  distributions' metadata). So pip imposes no runtime constraint and `pip install tree_sitter_java`
  alone will not pull the runtime in. The project must pin the runtime itself in
  `requirements.txt`.

### Which runtime API version the wrapper targets, and why it matters

The query API broke across majors. Measured in a venv, same grammars, three runtimes:

| runtime | `tree_sitter.QueryCursor` | `Query.captures` |
|---|---|---|
| 0.24.0 | **absent** | present |
| 0.25.2 | present | **absent** |
| 0.26.1 | present | **absent** |

So `Query.captures(...)` — which is what almost every tutorial and most LLM training data shows —
raises `AttributeError: 'tree_sitter.Query' object has no attribute 'captures'` on anything ≥0.25.
Live output from my probe:

```
Query.captures FAILED: AttributeError 'tree_sitter.Query' object has no attribute 'captures'
QueryCursor.captures: {'ann': [b'GetMapping'], 'args': [b'("/{id}")'], 'm': [b'get']}
```

The current usage section on [PyPI: tree-sitter](https://pypi.org/project/tree-sitter/) (0.26.1)
documents the new form: `Language(tspython.language())`, `Parser(PY_LANGUAGE)`,
`QueryCursor(query).captures(tree.root_node)`, and `.matches()` which "groups captures into
matches."

**Decision: target `tree_sitter>=0.25,<0.27`, QueryCursor form, no compatibility shim.** A shim that
tries `Query.captures` then falls back is three lines and tempting, but it means the wrapper's
behaviour depends on which runtime resolved — and `captures()` return shapes differ between the two
eras. Pin and assert instead: the wrapper raises a clear `ParserUnavailable` at import if
`tree_sitter.QueryCursor` is missing, naming the required pin.

`requirements.txt` additions:

```
# Parser substrate for the Java/Express(JS) extractors, and the upgrade path
# for TS/Go (see src/parse/tree_sitter_support.py). All of these ship
# prebuilt abi3 wheels -- no C toolchain, no Node, no JVM, no Go sidecar.
#
# The runtime is pinned to the >=0.25 query API: QueryCursor replaced
# Query.captures() in 0.25 and the old method is GONE, not deprecated.
tree-sitter>=0.25,<0.27
tree-sitter-java==0.23.5
tree-sitter-javascript==0.25.0
tree-sitter-typescript==0.23.2    # exports TWO grammars: typescript and tsx
tree-sitter-go==0.25.0
```

Grammars are pinned exactly, not floated: node type names and field names are **not** stable across
grammar releases, so a floating grammar silently empties a query (returns zero captures) rather than
erroring. That is the same silent-empty failure mode as the Angular record, which is the one failure
class this project has decided it will not tolerate. A grammar bump is a reviewed change with an
`EXTRACTOR_VERSION` bump behind it.

### Wrapper interface

```python
# src/parse/tree_sitter_support.py
"""Shared tree-sitter substrate.

Three of the stacks this pipeline is growing into need a real parse tree:
Java (annotations, interface methods with no body, Lombok-invisible members),
JavaScript for Express (middleware classified by ARITY, async wrappers one
call deep, object-literal schemas), and later TypeScript and Go, where the
current brace-counting line ranges are measurably wrong.

This module is deliberately thin. It owns four things and nothing else:
grammar loading, query execution, the translation from tree-sitter's
0-indexed byte/point world into this project's 1-indexed line conventions
and CodeSnippet, and the rule that a syntax error in one file never fails a
run. Everything about what to EXTRACT lives in the per-stack extractors.

It never raises into the pipeline for a bad source file: tree-sitter is
error-tolerant by construction and a file with a syntax error still yields a
usable tree with ERROR nodes in it. It raises only when the substrate itself
is missing (grammar not installed, wrong runtime pin), and the caller's
documented response to that is to fall back to regex and report
fidelity="regex" -- never to report syntax fidelity it did not get.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from src.extract.common import CodeSnippet, trim_snippet


class ParserUnavailable(RuntimeError):
    """The substrate is missing or mispinned. Callers degrade to regex."""


# language key -> (pypi module name, loader attribute on that module)
# tree-sitter-typescript is the odd one: ONE package, TWO grammars, because
# ".tsx" and ".ts" are different dialects -- '<' is generic-open, less-than or
# JSX-open depending on tokenizer state, and no single grammar decides that.
GRAMMARS: dict[str, tuple[str, str]] = {
    "java":       ("tree_sitter_java", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx":        ("tree_sitter_typescript", "language_tsx"),
    "go":         ("tree_sitter_go", "language"),
}

EXTENSION_TO_LANGUAGE = {
    ".java": "java", ".js": "javascript", ".jsx": "tsx", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx", ".go": "go",
}


@lru_cache(maxsize=None)
def _runtime():
    try:
        import tree_sitter
    except ImportError as exc:
        raise ParserUnavailable(
            "tree_sitter is not installed; add 'tree-sitter>=0.25,<0.27' to requirements.txt"
        ) from exc
    if not hasattr(tree_sitter, "QueryCursor"):
        raise ParserUnavailable(
            f"tree_sitter is installed but has no QueryCursor; this wrapper targets the >=0.25 "
            f"query API (Query.captures() was removed in 0.25). Pin 'tree-sitter>=0.25,<0.27'."
        )
    return tree_sitter


@lru_cache(maxsize=None)
def load_language(key: str):
    """Grammar objects are immutable and expensive-ish; cached per process."""
    ts = _runtime()
    try:
        module_name, attr = GRAMMARS[key]
    except KeyError:
        raise ParserUnavailable(f"no tree-sitter grammar registered for {key!r}") from None
    import importlib
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ParserUnavailable(f"grammar package {module_name!r} is not installed") from exc
    return ts.Language(getattr(module, attr)())


@lru_cache(maxsize=None)
def _parser(key: str):
    return _runtime().Parser(load_language(key))


@lru_cache(maxsize=256)
def compile_query(key: str, pattern: str):
    """Queries are compiled once per (language, pattern). An invalid pattern
    is a programming error in an extractor, not a bad input file, so
    QueryError propagates -- a broken query must fail loudly in tests rather
    than return zero captures and look like an empty file."""
    return _runtime().Query(load_language(key), pattern)
```

### Mapping onto the project's existing conventions

This is where most of the bugs would otherwise live. tree-sitter is 0-indexed rows and byte offsets;
everything in `codeExplanation-v2` is 1-indexed inclusive lines (`CodeSnippet`, `trim_snippet`,
`lineRange`, `visual_cues`, `highlightConfig`). Measured from my probe: a class declaration spanning
source lines 3-8 reports `start_point = Point(row=2, column=0)`, `end_point = Point(row=7, column=1)`.

```python
@dataclass
class ParsedFile:
    """One parsed source file, carrying everything the extractors and the
    existing snippet machinery need."""
    language_key: str
    source: bytes
    lines: list[str]            # the SAME list read_lines() produces, so
                                # trim_snippet / lineRange semantics are shared
    tree: object                # tree_sitter.Tree
    had_syntax_errors: bool
    error_lines: tuple[int, ...]  # 1-indexed lines containing ERROR/MISSING

    @property
    def root(self):
        return self.tree.root_node


def parse_source(text: str, language_key: str) -> ParsedFile:
    """Never raises for bad source. Encode once, to bytes, because
    tree-sitter's offsets are BYTE offsets -- slicing the str by them is
    wrong the moment a file contains a non-ASCII character (a comment in
    Hindi, an em dash, an emoji in a test fixture), and that bug produces
    an off-by-n snippet rather than an exception."""
    source = text.encode("utf-8")
    tree = _parser(language_key).parse(source)
    errors = tuple(error_report(tree.root_node))
    return ParsedFile(
        language_key=language_key,
        source=source,
        lines=text.splitlines(),
        tree=tree,
        had_syntax_errors=bool(tree.root_node.has_error),
        error_lines=errors,
    )


def line_range(node) -> tuple[int, int]:
    """tree-sitter Point.row is 0-indexed; this project's lineRange is
    1-indexed inclusive. This one function is the ONLY place that +1 is
    allowed to appear -- every off-by-one in the old brace-matching code
    came from the conversion being inlined at each use site.

    end_point.column == 0 means the node ends at the very start of a line
    (common for a block that closes on the previous line plus a newline);
    treating that row as the last line would over-report by one.
    """
    start = node.start_point.row + 1
    end_row = node.end_point.row
    if node.end_point.column == 0 and end_row > node.start_point.row:
        end_row -= 1
    return start, end_row + 1


def node_text(parsed: ParsedFile, node) -> str:
    return parsed.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def snippet_for(parsed: ParsedFile, node, *, prefix_nodes=()) -> CodeSnippet:
    """Build a CodeSnippet for a node, through the existing trim_snippet so
    the 120-line cap, the continuation note and -- critically -- the
    redact_secrets() choke point all still apply. Nothing may construct a
    CodeSnippet any other way.

    prefix_nodes exists for the decorator/annotation problem, which bites
    all three new stacks identically: a Java method_declaration's range
    starts at `public`, AFTER its @GetMapping; a Python FunctionDef's
    lineno points at `def`, after its @app.get(...). Clipping from the
    declaration loses the one line that says what the thing IS. The caller
    passes the modifiers/decorator nodes and the snippet starts at the
    earliest of them.
    """
    start, end = line_range(node)
    for extra in prefix_nodes:
        if extra is not None:
            start = min(start, line_range(extra)[0])
    return trim_snippet(parsed.lines, start, end)


def captures(parsed: ParsedFile, pattern: str, node=None) -> dict[str, list]:
    """Run one query and return {capture_name: [nodes]}.

    QueryCursor is per-execution state in the >=0.25 API, so a fresh one is
    created per call while the compiled Query is cached. Returning a plain
    dict of lists keeps extractors free of any tree-sitter type beyond Node.
    """
    query = compile_query(parsed.language_key, pattern)
    cursor = _runtime().QueryCursor(query)
    return dict(cursor.captures(node if node is not None else parsed.root))


def matches(parsed: ParsedFile, pattern: str, node=None) -> list:
    """Grouped form. Use this, NOT captures(), whenever two captures must be
    kept together -- an annotation name with ITS argument list, a route
    method with ITS path. captures() flattens across the whole subtree, so
    @GetMapping from one method and ("/x") from another collapse into
    parallel lists that line up by accident and mis-pair under any
    irregularity. This is the single most likely source of a silent wrong
    attribution in a query-based extractor, which the validation report
    ranks as the worst failure class for a narration product."""
    query = compile_query(parsed.language_key, pattern)
    return _runtime().QueryCursor(query).matches(node if node is not None else parsed.root)
```

### Error tolerance

The contract, in three rules:

1. **A syntax error never fails a file, and a failed file never fails a run.** tree-sitter recovers
   and still returns a tree. Verified: `parser.parse(b"class X { void f( { }")` returns
   `root.type == "program"`, `root.has_error == True`, with one `ERROR` node at
   `Point(row=0, column=10)`–`Point(row=0, column=19)`; the surrounding structure is still walkable.

```python
def error_report(node, _acc=None) -> list[int]:
    """1-indexed lines holding an ERROR or MISSING node. Walks the tree once
    at parse time; `has_error` is a cheap subtree flag, so clean subtrees are
    skipped wholesale rather than fully traversed."""
    acc = [] if _acc is None else _acc
    if not node.has_error and not node.is_missing:
        return acc
    if node.type == "ERROR" or node.is_missing:
        acc.append(node.start_point.row + 1)
    for child in node.children:
        error_report(child, acc)
    return acc


def is_sound(node) -> bool:
    """True when this subtree parsed cleanly. An extractor must call this
    before it reports a fact ABOUT a node: a method_declaration whose body
    contains an ERROR still has a trustworthy name and parameter list, but
    its end line and its call graph are not trustworthy, so facts derived
    from the body must be dropped."""
    return not node.has_error
```

2. **Per-node triage, not per-file.** A file with one bad method keeps the other twelve. The bad
   one is dropped from `importantFunctions` and its line recorded.
3. **Parse damage is disclosed, through the mechanisms that already exist.** When
   `parsed.had_syntax_errors`, the extractor appends to `notes` ("N line(s) of this file could not be
   parsed: lines 48, 102. Facts from those regions are omitted rather than guessed.") and adds a
   `notAnalyzed` entry naming the dropped aspect if an entire aspect was lost. The record stays
   `fidelity: "syntax"` — the parse was real, it just had holes, and holes are what `notes` and
   `notAnalyzed` are for. A file whose root is almost entirely ERROR (heuristic: >25% of lines in
   `error_lines`) is a different animal: the extractor should treat it as unparseable, return no
   facts, and let the render gate block it rather than narrate a tenth of a file.

### Migration note

- **No schema change from the wrapper itself.** It changes the *values* of `lineRange` and the
  *contents* of `importantFunctions` (correct ranges, previously-invisible generics/interface
  methods), which is exactly the case `mirror_store`'s version comment describes: "better line
  ranges, fixed detection."
- **`EXTRACTOR_VERSION: 6 → 7`** when the first tree-sitter-backed extractor lands, history entry:
  `7 - Java and JavaScript extraction run on tree-sitter parse trees; line ranges are byte-accurate
  node spans rather than brace-counted guesses, and records report fidelity "syntax".` One further
  bump when `ts_extractor`/`go_extractor` move over, because that materially changes records for
  files that previously extracted *successfully* — the highest-risk cache transition in the project,
  since those are the records a user has actually seen a video from.
- `requirements.txt` grows five pinned lines. `run-local.sh` already does
  `pip install --quiet -r requirements.txt` inside `.venv` on every run, so no script change is
  needed — but the first run after this PR downloads ~5 wheels, and the preflight block that checks
  `espeak-ng`/`ffmpeg` is the natural place to note it if a sandbox blocks PyPI. The grammars are
  pure wheels with no system dependency, unlike espeak-ng.

### Gaps

- **I did not verify node type names** for the Java/JS constructs the extractors will query
  (`method_declaration`, `annotation`, `formal_parameters`, `arrow_function`, `call_expression`
  field names). My probe confirmed `method_declaration`, `modifiers`, `annotation`,
  `annotation_argument_list`, `identifier` and the `name:` field for Java 0.23.5 specifically, by
  running a query against them. Everything else is unverified and must be confirmed against the
  pinned grammar with `node-types.json` or a scratch probe before a query is written — this is the
  silent-empty-capture risk, so it belongs in each stack's own research, not here.
- **No benchmark** comparing tree-sitter extraction accuracy against regex or against a compiler API
  for these languages was found; the case for the substrate rests on the structural argument
  (balanced delimiters are not regular) and on the measured failures in the validation report, not
  on published error rates.
- `tree-sitter-java` 0.23.5 last shipped 2024-12-21 and `tree-sitter-typescript` 0.23.2 on
  2024-11-11, both roughly two years stale relative to the javascript/go/python grammars at 0.25.0.
  I found no statement about whether the Java grammar covers records, sealed types or recent
  pattern-matching syntax; a Java 21+ repo should be probed before the Spring extractor relies on it.

---

## 4. Making validation enforcing

### Takeaway

The fix is not "fail the run when validation fails" — that would kill the honest partial output the
project is built around. It is a second, narrower gate that asks a different question. Validation
asks *is this record well-formed*; the render gate asks *is there anything true to say about this
file*. A chunk with four hedged routes and low confidence passes the gate and renders with hedging.
A chunk with nothing in any content list renders nothing, because 28 seconds of "this section covers
app, built with @angular/core" followed by "this part of the code has no further steps to narrate" is
the output the validation report calls the worst artifact in the repo.

### The distinguishing rule

Three outcomes per chunk, decided by one function, in this precedence order:

```python
# src/validate/render_gate.py
"""Phase 7 -- decides whether a chunk is narrated and rendered at all.

Schema validation (src/validate/schema_check.py) answers "is this record
well-formed". It is report-only on purpose: a record can be missing a field
and still be worth narrating. This module answers the different question the
pipeline actually needs before it spends a render on a chunk: "is there
anything TRUE to say about this file?"

The project's stance is honest partial output, so blanket failure is wrong.
Nearly everything degrades: low confidence, every claim assumed, regex
fidelity, unanalyzed aspects, trimmed snippets, parse holes. All of those
render, hedged, with the gap disclosed -- that is 'incomplete but honest'.

Exactly three things BLOCK, and each of them is a case where the only
sentences the narrator could produce are either untrue or vacuous:

  1. No content at all. Every one of importantFunctions, routes,
     eventHandlers, apiCalls, dataModels, sideEffects, inputs is empty.
     There is no fact to narrate, so the four beats collapse into a
     framework name and a filler sentence -- the Angular failure exactly.
  2. No substrate. fidelity == "none": the placeholder branch in
     reuse_pipeline for a stack with no extractor. It read nothing; it
     cannot be partially honest.
  3. Broken identity, or a self-contradicting claim. Missing chunkId /
     filePath / language / lineRange means the render bundle and the
     highlight cues cannot be built against real lines. A route with
     pathResolved is False and assumed is False means an extractor is about
     to assert a URL it could not construct -- the one error class a viewer
     cannot detect, so it blocks rather than warns.

A blocked chunk is not silence. It is counted, named with its reason in
pilot_report.json and on stderr, and surfaced once at the run level ("3 files
in this repository are not analyzed by this version of the pipeline") rather
than as three content-free video sections.
"""

from __future__ import annotations

CONTENT_FIELDS = ("importantFunctions", "routes", "eventHandlers", "apiCalls",
                  "dataModels", "sideEffects", "inputs")
IDENTITY_FIELDS = ("chunkId", "filePath", "language", "lineRange")

OK, DEGRADED, BLOCKED = "ok", "degraded", "blocked"


def gate(record: dict) -> dict:
    """Returns {"status": ok|degraded|blocked, "reasons": [...], "warnings": [...]}."""
    reasons: list[str] = []
    warnings: list[str] = []

    missing = [f for f in IDENTITY_FIELDS if not record.get(f)]
    if missing:
        reasons.append(f"missing identity field(s) {', '.join(missing)}; the render bundle and "
                       f"highlight cues cannot be built against real source lines")

    if (record.get("fidelity") or "regex") == "none":
        reasons.append("no extractor ran for this stack, so nothing in this record was read "
                       "from the source")

    if not any(record.get(f) for f in CONTENT_FIELDS):
        reasons.append("every content list is empty, so the narration would be a framework name "
                       "and a filler sentence with no fact in it")

    for route in record.get("routes") or []:
        if route.get("pathResolved") is False and not route.get("assumed"):
            reasons.append(f"route {route.get('path')!r} has an unresolved prefix but is not "
                           f"marked assumed, so the narration would assert a URL that was "
                           f"never constructed")

    if reasons:
        return {"status": BLOCKED, "reasons": reasons, "warnings": warnings}

    # Everything below is incomplete-but-honest: it renders.
    if (record.get("confidenceLevel") or "") in {"low", "medium"}:
        warnings.append(f"extraction confidence is {record['confidenceLevel']}")
    if (record.get("fidelity") or "regex") == "regex":
        warnings.append("facts came from pattern matching, not a parse tree; line ranges and "
                        "resolved paths are approximate and the narration hedges accordingly")
    for entry in record.get("notAnalyzed") or []:
        warnings.append(f"{entry.get('aspect')} not analyzed: {entry.get('reason')}")
    assumed = sum(1 for r in (record.get("routes") or []) if r.get("assumed")) \
            + sum(1 for h in (record.get("eventHandlers") or []) if h.get("assumed")) \
            + sum(1 for c in (record.get("apiCalls") or []) if c.get("assumed"))
    if assumed:
        warnings.append(f"{assumed} claim(s) marked assumed and hedged in the narration")

    return {"status": DEGRADED if warnings else OK, "reasons": [], "warnings": warnings}
```

Note what is **not** a blocker, deliberately:

- `fidelity: "regex"` — warns. Two stacks ship on it today and produce real content.
- Every claim assumed — warns. A hedged fact is the product working as designed.
- `notAnalyzed` non-empty — warns, **as long as some other aspect has content**. A Spring controller
  whose routes aren't analyzed but whose methods and data models are is worth narrating with the
  disclosure sentence. One whose everything is empty is blocked by rule 1, which is the correct
  interaction between §1's refusal rule and this one.
- Schema-invalid on a *non-identity* field (`frameworkOrLibrary` missing, `pullRequest` key absent)
  — warns. This is the existing report-only behaviour, preserved, and it is the reason the gate is a
  separate module rather than a flag on `validate_record`.
- Trimmed snippets, redacted secrets, parse holes — warn. All already carry notes.

### Change to `run_pilot.py`

```python
from src.validate.render_gate import gate, BLOCKED

    schema_result = validate_records(records)

    gates = {r.get("chunkId"): gate(r) for r in records}
    renderable = [r for r in records if gates[r.get("chunkId")]["status"] != BLOCKED]
    blocked = [r for r in records if gates[r.get("chunkId")]["status"] == BLOCKED]

    # Narration and render run over the renderable set only. Note this is
    # also a correctness fix for the reported numbers: narration.chunkCount
    # and withinTargetBand currently average in content-free chunks whose
    # ~28s scripts drag the distribution down.
    narration = generate_narration_for_repo(renderable)
```

and a new report section, beside `schemaValidation` rather than inside it:

```python
        "renderGate": {
            "total": len(records),
            "rendered": len(renderable),
            "blocked": len(blocked),
            "degraded": sum(1 for g in gates.values() if g["status"] == "degraded"),
            "blockedChunks": [
                {"chunkId": r["chunkId"], "filePath": r.get("filePath"),
                 "reasons": gates[r["chunkId"]]["reasons"]}
                for r in blocked
            ],
            "warnings": {cid: g["warnings"] for cid, g in gates.items() if g["warnings"]},
        },
```

`run_pilot` returns the report as it does now and additionally gets an **exit-status helper** so the
shell layer does not have to re-derive the verdict:

```python
def exit_code_for(report: dict, strict: bool = False) -> int:
    g = report["renderGate"]
    if g["rendered"] == 0:
        return 2          # nothing honest to render; no video should be produced
    if g["blocked"] and strict:
        return 3          # partial output, and the operator asked to be told loudly
    return 0              # partial output is the normal, accepted case
```

`main()` prints the blocked list to **stderr** (so it survives the `[:2000]` truncation that the
current `main()` applies to the JSON dump on stdout) and calls `sys.exit(exit_code_for(...))`.

### What the operator sees

On stderr, once per run, before the exit:

```
Render gate: 11 of 14 chunks will be rendered (6 degraded), 3 blocked.

Blocked — these files produce no video section:
  src/main/java/com/acme/OrderController.java
      every content list is empty, so the narration would be a framework name and a filler
      sentence with no fact in it
  src/routes/birds.js
      no extractor ran for this stack, so nothing in this record was read from the source
  src/components/UserCard.ts
      every content list is empty, so the narration would be a framework name and a filler
      sentence with no fact in it

Degraded — rendered, with the gap disclosed in the narration:
  src/handler/alumni.go        4 claim(s) marked assumed and hedged in the narration;
                               facts came from pattern matching, not a parse tree
  ...
Full detail: output/pilot_report.json -> renderGate
```

Three properties of that block worth defending: it names **file paths**, not chunk ids, because the
operator's next action is to open a file; it says **what the consequence is** ("produce no video
section"), not just a status word; and the degraded list is the project's honesty stance made
operational — those chunks shipped, and the operator can see exactly what the viewer will be told
was uncertain.

### How `run-local.sh` should exit

`run-local.sh` is `set -euo pipefail`, so `python scripts/run_backend_pilot.py $RENDER_FLAG` already
aborts the whole script on a non-zero exit — which is wrong for code 3 and right for code 2. So:

1. **`scripts/run_backend_pilot.py` propagates `exit_code_for`.** (I did not read that script; it
   is the wrapper `run-local.sh` actually calls, so the exit-code plumbing lands there and
   `run_pilot.main()` keeps its own.)
2. **Add a `--strict` flag** to `run-local.sh` that sets `STRICT=1` and passes `--strict` through.
   Without it, partial output is normal and the run continues to the render step.
3. **Handle the codes explicitly** rather than letting `set -e` decide:

```bash
# in run_backend() -- replace the bare invocation
set +e
python scripts/run_backend_pilot.py $RENDER_FLAG ${STRICT:+--strict}
PILOT_STATUS=$?
set -e
case "$PILOT_STATUS" in
  0) ;;
  2) echo "" >&2
     echo "No chunk in this repository produced narratable content, so there is nothing to" >&2
     echo "render. This is the pipeline refusing to make a video that says nothing true," >&2
     echo "not a crash. See output/pilot_report.json -> renderGate for the per-file reason;" >&2
     echo "the usual cause is a stack this version has no extractor for." >&2
     deactivate; exit 2 ;;
  3) echo "" >&2
     echo "Some chunks were blocked and --strict was requested; stopping before the render." >&2
     echo "Re-run without --strict to render the chunks that did produce content." >&2
     deactivate; exit 3 ;;
  *) deactivate; exit "$PILOT_STATUS" ;;
esac
```

4. **Step 4 must not contradict step 1.** `run_video_render` already exits 1 when
   `render-app/public/chunks/manifest.json` is absent — but its message says "run the backend step
   first without --no-render", which would now be a misdiagnosis: the staging directory is empty
   because every chunk was blocked. That message gets a branch that reads `renderGate.rendered` from
   `output/pilot_report.json` (or just mentions the possibility) so the operator is not sent to fix
   a flag that is not the problem.

Exit-code contract, to be documented in the `run-local.sh` header comment block:

| code | meaning | video produced |
|---|---|---|
| 0 | every chunk rendered, or some blocked and partial output accepted | yes |
| 1 | an actual failure (missing espeak-ng/ffmpeg, Remotion crash, npm) | no |
| 2 | nothing renderable: the pipeline refused rather than produce an empty video | no |
| 3 | partial output, blocked chunks present, `--strict` requested | no |

### Migration note

- **No schema change, so no `EXTRACTOR_VERSION` bump.** `render_gate.gate()` is a pure function of a
  record; stored records are untouched and reuse is unaffected. This is the cheapest of the four
  changes and can land first — it does not depend on §1, because `gate()` reads `fidelity` and
  `notAnalyzed` through `.get` with the same defaults §1 specifies, so on pre-version-5 records it
  degrades to the content-emptiness and identity rules alone, which are the two that matter most.
- Land it **before** the three new extractors, not after. Its whole value is that an unsupported
  stack stops producing an mp4, and the window in which that matters is exactly while the three
  extractors are being written.

### Gaps

- `scripts/run_backend_pilot.py` and `src/narrate/pipeline.py` were not read (outside the files I was
  pointed at). The exit-code plumbing and `generate_narration_for_repo`'s exact signature should be
  confirmed against them; I have assumed it takes a list of records, which is how `run_pilot` calls
  it.
- Whether `build_render_bundle`'s staging writes a `manifest.json` entry per chunk or one manifest
  for the set determines whether a blocked chunk needs explicit removal from a previous run's
  staging directory. A stale `render-app/public/chunks/<chunkId>/` from an earlier run would
  otherwise resurrect a blocked chunk into the video — a real risk given the mirror store's whole
  purpose is persistence across runs. Worth checking before this lands.
- The >25% error-lines threshold for "unparseable" in §3 and the choice to block on
  content-emptiness rather than on, say, a minimum spoken duration are both judgement calls with no
  source behind them. The duration alternative is attractive — `NarrationScript.estimated_seconds`
  against `TARGET_MIN_SECONDS = 90` is already computed — but it would block legitimately short
  honest chunks, so content-emptiness is the safer rule.

---

## Test plan (tests/ style: plain pytest functions, no classes, small inline fixtures)

Matching the existing files' conventions — a `_valid_record(**overrides)` helper per module, inline
triple-quoted source strings, `tmp_path` for anything touching disk.

**`tests/test_fidelity.py`**
- `test_fidelity_is_required_and_enum_checked` — `validate_record` reports a missing `fidelity`, and
  reports `"fidelity 'ast' is not one of ..."`.
- `test_hedge_level_assumed_outranks_regex` — `hedge_level({"fidelity": "regex"}, True) == ASSUMED`;
  the produced sentence starts `"It looks like"` and contains `"Going by"` nowhere.
- `test_regex_fidelity_hedges_an_unassumed_route` — exact string equality against
  `"Going by the text of the file, a GET request to /users is handled here."`
- `test_syntax_fidelity_asserts_plainly` — same record with `fidelity: "syntax"`, exact equality
  against the unhedged sentence.
- `test_regex_fidelity_omits_the_end_line` — `build_function_narration({"name": "f", "lineRange":
  [12, 40], "fidelity": "regex"})` contains `"starting at line 12"` and not `"to 40"`.
- `test_regex_fidelity_omits_the_export_claim_for_python` — `"It is exported"` absent.
- `test_not_analyzed_produces_one_disclosure_sentence_in_the_recap` — a record with a `routes`
  `notAnalyzed` entry; the recap beat contains `"not analyzed by this version"` and the flow beats
  do not.
- `test_not_analyzed_suppresses_the_stands_on_its_own_sentence` — absence is never asserted.
- `test_old_records_default_to_regex_fidelity` — a dict with no `fidelity` key narrates identically
  to one with `"regex"` (the backward-compatibility contract, as an equality assertion).

**`tests/test_route_prefix.py`**
- `test_single_level_prefix_resolves`
- `test_nested_chain_composes_in_source_order` — `/api` → `/v1` → `/users` == `/api/v1/users`
  (the Fiber case the report measured wrong).
- `test_parent_to_child_mount_normalises_to_the_same_edge` — `add_mount` and `add_child_edge` give
  identical `Resolution`s for the same topology (the Express/Flask vs Fiber direction equivalence).
- `test_unknown_parent_is_unresolved_with_a_partial_path` — path is the resolvable tail,
  `resolved is False`, `unresolved_reason == "unknown_parent"`, note mentions the symbol name.
- `test_non_literal_prefix_names_the_expression` — `PrefixEdge(segment=None,
  expression="basePath")`; note contains `basePath`; `unresolved_reason == "non_literal"`.
- `test_cycle_does_not_hang_and_is_reported` — A→B→A; returns, `unresolved_reason == "cycle"`.
- `test_depth_guard` — a 40-deep chain stops at `MAX_DEPTH` with `reason == "depth"`.
- `test_double_mount_is_reported_as_ambiguous_not_last_wins`
- `test_join_normalises_slashes` — `/api/` + `/` → `/api`; empty prefix + `users` → `/users`;
  no `//` ever appears.
- `test_unresolved_path_always_sets_assumed` — the hard rule, asserted over a table of cases.
- `tests/test_go_extractor.py` additions (parity, in the existing file): the current nested-group
  assertions must pass unchanged after the refactor, plus
  `test_group_with_a_variable_prefix_is_unresolved_and_names_the_variable` and
  `test_app_passed_as_a_parameter_is_not_treated_as_a_resolved_root` — the latter is a **new
  failing-first test** that documents the `roots.add("app")` guess, which is the one behavioural
  change the refactor should make.

**`tests/test_tree_sitter_support.py`** — needs `pytest.importorskip`, in the style of
`test_run_pilot.py`'s `requires_espeak = pytest.mark.skipif(shutil.which("espeak-ng") is None, ...)`:
```python
pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_java")
```
- `test_runtime_api_is_the_querycursor_era` — `hasattr(tree_sitter, "QueryCursor")`; this is the pin
  assertion and it fails loudly if someone downgrades to 0.24.
- `test_every_registered_grammar_loads` — parametrised over `GRAMMARS` keys.
- `test_line_range_is_one_indexed_inclusive` — a known 6-line class in a known position; asserts
  `(3, 8)` against the raw `Point(row=2)`/`Point(row=7)`.
- `test_line_range_does_not_over_report_when_the_node_ends_at_column_zero`
- `test_snippet_includes_the_annotation_above_the_declaration` — `prefix_nodes`; the snippet's first
  line is `@GetMapping("/{id}")`.
- `test_snippet_goes_through_redact_secrets` — a hardcoded `api_key = "sk-..."` in the parsed source
  comes back redacted with `secrets_redacted is True`, mirroring
  `tests/test_secret_redaction_integration.py`. This is the one that matters most: `trim_snippet` is
  the only secret choke point and a new snippet path could bypass it.
- `test_snippet_respects_the_120_line_cap_and_continuation_note`
- `test_non_ascii_source_slices_correctly` — a file with a non-ASCII comment above the target node;
  the snippet text is right, proving the byte-vs-str discipline.
- `test_syntax_error_does_not_raise_and_is_reported` — `had_syntax_errors is True`,
  `error_lines == (1,)`, and a sibling clean declaration is still extractable.
- `test_is_sound_is_false_only_for_the_damaged_subtree`
- `test_missing_grammar_raises_parser_unavailable_not_importerror`
- `test_matches_keeps_an_annotation_with_its_own_arguments` — two annotated methods in one class;
  asserts the pairing is per-match, i.e. the wrong-attribution guard.

**`tests/test_render_gate.py`**
- `test_record_with_content_is_ok`
- `test_empty_every_list_is_blocked` — built from the Angular shape described in the validation
  report: schema-valid, every content list empty.
- `test_placeholder_record_is_blocked` — `fidelity: "none"`.
- `test_low_confidence_with_content_is_degraded_not_blocked` — the honest-partial-output guarantee,
  as an explicit test.
- `test_all_claims_assumed_with_content_is_degraded_not_blocked`
- `test_not_analyzed_with_other_content_is_degraded`
- `test_not_analyzed_with_no_other_content_is_blocked`
- `test_unresolved_path_not_marked_assumed_is_blocked`
- `test_missing_identity_field_is_blocked`
- `test_missing_non_identity_field_is_not_blocked` — e.g. no `pullRequest` key; preserves today's
  report-only behaviour for the documented gap.
- `test_pre_version_5_record_gates_on_content_alone` — no `fidelity`/`notAnalyzed` keys; still
  gated correctly. Backward compatibility, asserted.

**`tests/test_run_pilot.py`** additions (existing file, existing `_build_repo` style)
- `test_blocked_chunk_is_not_narrated_or_rendered` — a repo with one good React file and one
  `.java` file (which today hits the placeholder branch); `renderGate.blocked == 1`,
  `narration.chunkCount == 1`, and `len(report["render"]) == 1`.
- `test_repo_with_only_unsupported_stacks_renders_nothing` — Java only;
  `renderGate.rendered == 0`, `exit_code_for(report) == 2`.
- `test_partial_run_exits_zero_and_three_under_strict` — same report, both codes.
- `test_blocked_chunks_are_named_with_reasons_in_the_report` — `blockedChunks[0]["filePath"]` and a
  non-empty `reasons` list, so the operator-facing contract is locked and not just the counts.

---

## Build order, and the three per-stack contracts

Order, because each step removes work from the next:

1. **§4 render gate** — no schema change, no version bump, lands standalone, and it is the thing
   that stops an unsupported stack shipping an mp4 while the extractors are in flight.
2. **§1 `fidelity` + `notAnalyzed`** — `EXTRACTOR_VERSION 5`. Both existing extractors declare
   `"regex"`; the two new narration rungs land with them.
3. **§2 route-prefix resolver** — `EXTRACTOR_VERSION 6`, including the `go_extractor` refactor with
   the parity test. Lands before any new extractor so Spring/Express/FastAPI route work is a
   graph-building exercise, not a dataflow exercise.
4. **§3 tree-sitter wrapper** — pins in `requirements.txt`, no version bump of its own; the bump to
   7 rides with the first extractor that uses it.

What each sibling researcher's extractor owes this layer, stated so it is built once:

| Contract | Python | Java/Spring | Express/JS |
|---|---|---|---|
| `FIDELITY` constant | `"syntax"` (stdlib `ast`, no new dependency) | `"syntax"` (tree-sitter-java 0.23.5) | `"syntax"` (tree-sitter-javascript 0.25.0) |
| Snippets | **must** go through `snippet_for`/`trim_snippet`, never hand-built — it is the only `redact_secrets` choke point | same | same |
| Decorator/annotation prefix | pass `node.decorator_list` as `prefix_nodes` (`FunctionDef.lineno` points at `def`) | pass the `modifiers` node (range starts at `public`, after `@GetMapping`) | pass the wrapping `call_expression` for `asyncHandler(async (req,res) => ...)` |
| Prefix graph | FastAPI `APIRouter(prefix=)` + `include_router(prefix=)`; Flask `url_prefix` + `register_blueprint` | class `@RequestMapping` as a root-with-prefix, one edge per method | `app.use(path, router)` with **file-qualified** `SymbolId`s |
| `notAnalyzed` | Django `include()` targets outside the chunk; `migrations/` skipped | the DI graph (needs `typed`); Spring Data proxy implementations that have no source file | the ordered middleware chain if it is not extracted; `server.servlet` style config prefixes |
| Never do | report `routes: []` for a framework that has routes | match `@Controller` as a literal string (the stereotypes are meta-annotated); read `/* */` license headers as the class description | classify middleware by name instead of arity (an error handler is the 4-argument one) |
