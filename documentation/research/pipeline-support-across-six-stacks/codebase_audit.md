# Pipeline support across six stacks — codebase audit of /home/claude/codeExplanation-v2

Audit method: direct reading of source on disk (all paths below are absolute),
plus empirical runs of the real pipeline modules against synthetic minimal
repos for Python, Java/Spring Boot, Express, Angular and React (fixtures under
`/tmp/claude-0/-home-claude/3023d7e0-bf56-5a80-ba0f-fff2b871fada/scratchpad/fix/`,
probe scripts in the same scratchpad). The repo is not a git checkout
(`git` dir present but environment reports non-repo), so no history claims are made.

## Bottom line (support matrix)

| Stack | Detected | Chunked | Extracted | Schema-valid | Narration content | Verdict |
|---|---|---|---|---|---|---|
| React (.tsx/.jsx) | yes | yes | yes (regex) | yes | real functions/handlers/API calls | **fully supported** (within regex limits) |
| Go (+ Fiber) | yes | yes | yes (regex) | yes | real functions/routes/structs | **fully supported** (within regex limits) |
| Angular | yes | yes | runs TS extractor | yes, confidence 0.95 "high" | **empty** — 0 functions, 0 handlers, 0 API calls | **partially supported — dangerously silent** |
| Python | yes | yes | no — placeholder | **no** | generic, contentless | not supported (fails loudly at validation, then renders anyway) |
| Java / Spring Boot | yes | yes | no — placeholder | **no** | generic, contentless | not supported (same) |
| Express / Node (package.json without react or @angular/core) | partially (`react_or_angular`) | yes or **silently zero** | no — placeholder | **no** | generic or **nothing at all** | not supported; worst failure mode |

---

## Q1. What does src/detect/ actually detect?

### Takeaway
Detection is marker-file based and does recognise Angular, Python, Spring Boot
and plain Java explicitly; it has no concept of Express/Node as a backend — any
`package.json` is a *frontend* marker, and a non-React non-Angular `package.json`
yields the ambiguous value `"react_or_angular"` that no downstream extractor handles.

### Cited findings
- Marker table: `react_or_angular` ← `package.json`; `python` ← `requirements.txt`, `pyproject.toml`, `setup.py`; `go` ← `go.mod`; `spring_boot` ← `pom.xml`, `build.gradle`, `build.gradle.kts` — `/home/claude/codeExplanation-v2/src/detect/project_type.py:26-31`.
- Frontend flavour from `package.json` deps: `@angular/core` → `"angular"`, `react` → `"react"`, otherwise → `"react_or_angular"` — `src/detect/project_type.py:97-108`.
- Java flavour: `"spring_boot"` if the build file text contains `spring-boot` or `org.springframework.boot`, else `"java"` — `src/detect/project_type.py:111-122`.
- Docker markers (`Dockerfile`, `docker-compose.yml`, …) and an architecture heuristic (`>1` backend service root → `"microservice"`) — `src/detect/project_type.py:32`, `:195`.
- Stray `.py`/`.go`/`.java` files with no marker file are surfaced as `unclaimed_hint_files` and deliberately never promoted to a detected stack — `src/detect/project_type.py:34-40`, `:132-156`; tested at `tests/test_project_type.py:89-98`.
- Scan depth is capped at `max_depth=3` from the repo root (`_iter_dirs`, `src/detect/project_type.py:67-82`, default at `:159`), so a marker file deeper than 3 levels is invisible.
- Empirical: Express fixture (`package.json` with `express` only) detects as `{'frontend': 'react_or_angular', 'backend': []}` — no backend stack at all.
- Empirical: Python fixture → `backend: ['python']`; Spring fixture → `backend: ['spring_boot']`; Angular fixture → `frontend: 'angular'`.

### Inferences
- Node/Express is structurally unrepresentable in `ProjectType`: there is no `"express"`/`"node"` value anywhere in the module, so an Express repo is misclassified as an unresolved frontend.

### Gaps
- No detection for Vue, Svelte, Next.js, NestJS, .NET, Ruby, PHP (no markers for them in `MARKER_FILES`).

---

## Q2. What does src/chunk/ do per stack? Is grouping language-specific?

### Takeaway
Grouping is explicitly language-specific, with four separate strategies keyed off
the Phase-1 marker hits; extensions walked are `.tsx/.ts/.jsx/.js` (frontend), `.go`,
`.py`, `.java`. Two real defects: files are **silently dropped** in a common frontend
layout, and the Express `react_or_angular` stack label is propagated into chunks that
nothing can extract.

### Cited findings
- Extension sets: `FRONTEND_SOURCE_EXTENSIONS = {".tsx", ".ts", ".jsx", ".js"}`, `GO_SOURCE_EXTENSION = ".go"`, `PYTHON_SOURCE_EXTENSION = ".py"`, `JAVA_SOURCE_EXTENSION = ".java"` — `src/chunk/feature_grouping.py:28-31`.
- Dispatch is per marker hit, one grouping function per stack — `src/chunk/chunker.py:46-62`.
- Frontend stack label for chunks is `project_type.frontend_stack or "react"` — `src/chunk/chunker.py:49`; so an Express repo produces features whose `stack == "react_or_angular"` (`Feature.stack`, `feature_grouping.py:51`), carried into every `ChunkPlan` at `src/chunk/chunk_splitter.py:79`/`:93`.
- React/Angular grouping: an organizing folder among `features/pages/routes/views/modules` is found first, and **only its immediate subdirectories** become features (`feature_grouping.py:119-141`); the organizing folder is added to `handled_dirs` (`:127`) and therefore skipped in the loose-file pass (`:143-145`). **Consequence: source files sitting directly inside `src/pages/`, `src/routes/` etc. are dropped from the plan entirely.**
  - Empirical proof (React fixture): `src/pages/Dashboard.tsx` plus `src/components/Header/Header.tsx` → features `[('components', 'react', ['src/components/Header/Header.tsx'])]`. `Dashboard.tsx` never appears in any feature or chunk, with no warning.
  - Empirical proof (Express fixture `ex` with only `src/routes/users.js`): `features: []`, `chunks: []`, schema `0 valid / 0`, zero narration, zero render bundles — the pipeline completes "successfully" having explained nothing.
- Go and Spring/Java share one pairing pass: files in directories named `handler(s)/controller(s)/repository/repositories/service(s)` are paired by resource stem (`_handler|_repository|_service|_controller|Handler|Repository|Service|Controller` stripped), every other directory becomes its own feature — `feature_grouping.py:38-43`, `:183-263`, `:266-271`.
- Python grouping is agent-name based: a stem ending `_main|_router|_config|_test` (or `test_` prefixed) groups under the shared core name; unmatched files become single-file features so nothing is dropped — `feature_grouping.py:45`, `:278-337`.
- Size splitting is language-agnostic: ≤200 lines one chunk, 200-800 and >800 one chunk per file, with `needs_further_split=True` above 200 lines (statement-level splitting is explicitly deferred) — `src/chunk/chunk_splitter.py:24-25`, `:36-41`, `:86-99`, module docstring `:1-14`.
- Grouping has unit tests for Python and Spring layouts — `tests/test_feature_grouping.py:73-96`.

### Inferences
- Chunking "supports" Python and Java in the sense of planning chunks for them; that plan is only ever consumed by the placeholder branch (see Q4), so grouping support creates chunks that cannot be explained.
- The dropped-files defect is not stack-specific (it hits React too) but is most likely to erase an *entire* Express/Node repo, because `src/routes/` holding route modules directly is the idiomatic Express layout.

---

## Q3. What extractors exist in src/extract/?

### Takeaway
Exactly two, both pure regex/heuristic (no AST): `ts_extractor.py` for TypeScript/JavaScript
and `go_extractor.py` for Go. The non-AST choice is documented as deliberate.

### Cited findings
- "Extraction here is regex/heuristic-based static analysis, not a real AST parser (ts-morph, go/ast). That is a deliberate scope decision" — `src/extract/common.py:1-11`.
- TS extractor header: "TypeScript / React (and by extension JS/Angular-shaped) extraction. Regex-based static analysis" — `src/extract/ts_extractor.py:1-5`. Regexes at `:14` (imports), `:28` (`export interface`), `:32` (`function` decls), `:37` (`const x = (…) => {`), `:47` (JSX `on*={`), `:50` (`api.`/`axios.` calls), `:58` (`baseURL`), `:61-68` (handler names, `console.`/`localStorage.`/`sessionStorage.`/`document.cookie` side effects).
- Go extractor: regexes for import blocks, `type X struct`, `func` decls, Fiber `app.Group(...)`, Fiber `var.Get/Post/...("path", handler)`, side effects `.Query/.QueryRow/.Exec/.Begin`, `log*.`, `os.WriteFile/Create/Remove`, and `.Use(` for route protection — `src/extract/go_extractor.py:12-38`, `:175`.
- Routing detection is Fiber-shaped only; `uses_fiber` comes from `"gofiber/fiber" in go.mod` — `src/extract/reuse_pipeline.py:58`, `src/extract/extractor.py:44`.
- `json_builder.py` declares `TS_EXTENSIONS = {".ts",".tsx",".js",".jsx"}` and `GO_EXTENSION = ".go"` — `src/extract/json_builder.py:32-33` — and has exactly two record builders: `build_frontend_chunk_record` (`:85`) and `build_backend_go_chunk_record` (`:243`).

### Inferences
- The TS regexes assume React/ESM idioms: `export interface`, top-level `function`/arrow consts, JSX `on*={…}`, and an `api`/`axios` client. Angular class methods, `@Input()` properties, Angular template bindings `(click)="…"` and `HttpClient.get()` match none of them — see Q6 for the measured result.
- Express/Node idioms (`router.get('/x', fn)`, `app.use`, `module.exports`, `exports.fn = function`) have no regex anywhere; even if an Express repo were routed to the TS builder, routes and handlers would come back empty (`build_frontend_chunk_record` hardcodes `"routes": []` — `json_builder.py:227`).

---

## Q4. CRITICAL — the code path for a stack with no extractor

### Takeaway
Two places emit an identical "not yet implemented" placeholder with `confidence: 0`.
That record **fails schema validation loudly**, but validation is non-blocking: the
pipeline proceeds to generate narration and a renderable video with generic,
contentless speech over the real source code.

### Cited findings — the exact branch
`/home/claude/codeExplanation-v2/src/extract/reuse_pipeline.py:80-94` (the path actually used by the pilot):

```python
        if chunk.stack in ("react", "angular"):
            record = build_frontend_chunk_record(root, chunk, project_type_dict, package_json_dir, base_url)
        elif chunk.stack == "go":
            record = build_backend_go_chunk_record(root, chunk, project_type_dict, module_path, uses_fiber)
        else:
            record = {
                "chunkId": chunk.chunk_id,
                "filePath": chunk.file_path,
                "featureName": chunk.feature_name,
                "projectType": project_type_dict,
                "notes": f"Extraction for stack '{chunk.stack}' is not yet implemented in Phase 3.",
                "confidence": 0,
                "confidenceLevel": "low",
                "contentHash": current_hash,
            }
```

The twin branch in the non-reuse orchestrator, `src/extract/extractor.py:55-72`, is identical
except that it omits `contentHash` and carries the comment:

```python
        else:
            # Python / Spring Boot extraction not yet implemented in Phase 3 —
            # the alumni repo has no genuine marker for either, so there is
            # nothing real to extract against yet. Recorded honestly rather
            # than skipped silently.
```

Note `chunk.stack` is interpolated into the note, so an Express repo produces the
literal note `Extraction for stack 'react_or_angular' is not yet implemented in Phase 3.`

### Cited findings — what happens next
- Schema validation: required fields are `chunkId, filePath, featureName, projectType, language, lineRange, frameworkOrLibrary, featureMapping, confidence, confidenceLevel` plus storage keys `contentHash, lastUpdated, pullRequest` — `src/validate/schema_check.py:14-18`. The placeholder is missing `language`, `lineRange`, `frameworkOrLibrary`, `lastUpdated`, `pullRequest`.
- Measured validation output for the Python fixture: `0 valid / 1`, problems = missing `language`, `lineRange`, `frameworkOrLibrary`, `lastUpdated`, `pullRequest`. Same five for the Spring fixture. A test locks this behaviour in: `tests/test_schema_check.py:81-96` ("Must be reported, not swallowed").
- `confidence: 0` passes the range check (`0 <= 0 <= 1`, `schema_check.py:46-48`) and `confidenceLevel: "low"` is a valid enum value (`:19`), so the only failures are the missing keys.
- **Validation is report-only.** `run_pilot` records `schemaValidation.invalid` into `pilot_report.json` and then unconditionally runs narration, file overviews and render bundles for every record — `src/pilot/run_pilot.py:35-64`. `scripts/run_backend_pilot.py:154-155` just prints "Schema validation: 0/1 valid." and continues; nothing in `run-local.sh` exits on it.
- `featureMapping` is injected into placeholder records by `_apply_feature_mapping`'s `setdefault` (`src/extract/extractor.py:90`), so it is not reported missing.
- Placeholder records are written to the mirror store like any other (`reuse_pipeline.py:107-108`) but carry no `extractorVersion`, so `needs_reanalysis` always returns True for them (`src/storage/mirror_store.py:81-83`) — i.e. `run_pilot`'s `reuseProvenCorrect` flag comes out False on a Python/Java repo.

### Cited findings — what the user actually gets (measured)
Python fixture (`agents/payments_main.py`, a real FastAPI-ish file with a docstring, a raise, two functions):
- narration: purpose `"This section covers payments, built with this stack."` (the `"this stack"` fallback is `src/narrate/script_builder.py:52-54`, reached because both `frameworkOrLibrary` and `language` are absent); flow `"This part of the code has no further steps to narrate beyond what purpose already covered."` (`script_builder.py:147-148`, `:285-291`); recap `"That covers what payments does. Deeper implementation details beyond what's shown here are left for review."` Estimated length 28.7 s.
- file card: `fileType "Source file"`, `layer "Backend"`, `language None`, `purpose None`, no frameworks/libraries/exports/contains/routes, `risks: ['extraction confidence is low']`.
Spring fixture (`AlumniController.java` with a Javadoc header and a `@GetMapping` route):
- identical shape; purpose `"This section covers Alumni, built with this stack."`; card `fileType "Source file"`, **`layer "Frontend"`** (wrong — see Q5), `language None`, `purpose None`.
- The video still renders: `build_render_bundle` needs only `script.beats` plus `filePath`/`featureName` (`src/render/render_pipeline.py:160-210`) — it never reads `language` or `lineRange`; `highlightConfig` is empty because no cues exist. The source file is staged under the fixed name `source.tsx` and displayed as plain text regardless of real extension — `scripts/run_backend_pilot.py:76-79`, `render-app/src/ChunkView.tsx:179`.

### Inferences
- The loud part (schema `invalid` count, `confidence 0`, the note string) is only visible to someone who reads `pilot_report.json` or the console line. The *artifact* — an mp4 with ~29 s of confident-sounding narration per file, over correctly displayed Python/Java source, with no highlights — looks like a finished product and contains no statement that extraction failed. That is the dangerous half of this path.
- The project's own docs acknowledge the gap: "Python and Spring Boot extraction are not implemented … Phase 3's `extract_repo()` only has real builders for React/Angular and Go" — `documentation/13-known-gaps-and-roadmap.md:10-26`. They do **not** mention the Angular-empty or Express cases below.

---

## Q5. What does src/extract/function_context.py assume about syntax?

### Takeaway
Its doc-comment reader understands only `//` and `/* */`, and its exported test is
Go's capital-letter rule or a literal `export` prefix. For Python and Java every
derived field comes back empty or false — silently, with no "assumed" flag.

### Cited findings
- Comment markers stripped are `/**`, `*/`, leading `*`, leading `//` — `src/extract/function_context.py:45-66`. `#` (Python/Ruby/shell) and `"""` docstrings appear nowhere in the module.
- `leading_doc_comment` only enters a block if the line above the definition ends with `*/` or starts with `//`; otherwise it returns `None` — `function_context.py:86-99`. A Python docstring is *below* the `def` line, so even if `"""` were recognised the position would be wrong.
- `file_header_comment` likewise accepts only a file-opening `/*` or `//` block — `function_context.py:129-142`. A Python module docstring (`"""…"""` at line 1) returns `None`; measured: the Python fixture's card `purpose` is `None` and `fileDescription` is absent, although the file does have a module docstring.
- `is_exported`: `if language == "go": return name[0].isupper()` else `return signature.lstrip().startswith("export")` — `function_context.py:159-163`. Only `"ts"` and `"go"` are ever passed (`src/extract/json_builder.py:137`, `:280`). Java `public`, Python's leading-underscore convention, and CommonJS `module.exports`/`exports.x` are all read as **not exported**.
- `_THROW_RE` matches `throw new`, `errors.New(`, `fmt.Errorf(` — `function_context.py:41`: Python `raise` and Java `throw new X()`… (`throw new` would match Java, but `raise` would not).
- `_AWAIT_RE` is `\bawait\b` and `isAsync` also checks `"async" in signature` — `function_context.py:42`, `:250`: Python `async def`/`await` would match incidentally; Java `CompletableFuture` would not.
- `_REACT_HOOK_RE` matches `useState|useEffect|useCallback|useMemo|useRef|useContext|useReducer` — `function_context.py:40`: a React-only field present on every record regardless of language.
- Call graph (`callers_of`, `calls_made`, `function_context.py:166-190`) is a bare `\bname\s*\(` text search over the function body, so it is language-agnostic but also matches a name in a comment or string.
- Param parsing splits on `,` then takes the text before `:` or the first space — `function_context.py:193-210`: handles `ctx context.Context` (Go) and `raw: string` (TS); Java `final List<String> xs` would yield `final`, and a generic containing a comma (`Map<String, Integer> m`) would split wrongly.
- None of this is ever reached for Python/Java today, because `build_function_context` is only called from the two TS/Go builders (`json_builder.py:131`, `:274`). It becomes an active hazard the moment a Python or Java extractor is added without revisiting it.

### Inferences
- Of the eight derived fields, for a hypothetical Python/Java path: `description`/`descriptionSource` → always None, `exported` → always False, `reactHooks` → always empty, `raisesError` → false for Python, `params` → wrong for Java generics; only `calledBy`/`calls`/`lineCount` would be approximately right.

### Gaps
- No test exercises `is_exported` or `leading_doc_comment` with a non-TS/Go language argument (`tests/test_function_context.py` exists; its cases are TS/Go-shaped).

---

## Q6. What does src/narrate/file_overview.py assume? (and the Angular trap)

### Takeaway
Framework markers do name FastAPI, Django, Flask, Spring, Express and Angular — but
they are matched against `frameworkOrLibrary`/`dependencies`, which only the TS and Go
extractors ever populate, so for Python/Java they are dead code. Layer classification
has no `.java` rule and mislabels Java as Frontend. Separately, **Angular produces a
schema-valid, "high"-confidence, completely empty record** — the most dangerous
output in the repo.

### Cited findings — file_overview
- `_FRAMEWORK_MARKERS` includes `gofiber/fiber`, `gin-gonic/gin`, `labstack/echo`, `net/http`, `react`, `@angular`, `vue`, `svelte`, `next`, `express`, `fastapi`, `django`, `flask`, `spring` — `src/narrate/file_overview.py:95-110`. Fed from `record["frameworkOrLibrary"] + record["dependencies"]` (`:427-432`), both of which the placeholder record lacks → measured `frameworks: []`, `libraries: []` for Python and Java.
- `_FILE_TYPE_RULES` path fragments are React/Go shaped: `/cmd/`, `/handler/`, `/repository/`, `/hooks/`, `/components/`, `/features/`, `/api/`, `/lib/` — `file_overview.py:33-49`; `_FILE_NAME_RULES` are `main.tsx`, `main.go`, `index.tsx`, `client.ts` — `:51-56`. Test-file detection covers only `.test.ts(x)`, `.spec.ts(x)`, `_test.go` — `:69`, `:197`, `:356`: Python `test_*.py` and Java `*Test.java` are never recognised as tests.
- `classify_file_type` fallbacks: `.tsx` → UI component, `.go` → Go source file, else `f"{record['language'] or 'Source'} file"` — `file_overview.py:84-88`. Measured: Python → `"Source file"`, Java → `"Source file"`.
- `classify_layer` has rules for `.go`, `.tsx/.jsx/.css/.scss/.html`, `.ts`, `.py` (→ Backend), and a final fallback `LAYER_BACKEND if record["language"] == "Go" else LAYER_FRONTEND` — `file_overview.py:220-231`. **There is no `.java` branch**, and a placeholder record has no `language`, so a Spring controller is labelled **`layer: "Frontend"`** on the card (measured). The `.py` branch at `:229` does fire, so Python lands on Backend by path extension alone.
- `_AGENTIC_MARKERS` (langchain, langgraph, openai, anthropic, mcp, crewai, …) — `file_overview.py:114-118` — also only sees `frameworkOrLibrary`/`dependencies`, so a Python LangChain agent is never classified `Agentic` today.
- `_pretty_package` is tuned to Go module paths and npm scopes (`_GENERIC_SEGMENTS`, `_CODE_HOSTS` at `:129-130`, logic at `:137-159`); Maven coordinates (`org.springframework.boot:spring-boot-starter-web`) and Python distribution names are not modelled.
- Key-mismatch bug affecting **all** stacks: `json_builder.py:176` and `:298` emit side effects as `{"type": kind, "description": …}`, while `file_overview.py:442-445` reads `effect.get("kind")` — so the card's `sideEffects` list is always empty even for React/Go files that do have detected side effects.
- Unavailable-field honesty is real: `unavailable` records why purpose/lastModified/owner/tests are missing, and shallow-clone dates and CODEOWNERS are refused rather than faked — `file_overview.py:319-345`, `:391-406`.

### Cited findings — Angular measured end-to-end
Angular fixture (`src/app/alumni/alumni.component.ts`: `export class AlumniComponent`, constructor-injected `HttpClient`, a `load()` method calling `this.http.get('/api/alumni')`, `@Component` decorator):
- detected `frontend: 'angular'`; one chunk, stack `angular`; routed to `build_frontend_chunk_record` (`reuse_pipeline.py:80-81`).
- extraction result: `importantFunctions []`, `eventHandlers []`, `apiCalls []`, `dataModels []`, `inputs []`.
- **`confidence: 0.95`, `confidenceLevel: "high"`** — because `confidence_from_flags` returns the base 0.95 when `total_claims == 0` (`src/extract/common.py:103-111`), and `confidence_level(0.95)` → `"high"` (`:114-119`).
- schema validation: **1 valid / 1**. No problems reported.
- narration: `"This section covers app, built with @angular/core."` + `"This part of the code has no further steps to narrate beyond what purpose already covered."` + recap. 28.2 s. Zero visual cues → no highlights.
- card: `fileType "TypeScript file"`, `layer "Frontend"`, `frameworks ['Angular']`, `purpose "Alumni list component for the admin area."` (the `//` header comment was read), `exports []`, `contains []`, `risks []` — **no risk is flagged at all.**
- Cause, in the regexes: `FUNCTION_DECL_RE` requires the `function` keyword and `ARROW_CONST_RE` requires `const x = (…) => {` (`src/extract/ts_extractor.py:32-43`), so Angular class methods are invisible; `INTERFACE_RE` requires `export interface` (`:28`) so `@Input()` props are invisible; `API_CALL_RE` matches only `api.`/`axios.` (`:50-57`) so `HttpClient` calls are invisible; `JSX_ON_PROP_RE`/`JSX_INLINE_HANDLER_RE` match `on[A-Z]…={` (`:47`, `:62`) so Angular template `(click)="…"` bindings are invisible. The module docstring itself only claims "TypeScript / React (and by extension JS/Angular-**shaped**)" — `ts_extractor.py:1-5`.

### Inferences
- Angular is the single most dangerous stack in this pipeline: unlike Python/Java it produces **no loud signal anywhere** — valid schema, "high" confidence, empty `risks`, a correct-looking file card with the real framework name — while the narration content is empty. A reviewer checking `pilot_report.json` would see "1/1 valid, confidence high" and conclude it worked.
- The Angular failure mode is strictly worse than the Python/Java one, which at least registers `0 valid`, `confidence 0`, a `low` confidence level and an explicit `risks: ['extraction confidence is low']` entry.

---

## Q7. Does anything handle .py, .java, or .js/.jsx as opposed to .ts/.tsx?

### Takeaway
Language *naming* covers all of them; language *handling* does not. `.js/.jsx`
are handled only when the repo also declares React or Angular; otherwise they fall
into the placeholder branch or are dropped.

### Cited findings
- `LANGUAGE_BY_EXTENSION` maps `.tsx/.ts → TypeScript`, `.jsx/.js → JavaScript`, `.go → Go`, `.py → Python`, `.java → Java`, with an unknown-extension fallback of the bare suffix — `src/extract/common.py:24-39`. This only labels; it selects nothing.
- Chunker walks `.js/.jsx` (`feature_grouping.py:28`) and `json_builder.TS_EXTENSIONS` includes them (`json_builder.py:32`), but the dispatch key is `chunk.stack`, not the file extension — `reuse_pipeline.py:80-83`, `extractor.py:55-58`. So `.js` files are TS-extracted only if `frontend_stack` resolved to `react` or `angular`.
- Measured, Express fixture with a conventional layout (`src/app.js` + `src/controllers/userController.js`): features `[('controllers','react_or_angular',[…]), ('src','react_or_angular',[…])]`, both records `confidence 0`, `confidenceLevel low`, note `Extraction for stack 'react_or_angular' is not yet implemented in Phase 3.` — i.e. an Express repo gets the Python-style placeholder, despite being JavaScript the TS extractor could partly read.
- Measured, Express fixture with `src/routes/` only: zero features, zero chunks (see Q2) — the pipeline produces no video content and reports no error.
- `.py` is handled by: detection (marker + hint), grouping (`group_python_agent_features`), `detect_language`, and `classify_layer`'s `.py → Backend` rule (`file_overview.py:229`). Nothing else.
- `.java` is handled by: detection (marker + hint), grouping (`group_spring_boot_features`), `detect_language`. `classify_layer` has no `.java` rule at all (`file_overview.py:220-231`).

---

## Q8. Test suite

### Takeaway
236 tests pass; coverage of non-TS/non-Go stacks is limited to detection, grouping
and the placeholder's *invalidity* — no test asserts anything about the narration or
video a Python/Java/Express/Angular repo produces.

### Cited findings
- `/home/claude/codeExplanation-v2/.venv/bin/python -m pytest -q` → `236 passed in 2.06s`.
- 30 test files; the only ones touching other stacks: `tests/test_project_type.py` (Angular detection `:21-24`, Python `:34-37`, Spring vs plain Java `:40-49`, stray-`.py` hints `:89-98`), `tests/test_feature_grouping.py` (Python agent grouping `:73-89`, Spring controller/service pairing `:92-96`), `tests/test_schema_check.py:81-96` (placeholder record must fail validation).
- There is no `tests/test_python_extractor.py` / `test_java_extractor.py` / Express or Angular extraction test; `tests/test_ts_extractor.py` and `tests/test_go_extractor.py` are the only extractor test files (`find tests -name "*.py"`).
- No test asserts the *absence* of Angular content, which is why the empty-but-confident Angular record is not caught by the suite.

### Inferences
- The suite's green status is accurate but says nothing about end-to-end stack coverage; it tests that unsupported stacks are *recorded* as unsupported, not that the user-visible output is safe.

---

## Loud vs silent failure — ranked by danger

1. **Silent, highest risk — Angular.** Schema-valid, `confidence 0.95 / "high"`, `risks: []`, correct framework on the card, and narration with zero substance. Nothing anywhere in the output says extraction found nothing. Evidence: measured run; `src/extract/ts_extractor.py:28-62`; `src/extract/common.py:103-111`.
2. **Silent, high risk — files dropped by the frontend grouper.** Any source file sitting directly in `src/pages|routes|features|views|modules` is omitted from the chunk plan with no warning; for an Express repo laid out as `src/routes/*.js` this erases the entire repo and the run still reports success. Evidence: `src/chunk/feature_grouping.py:119-145`; measured `features: []`, `chunks: []`.
3. **Silent-ish — Java layer mislabelled `Frontend`** on the file card shown before each file. Evidence: `src/narrate/file_overview.py:220-231`; measured.
4. **Silent, all stacks — card `sideEffects` always empty** due to the `type` vs `kind` key mismatch. Evidence: `src/extract/json_builder.py:176`, `:298` vs `src/narrate/file_overview.py:442-445`.
5. **Loud but non-blocking — Python / Spring Boot / Express placeholder.** `confidence 0`, `confidenceLevel low`, explicit note, 5 schema errors, `risks: ['extraction confidence is low']`. But validation does not gate anything (`src/pilot/run_pilot.py:35-64`), so a ~29 s/file video with generic narration over real source is still produced and staged. Evidence: `src/extract/reuse_pipeline.py:85-94`; `src/extract/extractor.py:59-72`; measured.
6. **Genuinely loud (hard failure) — none for unsupported stacks.** The only hard aborts in the run script concern missing TTS/ffmpeg/node and a missing staged manifest (`run-local.sh:117,137-174,276-285,362-384`), i.e. tooling, not stack support.

## Gaps in this audit
- Not run: the actual Remotion render / TTS for the fixture repos (requires piper/espeak + ffmpeg + `npm install`); the render-bundle analysis above is from reading `src/render/render_pipeline.py` and `scripts/run_backend_pilot.py`, plus the fact that neither reads `language`/`lineRange`.
- Fixtures were minimal synthetic repos, not large real-world Angular/Express/Spring projects; the *mechanisms* are proven, the exact per-file yield on a big repo is not.
- `src/detect/source_resolver.py`, `src/narrate/visual_cues.py`, `src/render/highlight_config.py` were not read line-by-line; claims about cues being empty for placeholder records follow from records having no `importantFunctions`/`routes`/`eventHandlers` and from the measured `flow`/card output, not from reading `visual_cues.py`.
