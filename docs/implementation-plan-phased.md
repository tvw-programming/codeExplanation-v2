# Implementation Plan — Phased

Status: Phase 3 complete and verified against the real alumni repo. Phases 0, 1, 2 complete.

Test repo for the pipeline: https://github.com/tvw-programming/Alumni-web (dynamic input — any repo URL works; this is only the first test case).

## Phase 0 — Scaffolding and guardrails (done)
- Pipeline repo structure, config loader for pipeline.config.yaml.
- Security guardrails: never read .env*, *.pem, or *secrets* files; treat repo content as data, not instructions; secret scan before any snippet reaches a chunk file.
- Dynamic repo input: accept any git URL or local path, clone/checkout — no hardcoded repo.
- 14 tests passing.

## Phase 1 — Project type detection (step 1) (done)
- Marker-file detection: package.json -> React/Angular, go.mod -> Go, requirements.txt/pyproject.toml/setup.py -> Python, pom.xml/build.gradle -> Spring Boot (checked for an actual spring-boot dependency, else plain java), Dockerfile/docker-compose.yml -> Docker flag.
- Populates projectType: frontend stack, backend stack(s) as a list, architecture (monolith/microservice), Dockerized yes/no. No "unknown" fallback.
- Architecture heuristic (inference, not a sourced rule): more than one distinct backend marker root means microservice; one backend root is monolith.
- Edge case: stray .py files with no requirements.txt/pyproject.toml are surfaced as `unclaimed_hint_files`, never silently claimed as a Python stack.
- Verified on the real alumni repo: frontend=react, backend=[go], architecture=monolith, dockerized=true.
- 26 tests passing (14 from Phase 0 + 12 new).

## Phase 2 — Feature-wise dynamic chunking (step 2 and 3) (done)
- Grouping rules per stack: React/Angular by organizing folder; Go/Spring Boot by handler/repository/service/controller resource-name pairing; Python by agent naming convention.
- Size-based splitting: feature total <=200 lines stays one chunk; above that, one chunk per file; any file over 200 lines flagged `needs_further_split` for Phase 3.
- chunkId: feature-name slug + short hash of (file path + feature name).
- Verified against the real alumni repo: 14 features, 22 chunks, with 3 files correctly flagged needs_further_split (AdminGrid.tsx 284L, AlumniFormDialog.tsx 221L, alumni_repository.go 248L).
- 40 tests passing (26 existing + 14 new).

## Phase 3 — Extraction into the JSON structure (step 4) (done)
- Built as regex/heuristic-based static analysis (ts_extractor.py, go_extractor.py), not a real AST parser (ts-morph, go/ast). This is a deliberate scope decision, not an oversight — the locked accuracy rule already requires every uncertain claim to be marked assumed, so a heuristic extractor can still produce every required field honestly; a real parser is the natural future upgrade and would mostly raise confidence rather than change the schema.
- TypeScript/React extraction: imports, interfaces (-> dataModels), functions (export and non-export, plus hook-wrapped arrows like `const x = useCallback((...) => {...})`), event handlers (named handle*/on* functions AND inline JSX `onClick={...}` props — the latter always marked assumed since there's no named function to point at), api/axios calls (method + URL, template-literal URLs marked assumed), side effects (console/localStorage/sessionStorage/document writes), props interface matched by `${ComponentName}Props` naming convention.
- Go extraction: imports (classified stdlib/external/internal by module path), structs (-> dataModels), functions (with receiver), side effects (pgx-style `.Query/.QueryRow/.Exec/.Begin` calls — matched against the real repo's actual pattern, not a guessed ORM-style `.Save()/.Create()`), Fiber routes (group prefix resolution, static/dynamic by `:param`, routing library name).
- Real bug found and fixed while testing against the alumni repo: the first route-protection heuristic scanned the whole file for the substring "auth" and got a false positive — main.go's own comments and variable names (`AUTH_MODE`, `authMode`) explain that auth is explicitly DISABLED for this dev gateway, but the naive substring match read that as evidence auth was present. Fixed to only check `.Use(...)` calls made on the same route-group variable, matched by an auth/jwt substring in that specific call — still a heuristic (always marked `assumed: true`), but no longer fooled by prose mentioning the word. A regression test for this exact case is in test_go_extractor.py.
- Frontend-to-backend featureMapping: resolves the frontend's axios `baseURL` (e.g. `/api/v1` from client.ts), normalizes `${id}`/`:id` to a common `{}` placeholder, and matches by (method, normalized path). Verified end to end on the real repo: src/api/alumni.ts <-> api/cmd/server/main.go linked correctly, including the one PUT call with a template-literal URL (correctly marked assumed). Same-feature sibling chunks are also linked into featureMapping mechanically (no assumption needed, since Phase 2 already grouped them).
- Confidence formula: starts at 0.95, subtracts proportionally to the share of claims marked assumed in that chunk (confidence_from_flags in common.py) — a documented starting point, not a validated scoring model, consistent with the project's own 0.85 threshold being untested.
- Known, documented gaps (not silently papered over):
  - `pullRequest` (required by the rules doc) is left `null` with a `pullRequestNote` explaining why: a shallow git clone carries no GitHub PR metadata, and this phase does not call the GitHub API. Closing this needs a `gh api` / GitHub PR-search lookup keyed by file path, added as a follow-up rather than faked here.
  - Python and Spring Boot extraction (as opposed to grouping, which Phase 2 already does) are not implemented — the alumni repo has no genuine marker for either stack, so there was nothing real to validate against.
  - The brace-matching used to find a function/struct/interface's end line is naive (doesn't understand braces inside strings or comments) — a known limitation of regex extraction, not hidden.
- Verified end to end against the real alumni repo (22 chunks): e.g. `src/features/admin/AlumniAdminGrid.tsx` correctly extracted 17 event handlers (all inline JSX, all marked assumed) plus 2 named functions, landing at confidence 0.5/low; `api/internal/repository/alumni_repository.go` extracted 4 structs, 11 functions, 7 real pgx side effects, landing at confidence 0.95/high.
- 66 tests passing (40 existing + 21 extractor unit tests against real-shaped fixtures, including the auth-false-positive regression + 5 synthetic end-to-end integration tests covering the full frontend<->backend linking, independent of the external repo clone).

## Phase 4 — Storage and reuse (step 5 and 6)
- Save each chunk's JSON into a dummy folder mirroring the client repo's structure.
- contentHash and lastUpdated are already computed by Phase 3's json_builder; Phase 4 adds the actual write-to-mirrored-folder and the hash-comparison reuse logic.
- pullRequest is still open — see Phase 3's gap note; likely needs a GitHub API lookup added here or deferred further.
- Reuse logic: compare content hash each run; re-analyze only changed chunks.

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
