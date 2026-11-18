# Implementation Plan — Phased

Status: Phase 5 complete and verified against the real alumni repo. Phases 0-4 complete.

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

## Phase 6 — Video rendering
- WhisperX word-level alignment feeding Remotion's interpolate()/useCurrentFrame() for highlight timing.
- Shiki decorations/transformers for code highlighting.
- TTS audio generation, caption burn-in.

## Phase 7 — Pilot and validation
- Run the full pipeline end-to-end on the alumni repo as proof case.
- Checks: JSON validates against the structure rules, reuse skips unchanged chunks, narration stays in the 90-180s band, highlights stay in sync.

## Repo
- Implementation lives in its own repo: https://github.com/tvw-programming/codeExplanation-v2
