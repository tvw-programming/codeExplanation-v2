# Known Gaps and Roadmap

Every gap below is carried forward deliberately and documented in the
code/plan rather than silently dropped. This file consolidates them in
one place, plus the two security incidents fixed after the engineering
code review.

> **Superseded in part by `14-stack-support-validation.md`.** A
> six-stack validation found that this file understated the problem in
> two ways. It framed the gap as "two stacks lack extractors", when in
> fact **Angular** produces schema-valid, fully-empty records (worse
> than a loud failure, because the video looks finished), **Express**
> cannot even be detected as a backend stack, and **Go is not as well
> supported as the text below implies** — generics, interface methods
> and closure-returning middleware are all invisible to it. Read that
> document for the current picture; the gaps below remain accurate as
> far as they go.

## Carried-forward implementation gaps

### 1. Python and Spring Boot extraction are not implemented

Feature *grouping* exists for both (`group_python_agent_features()`,
`group_spring_boot_features()`), but Phase 3's `extract_repo()` only has
real builders for React/Angular and Go — note that the Angular path is
the React builder, which matches almost nothing in an Angular file (see
`14-stack-support-validation.md`) — a chunk planned for either
other stack gets an honest placeholder record (`confidence: 0`,
`notes: "Extraction for stack '<stack>' is not yet implemented in
Phase 3."`), which correctly **fails** Phase 7's schema validation by
design.

**Why not implemented yet:** no real repo of either stack was available
to validate real extraction against — and this project's established
practice (every phase doc above) is to verify extraction logic against
genuine code before trusting it, not to ship untested heuristics for a
stack nobody has exercised.

**What closes it:** a real Python agent-based repo or Spring Boot repo
to test against, then two new extractor modules mirroring
`ts_extractor.py`/`go_extractor.py`'s shape (regex/heuristic, confidence-
scored, feeding the same `json_builder.py` schema).

### 2. `outputs` field is never populated

The schema has an `outputs` field (callbacks/events for React/Angular,
return values for Python, response bodies for Go Fiber/Spring Boot),
but `json_builder.py` currently always emits `"outputs": []`.

**What closes it:** extending `ts_extractor.py`/`go_extractor.py` to
infer return types/emitted events, following the same
assumed-when-uncertain pattern used everywhere else.

### 3. The real whisper.cpp alignment path is network-blocked in this sandbox

The binary compiles and runs; only the `huggingface.co` model-file
download is blocked by this sandbox's network allowlist (confirmed via
a direct `curl`: 403 at the proxy). Every real pilot run in this
session used the `estimated` fallback instead, honestly labeled.

**What closes it:** run in an environment where that host is reachable,
or pre-provide the model file. No code change needed — the real path
runs automatically once the download succeeds.

### 4. Remotion's own headless-Chromium download is also network-blocked

**What closes it:** already worked around for local verification via
`--browser-executable` pointing at this environment's pre-installed
Playwright Chromium. In an unrestricted environment, Remotion's normal
Chromium fetch would simply work.

### 5. The narrator's 90–180s target band is reliably met only for feature-rich chunks

Only 2/22 real chunks land in the target band with the current
template-only script generator; the other 20 (small, low-complexity
chunks) land shorter. Not a bug — a template built strictly from
grounded fields simply has less to say about a small chunk.

**What closes it:** either treat the 90–180s target as meant for
feature-rich chunks specifically, or add a richer, LLM-elaborated
script stage (same structure, richer prose) that pads small chunks
*without inventing ungrounded content* — see Phase 5's doc for why the
template approach was chosen first and what this upgrade would need to
preserve.

### 6. espeak-ng + estimated alignment are explicitly not production-ready

Stated directly in the Phase 7 plan: good enough to prove the full
mechanism, not recommended to ship as-is (robotic voice; 100% of cues
`assumed=true` in this environment since no real transcription ran).

**What closes it:** swap `tts.py: synthesize()` for a commercial TTS
vendor (one isolated function) and get the whisper.cpp path's network
dependency resolved (see gap 3).

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
full commit history and fixed in a single follow-up commit (168 tests
passing after the fix, with a before/after real-repo pilot re-run
showing identical output — confirming no regression).

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
| Coqui TTS (Indian English) with `edge_tts` fallback | `espeak-ng`, local and offline | Actually runs in this environment with no network dependency; isolated to one swappable function for a future vendor — see Phase 6 doc |
| WhisperX word timestamps | whisper.cpp via Remotion's own installer package | Avoids a heavy Python audio stack (`pyannote`, `torch`) this environment doesn't carry, while producing the same word-level timing shape — see Phase 6 doc |
| `ts-morph`/Babel static analysis | Regex/heuristic extraction, confidence-scored | No repo-specific build/tooling assumptions required for "any repo as input"; upgrade path explicitly left open — see Phase 3 doc |
| Fixed component/folder-based chunking | Feature-wise, stack-specific grouping, no hardcoded folder names | Matches the actual locked requirement ("the unit is the FEATURE") and generalizes across arbitrary repo layouts — see Phase 2 doc |

None of these substitutions are regressions from the original idea —
each one is a scoped, documented decision that keeps the system fully
working end to end inside this specific environment's real constraints,
with an explicit, named upgrade path back toward the original proposal
wherever that upgrade would add real value (richer narration, a
production voice, real word-level timing) without compromising the
accuracy/honesty guarantees the rest of the pipeline depends on.
