# Implementation Plan — Phased

Status: Phase 4 complete and verified against the real alumni repo. Phases 0, 1, 2, 3 complete.

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

## Phase 5 — Narrator script generation (step 7)
- Four-beat script per chunk (purpose, connections, flow, recap), 90-180s, ~130 wpm budget.
- Identifier pronunciation lookup table; VISUAL[HIGHLIGHT:id] cue tokens tied to line ranges.
- Confidence-gated speech: verified claims spoken, assumed claims hedged, unverified omitted; notes never spoken.
- Continuity glossary keyed by stable chunk IDs; dependency-first ordering.

## Phase 6 — Video rendering
- WhisperX word-level alignment feeding Remotion's interpolate()/useCurrentFrame() for highlight timing.
- Shiki decorations/transformers for code highlighting.
- TTS audio generation, caption burn-in.

## Phase 7 — Pilot and validation
- Run the full pipeline end-to-end on the alumni repo as proof case.
- Checks: JSON validates against the structure rules, reuse skips unchanged chunks, narration stays in the 90-180s band, highlights stay in sync.

## Repo
- Implementation lives in its own repo: https://github.com/tvw-programming/codeExplanation-v2
