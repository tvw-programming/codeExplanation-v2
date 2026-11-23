# Phase 3 — Extraction Into the JSON Structure

Status: multi-stack extractors shipped (`EXTRACTOR_VERSION = 9`).
Regex ceilings and remaining gaps:
[`14-stack-support-validation.md`](./14-stack-support-validation.md)
(banner) and [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).
Live suite count: documentation index / doc 10.

Historical Alumni-web snapshot (not a live dashboard):
`AlumniAdminGrid.tsx` → 17 handlers + 2 functions, confidence 0.5/low;
`alumni_repository.go` → 4 structs, 11 functions, 7 real pgx calls,
confidence 0.95/high.

**Stack honesty:** each stack has a dedicated builder (or shared
React-style mount path for Vue). Empty / low-fidelity extractions set
`visualAvailability: unavailable` and `visualGraph: null` — graphs are
never invented. Nested Fiber group prefixes **are** composed in-file.
Go generics, interfaces, and closure middleware are still missed.
Angular uses `angular_extractor.py` (not the React builder); no
`@Component` → unavailable visuals. Python uses stdlib `ast`. Spring DI
is by type. Express is a real backend stack.

## What this phase delivers

`src/extract/extractor.py: extract_repo(root, project_type)` (and
`reuse_pipeline.py` in the live path) dispatches each chunk to a
stack-specific builder (`json_builder.py` for React/Go;
`stack_records.py` for Angular/Vue/Solid/Qwik/JS/Python/Express/Spring/Rust),
then `attach_visuals()`, then resolves `featureMapping`
(`feature_mapping.py`).

## Locked rules this phase implements

- Every field in the locked schema (see
  [`11-json-schema-reference.md`](./11-json-schema-reference.md)) is
  populated where determinable.
- Any uncertain claim is marked `"assumed": true` with a note — never
  presented as fact.
- `featureMapping` resolves frontend API calls to backend routes by
  URL, accounting for a baseURL prefix and templated path parameters.

## Key functions and why they were chosen

### The scope decision: regex/heuristics, not a real AST parser

`common.py`'s module docstring states this directly: *"Extraction here
is regex/heuristic-based static analysis, not a real AST parser
(ts-morph, go/ast). That is a deliberate scope decision for this phase,
not an oversight."*

**Why heuristic extraction instead of ts-morph (TypeScript) or `go/ast`
(Go) from the start:**

- A heuristic extractor can produce every field the locked schema
  requires *today*, with every uncertain claim explicitly marked
  `assumed` — meeting the accuracy rule without needing a parser
  dependency, a build step, or a language-server-style project load
  for each target repo (which varies in its own build setup, tooling
  version, and dependency graph — brittle things to assume about an
  arbitrary "any repo as input").
- A real parser is explicitly framed as "the natural upgrade path" that
  "would mostly just raise confidence, not change the schema" — i.e.
  swapping the extraction engine later doesn't require redesigning
  anything downstream (Phase 4 storage, Phase 5 narration, Phase 6
  rendering all consume the same JSON shape regardless of how it was
  produced).
- The real bug this scope decision did surface — a route-protection
  heuristic false-positiving on the word "auth" inside a comment
  explaining auth was *disabled* — was found and fixed by testing
  against the real repo (tightened to only check `.Use()` calls on the
  matching route-group variable), which is itself evidence the
  heuristic approach, paired with real-repo verification, catches its
  own mistakes rather than hiding them behind parser-level confidence
  it hasn't earned.

### `trim_snippet(lines, start_line, end_line, max_lines=120)`

**What it does:** the single choke point every function/struct/interface
code snippet passes through before reaching a chunk record. Trims to
120 lines with a continuation note (never a silent cut-off), and — as of
the latest security fix — redacts secret-shaped substrings via
`guardrails.redact_secrets()`.

**Why a continuation note instead of a hard, silent 120-line cutoff:**
the locked rule is explicit that a function longer than the limit is
"NOT cut off silently... it continues in a follow-on snapshot." A
silent cutoff would show a reviewer (or a narrated video!) an
incomplete function body with no indication anything was missing — a
correctness problem, not just a cosmetic one. The continuation note
states exactly how many lines follow and where, so a later stage (or a
human) can fetch the rest deliberately.

**Why secret redaction is wired in at this one function instead of at
every individual extractor call site** (`ts_extractor.py`'s function/
interface extraction, `go_extractor.py`'s struct/function extraction,
etc.): every one of those call sites already funnels through
`trim_snippet()` to build its `CodeSnippet`. Putting the guard here
once means no future extractor — current or not-yet-written — can
forget to call it; the alternative (reminding every call site to scan)
is exactly the pattern that let a secret leak through undetected for
seven phases (see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)
for that full incident writeup).

### `confidence_from_flags(total_claims, assumed_claims, base=0.95)`

**What it does:** `confidence = base - 0.5 * (assumed_claims / total_claims)`,
floored at 0.05.

**Why a simple linear penalty instead of, say, a weighted score per
field type:** the module's own docstring is candid that this is "a
simple, documented confidence formula... not a validated scoring model —
a starting point, same as the project's own 0.85 threshold." A more
elaborate weighting scheme would create a false sense of precision
without any actual evidence backing the specific weights. A transparent,
easily-explained linear formula is more honest about what it is: a
rough signal, not a calibrated probability.

### `json_builder.py: _resolve_frontend_framework_or_library(imports, known_deps)`

**What it does:** matches each non-internal import against the repo's
**actual** `package.json` dependencies — including handling scoped
packages (`@mui/icons-material/Add` → `@mui/icons-material`) — rather
than guessing from the import string alone.

**Why cross-reference the real `package.json` instead of maintaining a
hardcoded list of "known framework import paths":** a hardcoded list
would need updating for every library this pipeline might ever
encounter across arbitrary input repos — a losing battle, and exactly
the kind of hardcoding the dynamic-design principle rejects. Reading
the repo's own dependency manifest means `frameworkOrLibrary` is always
correct for *that* repo's actual dependency set, with zero maintenance
as new libraries appear in the wild.

### `src/extract/feature_mapping.py: normalize_path(path)` / `match_calls_to_routes(...)`

**What it does:** strips dynamic path segments (`${id}` on the
frontend, `:id` on Fiber) to a comparable template, then matches
frontend API calls to backend routes by `(method, normalized_path)`,
accounting for the frontend's axios `baseURL`.

**Why normalize to `{}` placeholders instead of, say, exact string
matching or a full path-template library:** a frontend call to
`` `/alumni/${id}` `` and a backend route registered as
`/api/v1/alumni/:id` are the *same* endpoint under two different
templating conventions (JS template literals vs. Fiber's `:param`
syntax) — exact string matching would never connect them, breaking the
entire point of `featureMapping`. A single shared regex that erases
both conventions' dynamic-segment syntax is the minimum necessary
normalization to make the comparison apples-to-apples, without pulling
in a full routing/path-template dependency for what is fundamentally a
two-pattern substitution.

**Why a URL that's a runtime variable (not a literal string) is kept as
the `urlPattern` and marked `assumed: true`, rather than either dropping
the call or guessing a concrete URL:** the locked `apiCalls` rule says
exactly this — "If the URL is a variable, the pattern holds the
variable and is marked assumed." Dropping the call would hide a real
API call from the narrated explanation; guessing a concrete value would
risk stating something false as fact. Keeping the variable expression
itself, flagged, is the only option that is both complete and honest.

### Extra fields the schema docs originally omitted

`json_builder.py` writes more than the locked required list:

| Field | Where | Notes |
|---|---|---|
| `fileDescription` | record | File header comment; FileCard purpose |
| `extractorVersion` | record | Currently `9` (`mirror_store.EXTRACTOR_VERSION`); reuse invalidates on mismatch even if bytes match |
| `secretsRedacted` | each snippet | Set by `trim_snippet()` |
| `eventHandlers[].lineRange` | `[line, line]` at the bind site | `visual_cues.py` includes `eventHandlers` in `CUE_SOURCE_FIELDS` — 08 used to say handlers have no range |
| Function-context keys on `importantFunctions` | `function_context.py` | `description`, `descriptionSource`, `exported`, `calledBy`, `calls`, `params`, `raisesError`, `isAsync`, `reactHooks`, `apiCalls`, `sideEffects`, `lineCount` |
| `outputs` | record | Always `[]` — known gap |

### Angular honesty gate

Angular uses `angular_extractor.py` (not the React TS builder). When no
`@Component` / inputs are recovered, `attach_visuals` sets
`visualAvailability: unavailable` and `visualGraph: null`. Empty content
lists remain schema-valid; visuals are skipped in `FullVideo`, not
invented. See [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).

### `ts_extractor.py`: `JSX_INLINE_HANDLER_RE` and always-`assumed` inline handlers

**What it does:** a JSX prop bound directly to an inline arrow function
(`onClick={() => ...}`) is always recorded with `assumed: true` — "the
handler itself is anonymous, so this is always marked assumed... there
is no named function to point at with full confidence."

**Why always mark these assumed rather than trying to name/describe the
inline function's body:** an inline arrow function has no identifier a
reviewer or narration script could refer to by name with any certainty
about what the pipeline *thinks* its purpose is versus what it actually
does — synthesizing a plausible-sounding name for it would be inventing
information not actually present in the extraction's symbol table,
which the locked accuracy rule specifically forbids.

## Verified against the real repo

Historical Alumni-web snapshot (not a live dashboard):
`AlumniAdminGrid.tsx` (the richest real frontend chunk found): 17
handlers + 2 functions, confidence 0.5 ("low" — reflecting how many of
those 17 handlers are inline/assumed). `alumni_repository.go`: 4
structs, 11 functions, 7 real `pgx` database calls recognized by
`SIDE_EFFECT_PATTERNS`, confidence 0.95 ("high" — almost nothing had to
be marked assumed, because Go's route/handler/struct syntax is far less
ambiguous to a regex extractor than JSX inline handlers are).
