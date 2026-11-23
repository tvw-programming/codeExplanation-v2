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

### Copy recipe (viewer snapshot)

```bash
cp documentation/README.md \
   documentation/0{1,2,3,4,5,6,7,8,9}-*.md \
   documentation/1{0,1,2,3,4,5,7,8,9}-*.md \
   documentation/20-*.md \
   render-app/public/docs/
# Keep render-app/public/docs/manifest.json in sync with the table below.
```

`npm run build:docs` builds the viewer **app**; it does **not** copy
markdown. Research notes stay in `documentation/research/` and are not
part of the viewer.

## How to read this

| File | Covers |
|---|---|
| [`01-overview-and-dynamic-design.md`](./01-overview-and-dynamic-design.md) | What the pipeline is, end-to-end flow, dynamic design principle |
| [`02-configuration.md`](./02-configuration.md) | `pipeline.config.yaml`, config fields, Piper cache |
| [`03-phase0-scaffolding-and-security.md`](./03-phase0-scaffolding-and-security.md) | Phase 0 — config, dynamic repo input, security |
| [`04-phase1-project-type-detection.md`](./04-phase1-project-type-detection.md) | Phase 1 — marker-file stack detection |
| [`05-phase2-feature-wise-chunking.md`](./05-phase2-feature-wise-chunking.md) | Phase 2 — feature grouping + size-based splitting |
| [`06-phase3-extraction.md`](./06-phase3-extraction.md) | Phase 3 — extractors into the locked JSON schema |
| [`07-phase4-storage-and-reuse.md`](./07-phase4-storage-and-reuse.md) | Phase 4 — mirrored storage, hash + `extractorVersion` |
| [`08-phase5-narration.md`](./08-phase5-narration.md) | Phase 5 — narrator scripts, file cards, pauses |
| [`09-phase6-rendering.md`](./09-phase6-rendering.md) | Phase 6 — Piper/espeak, measured-beat, FullVideo, DiagramHeader |
| [`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md) | Phase 7 — schema validation + pilot runner |
| [`11-json-schema-reference.md`](./11-json-schema-reference.md) | Per-chunk JSON schema, including visual envelope |
| [`12-function-rationale-index.md`](./12-function-rationale-index.md) | Major functions and alternatives avoided |
| [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md) | Known gaps and what closes them |
| [`14-stack-support-validation.md`](./14-stack-support-validation.md) | Historical six-stack audit (read banner first) |
| [`15-narration-style-guide.md`](./15-narration-style-guide.md) | Voice and tone; identifiers spoken as written |
| [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md) | FullVideo order, honesty skips, brand chrome |
| [`18-repo-viewer.md`](./18-repo-viewer.md) | The React repo viewer (`frontend/`) — per-stack file trees, seeking to a file's moment in its stack video |
| [`19-mermaid-architecture-docs.md`](./19-mermaid-architecture-docs.md) | Mermaid docs/chat twin of Remotion visuals; selection + placement |
| [`20-mermaid-stack-matrix.md`](./20-mermaid-stack-matrix.md) | Per-stack Mermaid diagram kinds, honesty skips, caps |

**Research** (not in the viewer): [`research/README.md`](./research/README.md).

## The one-sentence version

Point the pipeline at **any** git URL or local path → detect stack →
feature-wise chunks → extract JSON (`EXTRACTOR_VERSION` 8) → narrate →
`FullVideo` (FileCard → optional tree/lifecycle → ChunkView → optional
breakdown) with brand-tinted `DiagramHeader`. Unavailable visuals are
skipped, not invented. See [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).

## Project status

Phases 0–7 run end-to-end. Multi-stack extractors + visuals shipped
through PR #5; DiagramHeader / center-packed trees in PR #6. Regex and
cross-file limits remain — doc 14 banner + doc 13.

**Tests (2026-11-19):** `pytest -q` → **290 passed, 3 skipped**.
Re-run locally rather than treating this as frozen.
