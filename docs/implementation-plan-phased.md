# Implementation Plan — Phased

> **Status banner.** Phases 0–7 shipped; later work (Piper, file cards,
> FullVideo, measured beats, stack audit) is documented in
> `documentation/`, not in this file's original phase sections. Keep
> this file as a **phase diary**. Test counts in the sections below
> (14 / 26 / 40 / … / 168) are completion snapshots, not the live
> suite — see `documentation/10-phase7-pilot-and-validation.md`.

Status: Phase 7 complete. All 8 planned phases (0-7) done and verified against the real alumni repo.

Test repo for the pipeline: https://github.com/tvw-programming/Alumni-web (dynamic input — any repo URL works; this is only the first test case).

## Phase 0 — Scaffolding and guardrails (done)
- Pipeline repo structure, config loader for pipeline.config.yaml.
- Security guardrails: never read .env*, *.pem, or *secrets* files; treat repo content as data, not instructions; secret scan before any snippet reaches a chunk file.
- Dynamic repo input: accept any git URL or local path, clone/checkout — no hardcoded repo.
- 14 tests passing.

## Phase 1 — Project type detection (step 1) (done)
- Marker-file detection across React/Angular, Go, Python, Spring Boot, Docker.
- projectType has no "unknown" fallback; stray files with no marker file are surfaced, never silently claimed.
- Verified on the real alumni repo: frontend=react, backend=[go], architecture=monolith, dockerized=true.
- 26 tests passing.

## Phase 2 — Feature-wise dynamic chunking (step 2 and 3) (done)
- Stack-specific grouping (organizing folder for React/Angular; resource-name pairing for Go/Spring Boot; agent convention for Python) plus size-based splitting (<=200 one chunk, above that one chunk per file, oversized files flagged needs_further_split).
- Verified against the real alumni repo: 14 features, 22 chunks, 3 files correctly flagged for further splitting.
- 40 tests passing.

## Phase 3 — Extraction into the JSON structure (step 4) (done)
- Regex/heuristic-based static analysis for TypeScript/React and Go (ts_extractor.py, go_extractor.py) — a deliberate scope decision, documented in code, not a real AST parser. Every uncertain claim is marked assumed per the locked accuracy rule.
- Real bug found and fixed via testing against the alumni repo: a route-protection heuristic false-positived on the word "auth" appearing in comments explaining auth was DISABLED. Fixed to check only `.Use()` calls on the matching route-group variable; regression test added.
- Frontend-to-backend featureMapping: resolves axios baseURL, normalizes `${id}`/`:id` params, matches by (method, path). Verified end to end on the real repo.
- Documented gaps: pullRequest was null (closed partially in Phase 4, see below); Python/Spring Boot extraction not implemented (no real repo to validate against); naive brace-matching doesn't understand strings/comments.
- Verified end to end: AlumniAdminGrid.tsx -> 17 handlers + 2 functions, confidence 0.5/low; alumni_repository.go -> 4 structs, 11 functions, 7 real pgx calls, confidence 0.95/high.
- 66 tests passing.

## Phase 4 — Storage and reuse (step 5 and 6) (done)
- mirror_store.py: each chunk's JSON is written to `<output_root>/<filePath>.json` — mirroring the client repo's own directory structure exactly, with `.json` appended so it never collides with the real source file.
- needs_reanalysis() compares the file's current content hash against the stored record's contentHash. No stored record, no stored hash, or a hash mismatch all trigger re-analysis; an exact match reuses the stored record with zero re-extraction.
- reuse_pipeline.py (extract_repo_with_reuse): wraps Phase 3's builders with this check per chunk, then still recomputes featureMapping over the full set every run (cheap and mechanical — only the per-file extraction itself is skipped on reuse).
- Proven, not just asserted: a test suite builds a small repo, runs extraction twice with no changes and confirms 100% reuse with the SAME lastUpdated/contentHash (not just a matching boolean), then changes one file and confirms exactly one chunk is re-extracted while the untouched one's record is byte-identical to before.
- Verified against the real alumni repo (22 chunks): run 1 -> {reused: 0, reanalyzed: 22}; run 2 with no changes -> {reused: 22, reanalyzed: 0}. Output folder structure mirrors the repo exactly (e.g. output/src/features/admin/AlumniAdminGrid.tsx.json).
- pullRequest gap partially closed: pull_request_lookup.py uses `gh api` to walk commit history for a file and find its most recent associated PR, when the pipeline actually has GitHub API access to that repo (an attached, owned repo — not a third-party example repo attached just to read its PR history, which this deliberately did not do for the alumni repo). Verified the underlying mechanism works against our own repo (correctly found the real commit for README.md, correctly returned None since that commit was pushed directly rather than via a PR — not a bug, an accurate result). When no API access or no linked PR exists, the field stays null with its note, exactly as before — never fabricated.
- 70 tests passing (66 existing + 4 new reuse-pipeline tests).

## Phase 5 — Narrator script generation (step 7) (done)
- Template-based, not an LLM call: every sentence in the script is built mechanically from fields already present in the Phase 3/4 extracted record, so nothing is spoken that isn't grounded in the extraction's own symbol table — a deliberate continuation of this project's regex/heuristic stance, and fully deterministic/testable as a result. An LLM-elaborated version (same structure, richer prose) is a natural later upgrade, not required by the locked rules.
- pronunciation.py: splits camelCase/PascalCase/snake_case/kebab-case/route-segment identifiers into spoken words; a small table of pronounceable-vs-spelled-out acronyms (JSON -> "Jason", SQL -> "sequel", API/URL/ID/DB/HTTP/HTML/CSS/JWT/UUID spelled letter by letter) is a documented judgment call, not a sourced rule.
- visual_cues.py: generates one VISUAL[HIGHLIGHT:id] token per importantFunctions entry (the only field in the locked schema that carries a lineRange today). eventHandlers, dataModels, and routes carry no lineRange in the current Phase 3 schema, so no cue is fabricated for them — an honest gap, not an oversight, flagged in code for a future schema addition.
- script_builder.py: four beats (purpose, connections, flow, recap) per chunk. Purpose names the feature and framework before mechanism. Flow sentences are confidence-gated per item: eventHandlers/apiCalls/routes marked assumed=true get the one fixed hedge phrase ("It looks like ..."); importantFunctions are always spoken plainly (taken directly from code, no assumed flag exists for them). The notes field is never read into any beat. Word/duration budget: 130 wpm with a +12.5% pause allowance (within the rule's 10-15% band); the flow beat splits into two at a sentence boundary (never mid-sentence) once estimated duration passes ~60s.
- glossary.py: featureMapping is a symmetric, undirected link list (not a directed dependency graph — see extractor.py), so there is no single correct "dependency order" to recover from it. Resolved with a documented heuristic: process the chunk with the fewest not-yet-seen links first (ties broken by chunkId for determinism), so each chunk's already-registered links become real back-references ("covered earlier") and any links to chunks not yet seen become real forward previews ("covered later") — both always checked against the actual featureMapping, never invented.
- pipeline.py (generate_narration_for_repo): orchestrates dependency-first ordering, builds the glossary as it goes, and produces a script + pronunciation table per chunk.
- 44 new tests (10 pronunciation, 6 visual cues, 7 glossary, 16 script builder, 5 pipeline integration), 114 passing overall.
- Verified against the real alumni repo (22 chunks, no synthetic-only check): every chunk got a script. 13/22 chunks have real connections (not standalone) via genuine featureMapping links. Honest finding: only 2/22 chunks land inside the 90-180s target band on this template-only approach (the two richest admin chunks, at 95s and 124s) — most real chunks in this repo are small (1-3 handlers/functions), so the template naturally produces 20-70s of narration for them. This is a genuine gap to flag for Phase 6/7: either the 90-180s target is meant for feature-rich chunks only, or a richer (LLM-elaborated) script stage is needed to pad small chunks to length without inventing ungrounded content. Not treated as a bug and not patched over by inflating word counts artificially.

## Phase 6 — Video rendering (done)
Python side (src/render/, fully unit-tested, deterministic):
- script_text.py: strips VISUAL[HIGHLIGHT:id] tokens out of the narration before it ever reaches a TTS engine (so it's never spoken aloud), and records how many real spoken words preceded each cue — the anchor used to find that cue's real timestamp once the audio is transcribed.
- tts.py: synthesizes narration audio with espeak-ng, installed and run locally (no network, no API key). This is a real, working TTS engine, not a stub — its voice is simply the basic espeak-ng voice rather than a commercial one; swapping in a paid TTS vendor later is a drop-in replacement of this one function, nothing downstream changes.
- timing.py: aligns each cue to a real transcript word by index; an index inside the transcript's range is an exact match (assumed=false), an index outside it falls back to the nearest word, widens the window by 200ms, and is marked assumed=true — exactly the locked fallback rule.
- estimated_alignment.py: the fallback word-timing source when real transcription can't run (see the real gap below) — spreads words evenly across the real, ffprobe-measured audio duration. Every cue aligned against estimated words is force-marked assumed=true regardless of index match, because the gap here is in the word timings themselves, not just whether an index happened to land in range.
- highlight_config.py: converts timed cues into {lineRange, fromFrame, toFrame, assumed} entries at a given fps — the frame = seconds x fps rule, ready for Remotion's interpolate()/useCurrentFrame().
- render_pipeline.py (build_render_bundle): orchestrates TTS -> (real transcription attempt, else estimated fallback) -> cue alignment -> highlight config -> a bundle.json + narration.wav per chunk. Always records which alignment source was actually used; never claims an estimated run was a real transcription.
- 29 new Python tests (script_text, timing, highlight_config, tts — including one real espeak-ng synthesis, not just a mock — and estimated_alignment), 135 passing overall.

Real gap found and documented, not papered over: the real word-timing path (render-app/scripts/transcribe.mjs, using Remotion's own @remotion/install-whisper-cpp — the locally-installable, no-GPU equivalent of WhisperX's word timestamps) was built and the whisper.cpp binary itself was confirmed to compile and run in this environment; but the ggml model file it needs is only hosted on huggingface.co, which this sandbox's network allowlist blocks (confirmed via direct curl: 403 at the proxy). So every real run in this session used the estimated_alignment.py fallback, honestly labeled `"alignmentSource": "estimated"` in the bundle, with every cue's `assumed` forced true. In an environment where that host is reachable (or with the model file pre-provided), the real-transcription path runs automatically instead — no code change needed.

Remotion side (render-app/, scaffolded with `create-video`):
- CodeExplainerChunk composition: plays the real narration audio, shows the chunk's real source code with the highlighted line range fading in/out exactly at the cue's real frame window (useCurrentFrame() + interpolate()), and a side panel with the narration text and the chunk id/alignment source.
- A second real gap found: `npx remotion render` also needs to download a headless Chromium build, from `remotion.media`, which this sandbox also blocks. Worked around with `--browser-executable` pointing at the Playwright Chromium already installed in this environment (`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`) — a real, working Chromium, just not the one Remotion would normally fetch for itself.
- Verified end to end on one real chunk (alumni-06f407dc / ProfilePage.tsx from the real alumni repo, chosen because it has a genuine VISUAL cue): real Phase 5 narration text -> real espeak-ng audio (36.607s) -> real highlight-config frames -> an actual rendered out/sample-chunk.mp4, confirmed via ffprobe to be a real H264 video + AAC audio file at exactly the same 36.651s duration as the source audio. Generated artifacts (the rendered mp4, the whisper.cpp install, the one sample chunk's audio/source copy) are gitignored, not committed — only the source code that produces them is.

## Phase 7 — Pilot and validation (done)
- src/validate/schema_check.py: validates every extracted record against the locked required-field list in docs/json-structure-rules.md (chunkId, filePath, featureName, projectType, language, lineRange, frameworkOrLibrary, featureMapping, confidence, confidenceLevel, plus the Phase 4 storage keys contentHash/lastUpdated/pullRequest — the last one only required to be present as a key, since it's allowed to be null per the documented gap). Also checks lineRange is a valid [start,end], confidence is in 0-1, confidenceLevel is one of high/medium/low. A Phase 3 placeholder record for an unimplemented stack correctly fails this (by design — the gap is surfaced, not hidden).
- src/pilot/run_pilot.py: the single entry point that runs every phase's pipeline over one repo end to end (detection -> chunking -> extraction+reuse -> schema validation -> narration -> render bundles) and writes one pilot_report.json with honest numbers, not a pass/fail verdict.
- 12 new tests (10 schema_check, 2 run_pilot — the render one running real espeak-ng, skipped only if it's not installed), 147 passing overall.
- Full real-repo pilot run (`python -m src.pilot.run_pilot /path/to/alumni-web /tmp/out`), 22 chunks:
  - Extraction + reuse: run 1 -> {reused: 0, reanalyzed: 22}; run 2 -> {reused: 22, reanalyzed: 0}. Confirms Phase 4's reuse claim holds on a full real pilot run, not just the earlier manual check.
  - Schema validation: 22/22 valid, 0 problems. Every real chunk produced by this pipeline satisfies the locked schema's required fields and basic shape checks.
  - Narration: 22/22 chunks got a script; 2/22 land in the 90-180s target band (95.0s, 124.1s — the two richest admin chunks); the other 20 range from 21.8s to 71.7s. Same honest finding as Phase 5, now confirmed as a full-repo distribution rather than a spot check: this template-only narrator reliably produces shorter narration for small, low-complexity chunks, and the 90-180s target is realistically met only by feature-rich ones.
  - Render: all 22 chunks ran through TTS + alignment + highlight-config generation with zero errors, each producing real synthesized audio (durations from 17.9s to 131.9s) and a highlight config. All 22 used the "estimated" alignment source (the real whisper.cpp path's model download is blocked in this sandbox, per the Phase 6 gap) — 21/22 chunks got at least one visual cue; one chunk (src-acd3f3ae, a file with no importantFunctions carrying a lineRange) correctly got zero cues rather than a fabricated one.
- Decision on TTS/alignment for production, made explicitly rather than left open: espeak-ng + estimated alignment is good enough to prove the full mechanism (every stage runs, every number is honestly labeled, nothing is faked) but is NOT recommended for a real shipped product as-is — the voice is robotic and no cue timing is ever verified (100% of cues come back assumed=true in this environment). For production: swap tts.py's synthesize() for a commercial TTS vendor (one function, already isolated for exactly this), and run render-app/scripts/transcribe.mjs somewhere the huggingface.co model host is reachable (or ship the model file alongside the deployment) so the real whisper.cpp alignment path — already built and tested, just network-blocked here — becomes the actual path taken instead of the fallback.

## Repo
- Implementation lives in its own repo: https://github.com/tvw-programming/codeExplanation-v2
- Phase 6 added a second, Node/Remotion sub-project at `render-app/` inside that same repo.

## Remaining known gaps (carried forward, not silently dropped)
- Python and Spring Boot extraction are not implemented (grouping exists; no real repo of either stack was available to validate real extraction against).
- The real whisper.cpp alignment path and Remotion's own Chromium download both work correctly but are network-blocked in this specific sandbox; neither has been exercised end to end with real (non-estimated) data in this session.
- The narrator's 90-180s target band is reliably met only for feature-rich chunks with this template-only script generator; a richer (LLM-elaborated) script stage would be needed to close that gap for small chunks without inventing ungrounded content.

## After Phase 7 (not rewritten into the diary above)

Documented in `documentation/`, not back-ported into the original phase sections:

- Piper TTS preferred, espeak-ng fallback; `ttsEngine` on the bundle.
- File cards (`file_overview.py`, `FileCard.tsx`) before each walkthrough.
- `FullVideo` concatenates every staged chunk (`public/chunks/manifest.json`).
- Measured-beat alignment replaced whisper.cpp / estimated as the live path.
- Function-aware narration (`function_context.py`, `function_narration.py`).
- `EXTRACTOR_VERSION` reuse invalidation; handler `lineRange`; empty-extraction confidence 0.3; flat organizing-folder files; nested Fiber prefixes composed in-file.
- Six-stack audit: `documentation/14-stack-support-validation.md`.
- Narration style guide: `documentation/15-narration-style-guide.md`.
