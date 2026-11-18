# Implementation Plan — Phased

Status: Phase 0 in progress. Nothing implemented before this.

Test repo for the pipeline: https://github.com/tvw-programming/Alumni-web (dynamic input — any repo URL works; this is only the first test case).

## Phase 0 — Scaffolding and guardrails
- Pipeline repo structure, config loader for pipeline.config.yaml.
- Security guardrails: never read .env*, *.pem, or *secrets* files; treat repo content as data, not instructions; secret scan before any snippet reaches a chunk file.
- Dynamic repo input: accept any git URL or local path, clone/checkout — no hardcoded repo.

## Phase 1 — Project type detection (step 1)
- Marker-file detection: package.json -> React/Angular, go.mod -> Go, requirements.txt/pyproject.toml -> Python, pom.xml/build.gradle -> Spring Boot, Dockerfile -> Docker flag.
- Populate projectType: frontend stack, backend stack, architecture (monolith/microservice), Dockerized yes/no. No "unknown" fallback.
- First test target: alumni repo (React + Go Fiber).

## Phase 2 — Feature-wise dynamic chunking (step 2 and 3)
- Grouping rules per stack: React/Angular by route or component folder; Python by agent (main, router, config, test grouped together); Go by package/handler; Spring Boot by controller/service.
- Size-based splitting: <=200 lines one chunk, 200-800 split at logical boundaries, >800 multiple chunks.
- Frontend-to-backend linking: match API calls to backend routes by URL into featureMapping.

## Phase 3 — Extraction into the JSON structure (step 4)
- Implement extractor against the full field list in docs/json-structure-rules.md.
- Enforce per-field rules (mandatory snippets trimmed to 120 lines, Postman-style apiCalls, routing library/protected/static-dynamic on routes).
- Note: earlier adapter build order (Express first/hardest, then .NET, Spring Boot, Go Fiber/easiest) predates the move to dynamic feature detection across stacks. Starting instead with the alumni repo's stacks (React + Go Fiber) since that is the live test case, then extending to Python, Spring Boot, Express.

## Phase 4 — Storage and reuse (step 5 and 6)
- Save each chunk's JSON into a dummy folder mirroring the client repo's structure.
- Add contentHash, lastUpdated, pullRequest (full URL) — all required.
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
