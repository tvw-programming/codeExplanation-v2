# codeExplanation-v2 — Documentation

Comprehensive, phase-wise and feature-wise documentation of this pipeline:
what it does, how to configure it, what "dynamic" means in this codebase,
the rules each phase is locked to, and — for every important function —
**why that function/approach was chosen instead of the obvious alternative**.

## Doc architecture

| Tree | Role |
|---|---|
| `docs/` | Locked rules (`implementation-plan-phased.md`, `json-structure-rules.md`). If this folder and `docs/` ever disagree, **`docs/` wins**. |
| `documentation/` | **Canonical narrative.** Edit Markdown **here only**. |
| `render-app/public/docs/` | Snapshot served by the MUI docs viewer. It is **not** live-linked to this folder. |
| `documentation/research/` | Working research notes / evidence, not product copy. |

Until the snapshot is refreshed, the viewer keeps serving whatever was
last copied (historically 01–13, missing 14/15, with a stale 13).

### Copy recipe (viewer snapshot)

After editing files in this folder, copy the numbered docs and this
index into the viewer snapshot and refresh the manifest:

```bash
cp documentation/README.md \
   documentation/0{1,2,3,4,5,6,7,8,9}-*.md \
   documentation/1{0,1,2,3,4,5}-*.md \
   render-app/public/docs/
# Then keep render-app/public/docs/manifest.json in sync with the
# table below (groups Start Here / Pipeline Phases / Reference / Roadmap).
```

`npm run build:docs` builds the viewer **app**; it does **not** copy
markdown. Research notes stay in `documentation/research/` and are not
part of the viewer.

## How to read this

| File | Covers |
|---|---|
| [`01-overview-and-dynamic-design.md`](./01-overview-and-dynamic-design.md) | What the pipeline is, end-to-end flow, and the "dynamic, not hardcoded" design principle that runs through every phase |
| [`02-configuration.md`](./02-configuration.md) | `pipeline.config.yaml`, every config field, unused-at-runtime keys, Piper cache |
| [`03-phase0-scaffolding-and-security.md`](./03-phase0-scaffolding-and-security.md) | Phase 0 — config loader, dynamic repo input, security guardrails |
| [`04-phase1-project-type-detection.md`](./04-phase1-project-type-detection.md) | Phase 1 — marker-file stack detection (including the Express hole) |
| [`05-phase2-feature-wise-chunking.md`](./05-phase2-feature-wise-chunking.md) | Phase 2 — feature grouping + size-based chunk splitting |
| [`06-phase3-extraction.md`](./06-phase3-extraction.md) | Phase 3 — regex/heuristic extraction into the locked JSON schema |
| [`07-phase4-storage-and-reuse.md`](./07-phase4-storage-and-reuse.md) | Phase 4 — mirrored storage, content-hash + `extractorVersion` reuse, PR lookup |
| [`08-phase5-narration.md`](./08-phase5-narration.md) | Phase 5 — function-aware narrator scripts, file cards, real pauses |
| [`09-phase6-rendering.md`](./09-phase6-rendering.md) | Phase 6 — Piper/espeak, measured-beat alignment, FullVideo, FileCard, CSS highlights |
| [`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md) | Phase 7 — schema validation + full-repo pilot runner |
| [`11-json-schema-reference.md`](./11-json-schema-reference.md) | The complete per-chunk JSON schema, field by field |
| [`12-function-rationale-index.md`](./12-function-rationale-index.md) | One table: every major function/module, and why it beat the alternative |
| [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md) | Known gaps and what closes them |
| [`14-stack-support-validation.md`](./14-stack-support-validation.md) | Six-stack validation: what actually extracts vs what only detects/chunks |
| [`15-narration-style-guide.md`](./15-narration-style-guide.md) | Voice and tone; identifiers spoken as written |

**Research** (not in the viewer): [`research/README.md`](./research/README.md)
holds the evidence behind doc 14. Do not treat those notes as product copy.

## The one-sentence version

Point the pipeline at **any** git URL or local path → it detects the
stack itself (no hardcoded repo) → groups the code into features →
chunks those features → extracts a structured JSON record per chunk
where an extractor exists (functions, routes, API calls, data models —
grounded in the actual code, nothing invented) → turns each record into
a narrated script (file card + four-beat structure + per-function
item beats) → concatenates every staged chunk into one `FullVideo`
(audio + CSS-highlighted code). Schema validation is **report-only**:
placeholder stacks still get narrated and can still produce an mp4.

Detection is not "any stack." There is no Express/Node backend value;
Angular is detected and chunked but extraction is empty-valid; Python
and Spring are grouped but not extracted. See
[`14-stack-support-validation.md`](./14-stack-support-validation.md).

## Project status

Phases 0–7 **run end-to-end**. Extraction is **not** complete for all
advertised stacks (see the matrix in the root `README.md` and doc 14).

"Verified against the real repo" sections in the phase docs are
**historical Alumni-web snapshots**, not a live dashboard.

**Tests (2026-11-19):** `pytest -q` → **245 passed, 3 skipped**.
Re-run locally rather than treating this as frozen.
