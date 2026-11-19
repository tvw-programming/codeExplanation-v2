# Function Rationale Index

One consolidated table of every major function/module decision covered
in the phase docs, and the alternative it deliberately avoided. Use
this as a quick cross-reference; each row links to the phase doc with
the full explanation.

| Phase | Function / Module | Chosen approach | Alternative avoided, and why |
|---|---|---|---|
| 0 | `load_config()` | Typed `PipelineConfig` dataclass, validated once at load | Raw dict passed around — typos fail silently, deep in a later phase |
| 0 | `source_resolver.resolve_source()` | Shallow (`--depth 1`) clone | Full clone — history isn't needed here; PR history is fetched separately via `gh api` |
| 0 | `_looks_like_git_url()` | Checks `git@` or `(http(s) + .git / recognized host)` | Bare `http` prefix check — would accept non-git URLs and give confusing git errors |
| 0 | slug/destination validation in `resolve_source()` | Rejects unsafe slugs, re-verifies resolved path is inside workdir | Trusting whatever path `git clone`'s target argument resolves to — caused a real path-traversal bug |
| 0 | `_host_is_github()` | Exact-or-subdomain host match | `"github.com" in netloc` substring check — accepted `github.com.attacker.net` |
| 0 | `git clone` argv `--` separator | Explicit positional-argument separator | Relying solely on URL-shape validation to prevent flag injection |
| 0 | `secret_scan()` + `redact_secrets()` as two functions | Raise-on-match for hard blocks; redact-and-flag for snippet content | One function for both — would either crash legitimate chunks or silently under-protect blocked files |
| 0 | `_SECRET_PATTERNS` | Deliberately broad/coarse | A tighter, low-false-positive detector — risks missing a real secret, the worse outcome |
| 0 | path blocking via `fnmatch` glob | `.env*`, `*.pem`, `*secrets*` | An explicit filename list — needs updating per new naming convention |
| 1 | `_find_marker_hits()` | Marker-file detection (`go.mod`, `package.json`, ...) | Extension-based scanning — misclassifies stray files as a detected stack |
| 1 | bounded `max_depth` walk | Depth-limited directory walk | Unbounded recursive walk — slow in large/vendored trees |
| 1 | `_find_unclaimed_hints()` | Surface hinted-but-unmarked files for human review | Silently ignore them, or silently promote them to a detected stack |
| 1 | `_detect_frontend_flavor()` | Checks actual `package.json` dependencies | Assuming every `package.json` means React |
| 1 | `_detect_java_flavor()` | Checks for `spring-boot` dependency in build file contents | Assuming any Maven/Gradle project is Spring Boot |
| 1 | architecture heuristic | Count of distinct backend marker-file roots | Counting Dockerfiles or top-level folders — less direct a signal |
| 2 | `group_react_or_angular_features()` | Checks a list of conventional organizing-folder names; **flat files in the organizing folder are now claimed** | Hardcoding one specific layout; earlier only *subdirectories* became features (silent empty runs) |
| 2 | `_group_by_resource_pairing()` | One shared function for Go + Spring Boot/Java | Two near-duplicate implementations — doubles the surface for bugs |
| 2 | `RESOURCE_SUFFIX_PATTERN` | Fixed suffix-stripping list (`_handler`, `Controller`, ...) | Fuzzy/Levenshtein filename matching — slower, riskier false pairings |
| 2 | `group_python_agent_features()` | Separate agent-convention grouping | Reusing the Go/Spring Boot resource-pairing function — wrong convention for Python |
| 2 | file-level split for medium/large features | Split at file boundaries; flag oversized files `needs_further_split` | Attempting a statement-level split without a real parser (duplicates Phase 3's job) |
| 2 | `make_chunk_id()` | SHA-256 hash of `file_path:feature_name` + readable slug | A running counter — unstable across runs with different file-walk order |
| 3 | extraction engine overall | Regex/heuristic static analysis, confidence-scored | A real AST parser (ts-morph/go-ast) from day one — adds build/tooling assumptions about an arbitrary input repo |
| 3 | `trim_snippet()` | Single choke point for trimming + secret redaction | Scattering secret-scan calls across every extractor call site — this is exactly what went missing before the fix |
| 3 | `confidence_from_flags()` | Simple linear penalty, explicitly "not validated" | A more elaborate weighted scoring model — would look precise without any real backing evidence |
| 3 | `_resolve_frontend_framework_or_library()` | Cross-references the repo's real `package.json` | A hardcoded list of known framework import paths — unmaintainable against arbitrary repos |
| 3 | `normalize_path()` / `match_calls_to_routes()` | One shared `{}`-placeholder normalization for both `${id}` and `:id` | Exact string matching — would never connect a frontend call to its backend route |
| 3 | inline JSX handler extraction | Always `assumed: true`, no synthesized name | Inventing a plausible name/purpose for an anonymous inline function |
| 4 | `output_path_for()` | Mirrors the real repo's directory structure | A flat `chunks/<chunkId>.json` layout — opaque to a human browsing the output |
| 4 | `needs_reanalysis()` | SHA-256 content hash **and** `EXTRACTOR_VERSION` (currently 6) | File modification timestamp; also: hash-only reuse would keep stale JSON after extractor upgrades |
| 4 | "no stored hash" handling | Treated as "needs re-analysis" | Trusting an old record with no hash to compare — unjustified optimism |
| 4 | `extract_repo_with_reuse()` | Always recomputes `featureMapping` fully, even with reused chunks | Caching cross-chunk links per-chunk — risks stale links when a linked chunk changes |
| 4 | `find_last_pull_request_url()` | Best-effort, never raises, returns `None` on any failure | Propagating failures — `pullRequest` being unknown is an expected, accepted state |
| 4 | `file_path` in `gh api` query | URL-encoded via `urllib.parse.quote()` | Raw interpolation — broke on `&`/`#`/`%`/spaces in a path |
| 4 | PR lookup scope | Verified against this project's own repo only | Force-attaching the third-party example repo just to read its PR history |
| 5 | narration generation overall | Template-based, deterministic, grounded in the extracted record | An LLM call per chunk — non-deterministic, costly at scale, and risks un-grounded claims |
| 5 | `build_item_beats()` / `function_narration.py` | Per-function spoken text from doc comments, callers, body facts + real `pause_after_ms` | A single "The X function runs next" flow sentence per symbol |
| 5 | `file_overview.py` | FileCard payload (purpose from `fileDescription`, `unavailable` reasons) | Cutting from the last line of one file to the first of the next with no chapter title |
| 5 | `PRONOUNCEABLE_ACRONYMS` | Table **built**; **not applied** to TTS — identifiers spoken as written (doc 15) | Splitting camelCase at runtime (would mismatch the name on screen); SSML unused |
| 5 | `generate_visual_cues()` | Cues `importantFunctions`, `eventHandlers` (now with `lineRange`), `routes` | Fabricating a line range for `dataModels`; older docs that said handlers have no range |
| 5 | `dependency_first_order()` | Deterministic "fewest unseen links first" heuristic | A real topological sort — undefined, because `featureMapping` is undirected, not a DAG |
| 5 | `build_flow_beats()` split | Splits only at a sentence boundary near the time budget | Truncating by raw word/char count — risks cutting a spoken sentence in half |
| 5 | hedge phrasing | One single fixed phrase ("It looks like") for every assumed claim | Varying wording per field type — dilutes the listener's learned signal |
| 6 | `tts.py: synthesize()` | **Piper** Indian-English voice preferred; **espeak-ng** fallback; `ttsEngine` recorded | Cloud TTS as the *only* engine; also: older docs that say espeak-ng is the sole engine |
| 6 | `build_render_bundle()` timing | Per-beat synthesis + silence + concat; `alignmentSource: measured-beats` | Transcribing the whole track with WhisperX / whisper.cpp, or even-word `estimated` as the live path |
| 6 | `build_estimated_words()` / `transcribe.mjs` | **Legacy / unused** by the live bundle (still unit-tested) | Presenting them as the production aligner |
| 6 | `highlight_config.py` | Kept to a pure seconds→frames conversion | Folding rendering logic into Python |
| 6 | `ChunkView.tsx` highlights | CSS selection bar over plain text | Shiki decorations (dependency present, **not imported**) |
| 6 | Remotion `FullVideo` + `FileCard` | Concatenates every staged chunk; card introduces each file | Shipping only `CodeExplainerChunk` (that composition remains the sample-chunk demo) |
| 6 | `calculateMetadata` | Duration from measured `durationMs` (plus card frames) | A fixed/hardcoded composition duration |
| 7 | `validate_record()` | Checks `pullRequest`'s **key**, not its value, for presence | Requiring non-null — would force fabricating a PR URL for a legitimately unknown one |
| 7 | placeholder records for unimplemented stacks | Allowed to legitimately fail schema validation | Special-casing them to pass — hides a real, known gap |
| 7 | `run_pilot()` double extraction run | Re-runs extraction once more inside the pilot to prove reuse on real data | Trusting Phase 4's unit tests alone — proves the mechanism in isolation, not on this specific real repo |
| 7 | `pilot_report.json` shape | Raw honest numbers, no pass/fail verdict | A single boolean verdict — would force an arbitrary judgment call about which gaps are acceptable |
