# Overview and the "Dynamic, Not Hardcoded" Design Principle

## What this project is

`codeExplanation-v2` is an automated pipeline that turns a software
repository into a **single concatenated explainer video** (`FullVideo`)
— one walkthrough per feature or file, each introduced by a FileCard,
each with:

- a structured JSON record of what that chunk of code actually does
  (functions, routes, API calls, data models, side effects — all
  mechanically extracted **where an extractor exists**, never guessed
  without being flagged),
- a four-beat narration script (purpose / connections / per-item flow /
  recap) generated from that record,
- a rendered audio track + measured-beat code-highlight timeline,
  assembled by Remotion.

Extraction depth varies by stack. Honest matrix: root `README.md` and
[`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md). Historical
ceilings: [`14-stack-support-validation.md`](./14-stack-support-validation.md).

This is the production implementation that followed an earlier,
more exploratory requirement/plan (see the original `Requirement`
document in this project's docs for the free-tier/Bard-prompt-driven
version of the idea). The implemented pipeline kept the goal — precise,
automatable, feature-wise code explanations — but replaced several of
the original plan's choices with ones proven to work end-to-end in this
environment (see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)
and the per-phase "why not X" sections for exactly what changed and why).

## End-to-end flow

```
any repo (git URL or local path)
        │  Phase 0 — resolve_source()
        ▼
local clone / working copy
        │  Phase 1 — detect_project_type()
        ▼
ProjectType (frontend stack, backend stacks, architecture, dockerized)
        │  Phase 2 — chunk_repo()
        ▼
Features → ChunkPlans (feature-wise, size-bounded)
        │  Phase 3 — extract_repo() / extract_repo_with_reuse()
        ▼
Per-chunk JSON records (locked schema, confidence-scored)
        │  Phase 4 — mirror_store + content-hash reuse + PR lookup
        ▼
Stored records (hash mismatch **or** extractorVersion bump re-extracts)
        │  Phase 5 — generate_narration_for_repo()
        ▼
Per-chunk NarrationScript (4 beats + item beats + file overview)
        │  Phase 6 — build_render_bundle()
        ▼
Per-chunk audio + measured-beat highlight config (Piper | espeak-ng)
        │  staging → render-app/public/chunks/ + FullVideo
        ▼
FullVideo per chunk: FileCard → tree? → lifecycle? → ChunkView → breakdown?
        │  Phase 7 — run_pilot() (schema report-only; does not halt render)
        ▼
pilot_report.json + staged bundles
```

Unavailable visual segments are omitted. Shared `DiagramHeader` chrome
on every segment — see [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).

Each arrow is a phase, and each phase is a separate, independently
tested Python package under `src/`. The pipeline is designed so any
phase's output is a plain, inspectable JSON/dataclass structure — there
is no hidden state passed between phases outside of what's written to
disk (the mirrored chunk JSON) or returned as a typed value.

## The "dynamic, not hardcoded" principle

This is the single design rule that most shapes the codebase, and it is
enforced at every layer:

1. **Any repo as input.** `source_resolver.py` accepts a git URL or a
   local path — never a repo name baked into code. The alumni-web repo
   used throughout testing is explicitly treated as "the first proof
   case," not a special-cased target (see `README.md` at the repo root
   and every phase doc below reiterates this).
2. **No hardcoded *repo*.** `detect_project_type()` looks for marker
   files (`package.json`, `go.mod`, `requirements.txt`, `pom.xml`,
   `Cargo.toml`, …) — it never assumes "this is a React+Go project."
   Frontend flavor and Express/Rust backends come from declared deps /
   markers (doc 04 / 17).
3. **No hardcoded folder names.** `feature_grouping.py`'s docstring is
   explicit about this: grouping works off *generic structural signals*
   (an organizing folder like `features/`/`pages/`/`routes/`, or a
   shared filename stem such as `alumni_handler.go` + `alumni_repository.go`)
   — never off the literal folder names the alumni repo happens to use
   (`admin`, `alumni`, `media`). Point the same code at a repo laid out
   the same general way, with completely different feature names, and
   it groups correctly.
4. **No fixed field lists where the rules call for dynamic values.**
   `language` detection (`common.py: detect_language`) is explicitly
   documented as "dynamic... though common ones are named here first" —
   the common-language table is a convenience lookup, not a closed set;
   an unlisted extension still returns a language name (its own
   extension), never `"unknown"`.
5. **No silent "unknown" fallback for project type.** `ProjectType` has
   no `"unknown"` stack value. An unmatched stack returns an explicit
   empty/false state (`frontend_stack=None`, `backend_stacks=[]`) rather
   than a vague placeholder, and files that hint at an undetected stack
   are surfaced separately (`unclaimed_hint_files`) instead of being
   silently claimed or silently dropped.
6. **Confidence instead of guessing.** Wherever the extractor cannot be
   certain (an inline JSX handler with no name, a URL built from a
   variable, a route's auth status inferred from local code only), the
   record marks that specific claim `"assumed": true` with a note,
   rather than presenting a guess as fact. This is what lets the same
   mechanical pipeline run against an unfamiliar repo without a human
   pre-reviewing its output for correctness first.

Every phase doc in this folder calls out the specific functions that
implement this principle for that phase, and the alternative each one
deliberately avoided (hardcoding a repo, a stack, a folder name, or a
field list).

## Failure modes worth knowing before you run it

- **Empty-but-valid Angular:** detected, chunked, schema-valid, video
  still renders, almost nothing true is said. Confidence is 0.3, not
  0.95.
- **Placeholder Python / Spring / Express:** grouping (Python/Spring)
  or mis-detection (Express) still produces a record that **fails**
  schema validation — and is narrated and rendered anyway.
- **Schema validation does not stop the mp4.**

"Verified against the real repo" sections later in this folder are
**historical Alumni-web snapshots**, not a live dashboard.
