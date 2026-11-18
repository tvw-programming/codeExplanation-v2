# Phase 7 — Pilot and Validation

Status: done. 12 new tests (10 schema_check, 2 run_pilot — the render
one running real espeak-ng, skipped only if it's not installed), 147
passing overall at phase completion (now 168, after the post-code-review
security fixes — see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)).

## What this phase delivers

1. `src/validate/schema_check.py: validate_record()` / `validate_records()`
   — checks every extracted record against the locked required-field
   list.
2. `src/pilot/run_pilot.py: run_pilot(repo_root, output_root, render=True)`
   — the single entry point that runs **every** phase's pipeline over
   one repo end to end and writes one `pilot_report.json` with honest
   numbers, never a bare pass/fail verdict.

## Locked rules this phase implements

No new locked rule of its own — this phase's job is to *verify* every
earlier phase's locked rules actually hold on real data, end to end, in
one command.

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
this single exception is deliberate and documented, not an oversight —
the rules doc calls `pullRequest` required, but Phase 3/4 established
(for entirely legitimate reasons: a shallow clone has no PR metadata, a
third-party repo has no API access) that its *value* can honestly be
`null`. A validator that demanded non-null here would force every
caller to either fabricate a PR URL or fail validation for a state the
pipeline has already decided is acceptable — neither of which is
correct. Checking only for the key's presence enforces "the field was
considered and explicitly recorded as unknown," which is exactly what
this pipeline's honesty stance calls for.

**Why a Phase-3 placeholder record for an unimplemented stack (Python/
Spring Boot extraction) is allowed to legitimately *fail* this
validator, rather than being special-cased to pass:** the module's own
docstring states this is "by design — the gap is surfaced, not
hidden." Special-casing the placeholder to pass validation would hide
a real, known limitation behind a green checkmark; letting it fail
honestly is what makes the Phase 7 pilot report's "problems" list a
trustworthy inventory of real gaps rather than a sanitized summary.

### `run_pilot(repo_root, output_root, render=True)` — running extraction *twice* inside one pilot run

**What it does:** runs `extract_repo_with_reuse()` once, then
**immediately again** on the same repo/output, specifically to prove
reuse actually triggers on this exact run, not just that the mechanism
exists in isolated unit tests.

**Why re-run extraction a second time inside the pilot itself, instead
of trusting Phase 4's own unit tests to have already proven reuse
works:** a unit test proves the mechanism is *correct in isolation*,
against a small synthetic fixture. It does not prove reuse actually
*happens* for a specific real repo's specific real file layout and
content-hash values on a from-scratch run — there could be a
real-world edge case (e.g. a path-normalization mismatch between what
the chunker produces and what the mirror store expects) that a
synthetic test wouldn't catch. The pilot's own `reuseProvenCorrect`
check (`reuse_check_stats["reused"] == reuse_check_stats["total"]`) is
exactly the kind of "proven, not just asserted" verification this
project applies consistently — the same standard used for the Phase 4
reuse claim and the Phase 6 real-audio render.

### `run_pilot()`'s report shape — honest numbers, not a verdict

**What it does:** the final `pilot_report.json` reports raw counts
(`chunkCount`, `validCount`/`invalidCount`, `narration.withinTargetBand`,
per-chunk render results including `alignmentSource` and `allCuesAssumed`)
— there is no single `"passed": true/false` field anywhere in the
report.

**Why report numbers instead of a verdict:** a single pass/fail boolean
would have to make an arbitrary judgment call about *which* gaps are
acceptable (is 2/22 chunks in the target narration band a "pass" or a
"fail"? Is an unimplemented Python extractor a "fail" for the whole
pilot, or an expected, out-of-scope gap?). Reporting the actual numbers
and letting a human (or a later automated threshold, if one is ever
added) interpret them is more honest and more useful — it's also
exactly how every other phase in this project reports its own findings
(e.g. Phase 5's narration-length distribution, Phase 6's per-chunk
alignment sources), so Phase 7's report format is consistent with the
project's established voice rather than introducing a new, different
kind of output at the very end.

## Full real-repo pilot results (22 chunks)

- **Extraction + reuse:** run 1 → `{reused: 0, reanalyzed: 22}`; run 2 →
  `{reused: 22, reanalyzed: 0}`.
- **Schema validation:** 22/22 valid, 0 problems.
- **Narration:** 22/22 chunks got a script; 2/22 land in the 90–180s
  target band (95.0s, 124.1s); the other 20 range 21.8s–71.7s.
- **Render:** all 22 chunks ran through TTS + alignment +
  highlight-config generation with zero errors; durations 17.9s–131.9s;
  all 22 used the `"estimated"` alignment source (the real whisper.cpp
  path's model download is blocked in this sandbox); 21/22 chunks got
  at least one visual cue — the one exception (a file with no
  `importantFunctions` carrying a `lineRange`) correctly got **zero**
  cues rather than a fabricated one.

## The explicit production decision this phase states

espeak-ng + estimated alignment is good enough to **prove the full
mechanism** (every stage runs, every number is honestly labeled,
nothing is faked) but is explicitly **NOT recommended for a real
shipped product as-is** — the voice is robotic and no cue timing is
ever verified in this environment (100% of cues come back
`assumed=true`). The stated production path: swap `tts.py`'s
`synthesize()` for a commercial TTS vendor (already isolated to one
function for exactly this reason), and run
`render-app/scripts/transcribe.mjs` somewhere the `huggingface.co`
model host is reachable (or ship the model file with the deployment)
so the real whisper.cpp alignment path — already built and tested,
just network-blocked here — becomes the path actually taken.
