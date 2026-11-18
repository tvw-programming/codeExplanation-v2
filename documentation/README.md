# codeExplanation-v2 — Documentation

Comprehensive, phase-wise and feature-wise documentation of this pipeline:
what it does, how to configure it, what "dynamic" means in this codebase,
the rules each phase is locked to, and — for every important function —
**why that function/approach was chosen instead of the obvious alternative**.

This folder is generated documentation, kept separate from `docs/`
(`docs/implementation-plan-phased.md` and `docs/json-structure-rules.md`),
which are the two **source-of-truth** rule documents this pipeline was
built against. Everything here is a synthesis and expansion of those two
files plus the code's own docstrings — nothing here overrides them; if
this folder and `docs/` ever disagree, `docs/` wins.

## How to read this

| File | Covers |
|---|---|
| [`01-overview-and-dynamic-design.md`](./01-overview-and-dynamic-design.md) | What the pipeline is, end-to-end flow, and the "dynamic, not hardcoded" design principle that runs through every phase |
| [`02-configuration.md`](./02-configuration.md) | `pipeline.config.yaml`, every config field, how to point the pipeline at a different repo |
| [`03-phase0-scaffolding-and-security.md`](./03-phase0-scaffolding-and-security.md) | Phase 0 — config loader, dynamic repo input, security guardrails |
| [`04-phase1-project-type-detection.md`](./04-phase1-project-type-detection.md) | Phase 1 — marker-file stack detection |
| [`05-phase2-feature-wise-chunking.md`](./05-phase2-feature-wise-chunking.md) | Phase 2 — feature grouping + size-based chunk splitting |
| [`06-phase3-extraction.md`](./06-phase3-extraction.md) | Phase 3 — regex/heuristic extraction into the locked JSON schema |
| [`07-phase4-storage-and-reuse.md`](./07-phase4-storage-and-reuse.md) | Phase 4 — mirrored storage, content-hash reuse, PR lookup |
| [`08-phase5-narration.md`](./08-phase5-narration.md) | Phase 5 — template-based narrator script generation |
| [`09-phase6-rendering.md`](./09-phase6-rendering.md) | Phase 6 — TTS, alignment, highlight frames, Remotion |
| [`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md) | Phase 7 — schema validation + full-repo pilot runner |
| [`11-json-schema-reference.md`](./11-json-schema-reference.md) | The complete per-chunk JSON schema, field by field |
| [`12-function-rationale-index.md`](./12-function-rationale-index.md) | One table: every major function/module, and why it beat the alternative |
| [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md) | Every honestly-documented gap, and what closes it |

## The one-sentence version

Point the pipeline at **any** git URL or local path → it detects the
stack itself (no hardcoded repo, no hardcoded framework) → groups the
code into features → chunks those features → extracts a structured JSON
record per chunk (functions, routes, API calls, data models — all
grounded in the actual code, nothing invented) → turns each record into
a narrated script → turns each script into a rendered video chunk
(audio + highlighted code), with every step's output validated and
reused across runs via content hashing.

## Project status at the time of writing

Phases 0–7 are complete and have all been verified against a real third
-party repository (`https://github.com/tvw-programming/Alumni-web`, React
+ Go Fiber), not just synthetic fixtures — see each phase doc's
"Verified against the real repo" section. 168 automated tests pass as of
the latest commit on `main`.
