# Known Gaps and Roadmap

Every gap below is carried forward deliberately and documented in the
code/plan rather than silently dropped. This file consolidates them in
one place, plus the two security incidents fixed after the engineering
code review.

## Current stack picture

Product visuals + honesty: [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).
Doc 14 is a **historical** audit — read its banner first.

| Stack | Detect | Chunk | Extract | Visuals honesty |
|---|---|---|---|---|
| React TS/JSX | yes | yes | `extract/react/` (regex) | tree/lifecycle when mounts exist; regex limits remain |
| Go Fiber | yes | yes | `extract/go/` (regex) | `route_tree`; in-file prefixes compose |
| Angular | yes | yes | `extract/angular/` | selector→usage mounts + signal/decorator I/O; empty → unavailable |
| Vue / Solid / Qwik / JS | yes | yes | `extract/{vue,solid,qwik,javascript}/` | thin trees; skip when empty |
| Python | yes | yes | `extract/python/` (`ast`) | in-file APIRouter prefix; Django `path()` literals (method UNKNOWN); empty → unavailable |
| Spring Boot | yes | yes | `extract/spring/` | `di_graph` by type + Lombok/setter/@Inject; bare `@RequestMapping` → ALL; no Impl-from-imports |
| Express | yes | yes | `extract/express/` | `route_tree` incl. route chains; backend stack |
| Rust | yes | yes | `extract/rust/` | partial; method from attrs; routes assumed |

## Carried-forward product gaps

Keep these as roadmap: deeper parsers (tree-sitter / typed), package-
level Go / Angular component-bundle chunking, cross-file route-prefix
resolver, `outputs` always empty, statement-level split
(`needs_further_split` unused), LLM-elaborated narration (`llm:` config
unused), production voice quality.

whisper.cpp-blocked-so-all-cues-assumed and the Chromium-sandbox
download are **environment notes**, not the live production story.
Live alignment is `measured-beats`; live TTS is Piper then espeak-ng.
See [`09-phase6-rendering.md`](./09-phase6-rendering.md).

## Carried-forward implementation gaps (detail)

### 1. Multi-stack extractors are shipped but still thin

Python (`ast`), Spring (DI-by-type), Express, Angular, Vue/Solid/Qwik,
JS, Rust, React, and Go builders exist (`EXTRACTOR_VERSION` 12). All
stacks use `src/extract/<stack>/{extract,record}.py`; flat modules are
shims; `stack_records.py` re-exports. Remaining gaps: regex ceilings,
cross-file route prefixes, package-level Go chunking, Angular
template-bundle chunking (class+html as one chunk unit), Spring
typed interface→impl resolution (still never invent Impl from imports).
Spring honesty enrichments landed (`EXTRACTOR_VERSION` 12): bare
`@RequestMapping` → `ALL`; multi `method=` / path arrays; `${}`/`#{}`
assumed; setter/`@Inject` DI; multi-ctor assumed; Spring Data repo
interfaces without proxy Impl. Django `urlpatterns` `path()`/`re_path()`/
`url()` literals landed (`EXTRACTOR_VERSION` 11; method `UNKNOWN`;
`include()` mounts assumed, not joined). Angular project selector
index → template child mounts landed (`EXTRACTOR_VERSION` 10). Doc 14’s
“placeholder only” claim is **obsolete**; its structural ceiling
analysis still applies.

### 2. `outputs` field is never populated

The schema has an `outputs` field (callbacks/events for React/Angular,
return values for Python, response bodies for Go Fiber/Spring Boot),
but Go/`go/record.py` still emits `"outputs": []` (React fills callback
outputs from JSX prop mounts when present).

**What closes it:** extending `react/extract.py` / `go/extract.py` to
infer return types/emitted events, following the same
assumed-when-uncertain pattern used everywhere else.

### 3. whisper.cpp model download / estimated alignment — environment note

The leftover `transcribe.mjs` path still cannot fetch its Hugging Face
model in this sandbox. That is **not** the live aligner.
`build_render_bundle` writes `"alignmentSource": "measured-beats"`.
Keep `transcribe.mjs` as unused/optional.

**What closes it (if anyone revives transcript alignment):** reachable
Hugging Face, or a pre-provided model file.

### 4. Remotion Chromium download — environment note

Already worked around in `run-local.sh` via Playwright Chromium (Linux
sandbox) or an installed Chrome/Chromium/Edge/Brave (macOS), plus
`REMOTION_BROWSER_EXECUTABLE`. Not a current product gap.

### 5. The narrator's 90–180s target band is reliably met only for feature-rich chunks

Historical Alumni-web snapshot (old short templates): only 2/22 chunks
landed in the target band. Function-aware item beats plus real pauses
changed the distribution; **re-measure** rather than citing 2/22 as
current. Not a bug — a template built strictly from grounded fields
simply has less to say about a small chunk. The target stays; it is
unmet for many small files.

**What closes it:** either treat the 90–180s target as meant for
feature-rich chunks specifically, or add a richer, LLM-elaborated
script stage (same structure, richer prose) that pads small chunks
*without inventing ungrounded content* — see Phase 5's doc for why the
template approach was chosen first and what this upgrade would need to
preserve.

### 6. Production voice quality is still not shipped

Piper (Indian-English) is the default when the model is cached;
espeak-ng is the required fallback. That is a partial delivery of the
original Coqui/Indian-English requirement, not a commercial studio
voice. Measured-beat alignment replaced estimated-every-cue.

**What closes it:** a higher-quality TTS swap of `tts.py: synthesize()`
(still one function). whisper.cpp is not required for that.

### 7. No statement-level split for oversized single files

`chunk_splitter.py` flags a file over `small_max_lines` within a
medium/large feature as `needs_further_split=True`, but nothing yet
consumes that flag to actually perform a second, statement-level split.

**What closes it:** once a real parser is introduced for a stack (the
natural Phase 3 upgrade path already discussed in its own doc), use it
to split flagged files at real statement boundaries rather than leaving
them as one oversized chunk.

## Security incidents found by code review and fixed

These were found via `/engineering:code-review` against this repo's
full commit history and fixed in a follow-up commit (168 tests passing
**at that time**; live count is in
[`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md)).
A before/after real-repo pilot re-run showed identical output —
confirming no regression.

### A. Secret redaction built but never wired into the real pipeline (Critical)

`secret_scan()` existed and was unit-tested in isolation since Phase 0,
but nothing in the real extraction path ever called it — a hardcoded
secret in a source file would have been copied verbatim into the
output JSON. **Fix:** added a non-raising `redact_secrets()` and wired
it into `extract/common.py: trim_snippet()` — the one choke point every
code snippet passes through — so no current or future extractor call
site can bypass it. `json_builder.py` now surfaces a `secretsRedacted`
flag per snippet, adds a reviewer note, and caps confidence at 0.5 for
any affected chunk. Proven with a dedicated end-to-end integration test
(`tests/test_secret_redaction_integration.py`) that reproduces the
exact leak and asserts it's closed — specifically because a unit test
of `guardrails.py` alone, which already existed, is what let this gap
go unnoticed for seven phases.

### B. Path traversal in `source_resolver.resolve_source()` (Critical)

A crafted source value ending in a directory-traversal segment (e.g.
`.../someorg/..`) produced a clone-directory slug of `".."`, resolving
the intended clone destination to the workdir's own **parent** — an
arbitrary, already-existing directory — while silently skipping the
clone step (because that parent "already existed"), handing the rest of
the pipeline the wrong directory to scan. A related hostname-substring
bug (`"github.com" in netloc` accepting `github.com.attacker.net`) was
found and fixed alongside it. **Fix:** reject any unsafe slug (empty,
`.`, `..`, or containing a path separator), independently re-verify the
resolved destination is a true child of the workdir, switch to an
exact-or-subdomain host check, and add a `--` argument separator before
the URL in the `git clone` argv for defense in depth. 11 new regression
tests, including both exact repros from the review.

### C. Unencoded file path in the PR-lookup `gh api` query string (Medium)

`pull_request_lookup.py` interpolated `file_path` raw into a query
string, so a path containing `&`, `#`, `%`, or a space could produce a
malformed or semantically wrong request. **Fix:**
`urllib.parse.quote(file_path, safe="/")`. This module also had zero
dedicated tests before this fix despite being in use since Phase 4 —
closed with a new `tests/test_pull_request_lookup.py`.

## From the original project requirement — what changed and why

The project's original, more exploratory requirement document (see the
"Requirement" doc in this project's Claude Docs store) proposed several
specific tools that the implemented pipeline deliberately replaced; each
substitution is explained in full in its phase doc, summarized here:

| Original proposal | What was actually built | Why (see phase doc) |
|---|---|---|
| Per-chunk LLM call (Bard/Gemini free tier) for `narrativeScript` and structured metadata | Mechanical, template-based extraction (Phase 3) + narration (Phase 5) | Determinism, testability, no per-chunk cost/latency/quota risk, zero risk of inventing ungrounded claims — see Phase 5 doc |
| Coqui TTS (Indian English) with `edge_tts` fallback | **Piper** Indian-English (preferred) + **espeak-ng** fallback, both local | Offline, no API key; Piper is the partial original-requirement delivery; commercial vendor still a one-function swap — see Phase 6 doc |
| WhisperX word timestamps | **Measured-beat** alignment (per-beat WAV + silence). whisper.cpp leftover | Cue windows come from measured beat durations, not a transcript — see Phase 6 doc |
| `ts-morph`/Babel static analysis | Regex/heuristic extraction, confidence-scored | No repo-specific build/tooling assumptions required for "any repo as input"; upgrade path explicitly left open — see Phase 3 doc |
| Fixed component/folder-based chunking | Feature-wise, stack-specific grouping, no hardcoded folder names | Matches the actual locked requirement ("the unit is the FEATURE") and generalizes across arbitrary repo layouts — see Phase 2 doc |

None of these substitutions are regressions from the original idea —
each one is a scoped, documented decision that keeps the system fully
working end to end inside this specific environment's real constraints,
with an explicit, named upgrade path back toward the original proposal
wherever that upgrade would add real value (richer narration, a
production voice, real word-level timing) without compromising the
accuracy/honesty guarantees the rest of the pipeline depends on.
