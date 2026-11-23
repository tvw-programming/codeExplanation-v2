# Phase 7 — Pilot and Validation

Status: done. 12 new tests at original phase completion (10
`schema_check`, 2 `run_pilot`). **Do not treat 147 / 168 as live.**

**Tests (2026-11-23):** `pytest -q` → **334 passed, 4 skipped**. Re-run
locally; pin a new dated count here when it changes.

Phases 0–7 run end-to-end. Multi-stack extractors + visuals are
shipped (`EXTRACTOR_VERSION` 8); fidelity and coverage still vary by
stack (doc 17). Schema validation remains **report-only**
(`run_pilot.py` records `schemaValidation.invalid` then continues).

## What this phase delivers

1. `src/validate/schema_check.py: validate_record()` / `validate_records()`
   — checks every extracted record against the locked required-field
   list.
2. `src/pilot/run_pilot.py: run_pilot(repo_root, output_root, render=True)`
   — the single entry point that runs **every** phase's pipeline over
   one repo end to end and writes one `pilot_report.json` with honest
   numbers, never a bare pass/fail verdict.
3. `scripts/run_backend_pilot.py` (what `./run-local.sh` actually
   calls) — wraps `run_pilot`, then **stages** every successfully
   rendered chunk into `render-app/public/chunks/<chunkId>/` plus
   `render-app/public/chunks/manifest.json` so `FullVideo` can render
   the whole repo. The first chunk is also copied to
   `public/sample-chunk/` for the demo composition.

## Locked rules this phase implements

No new locked rule of its own — this phase's job is to *verify* every
earlier phase's locked rules actually hold on real data, end to end, in
one command. It does **not** halt render on schema failure.

## Key functions and why they were chosen

### `schema_check.py: validate_record(record)`

**What it does:** checks presence of every field the rules doc marks
`required: yes` (`chunkId`, `filePath`, `featureName`, `projectType`,
`language`, `lineRange`, `frameworkOrLibrary`, `featureMapping`,
`confidence`, `confidenceLevel`), plus the Phase 4 storage keys
(`contentHash`, `lastUpdated`, `pullRequest` — checked as **present
keys**, not as non-null values, since `pullRequest: null` is an
accepted, documented state). Also validates `lineRange` is a real
`[start, end]` with `start <= end`, `confidence` is in `[0, 1]`, and
`confidenceLevel` is one of `high`/`medium`/`low`.

**Why check "key exists" rather than "value is non-null" specifically
for `pullRequest`, while every other required field must be non-null:**
this single exception is deliberate and documented — the rules doc
calls `pullRequest` required, but Phase 3/4 established that its
*value* can honestly be `null`. Checking only for the key's presence
enforces "the field was considered and explicitly recorded as unknown."

**Why schema validation stays report-only:** incomplete or
low-confidence records still narrate/render so a pilot can finish; the
report surfaces `schemaValidation.invalid` instead of hiding gaps.
Angular-empty and similar cases remain schema-valid with empty lists —
visuals now go `unavailable` (doc 17) rather than inventing graphs.
Doc 14’s “placeholder-only Python/Spring/Express” claim is obsolete.

### `run_pilot(repo_root, output_root, render=True)` — extraction twice

**What it does:** runs `extract_repo_with_reuse()` once, then
**immediately again** on the same repo/output, specifically to prove
reuse actually triggers on this exact run. After an
`EXTRACTOR_VERSION` bump, the second run reanalyzes until records are
rewritten at the new version.

**Why re-run extraction a second time inside the pilot itself:** a unit
test proves the mechanism in isolation. The pilot's
`reuseProvenCorrect` check is "proven, not just asserted" on this
repo's real paths. Version invalidation is part of that story now.

### Staging for FullVideo

`run_backend_pilot.py` copies each successful render bundle (and source
snippet / audio) to `render-app/public/chunks/<chunkId>/` and writes
`{"chunkIds": [...]}` to `public/chunks/manifest.json`. `./run-local.sh`
then `npx remotion render FullVideo output/video.mp4`. Without this
staging step there is nothing for Remotion to play back. Undocumented
in the original Phase 7 writeup.

### `run_pilot()`'s report shape — honest numbers, not a verdict

The final `pilot_report.json` reports raw counts (`chunkCount`,
`validCount`/`invalidCount`, `narration.withinTargetBand`, per-chunk
render results including `alignmentSource` and `ttsEngine`) — there is
no single `"passed": true/false` field.

Live render rows should show `"alignmentSource": "measured-beats"`,
not `"estimated"`. Treat older reports that say every cue was
`assumed=true` because whisper.cpp was blocked as **historical**.

## Full real-repo pilot results (22 chunks) — historical Alumni-web snapshot

- **Extraction + reuse:** run 1 → `{reused: 0, reanalyzed: 22}`; run 2 →
  `{reused: 22, reanalyzed: 0}` (pre-`extractorVersion` bump).
- **Schema validation:** 22/22 valid, 0 problems (React + Go only —
  that repo has no Angular/Python/Spring/Express chunks).
- **Narration:** 22/22 chunks got a script; **2/22 in the 90–180s
  band** on the **old short templates**. Re-measure after
  function-aware item beats; do not cite 2/22 as current.
- **Render (then):** all 22 used `"estimated"` alignment. **Now** the
  live path writes `"measured-beats"` and prefers Piper over espeak-ng.

## Production voice / timing (updated)

espeak-ng remains the required fallback; Piper is the default when the
voice is cached. Measured-beat alignment is the live timing source.
Commercial TTS is still a one-function swap. `transcribe.mjs` is
**not** the production aligner — leftover / unused by
`build_render_bundle`. Voice quality for a shipped product is still an
open gap (see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)).
