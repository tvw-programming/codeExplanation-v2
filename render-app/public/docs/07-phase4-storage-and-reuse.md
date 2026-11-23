# Phase 4 — Storage and Reuse

Status: done, 70 tests passing at phase completion (66 existing + 4
reuse-pipeline tests). Verified against the real alumni repo (22
chunks): run 1 → `{reused: 0, reanalyzed: 22}`; run 2 with no changes →
`{reused: 22, reanalyzed: 0}`.

## What this phase delivers

1. **Mirrored storage** (`mirror_store.py`): each chunk's JSON lives at
   `<output_root>/<filePath>.json`.
2. **Content-hash + extractor-version reuse** (`needs_reanalysis()`):
   skip re-extraction only when the file bytes **and**
   `extractorVersion` match. `EXTRACTOR_VERSION = 19` in
   `mirror_store.py` forces re-analysis when extractors change even if
   source bytes did not. Hash match is no longer enough.
3. **Best-effort PR lookup** (`pull_request_lookup.py`): fills the
   `pullRequest` field via `gh api` when real GitHub access exists.

## Locked rules this phase implements

- Chunk JSON files live in a dummy folder mirroring the client repo's
  own structure.
- `contentHash`, `lastUpdated`, `pullRequest` are required storage
  fields on every stored record.
- A matching content hash **and** matching `extractorVersion` reuses
  the stored record with zero re-analysis; a hash mismatch, missing
  record, missing hash, or older extractor version re-analyzes only
  that one chunk.

## Key functions and why they were chosen

### `mirror_store.py: output_path_for(output_root, file_path)`

**What it does:** `<output_root>/<file_path>.json` — literally the
source repo's own directory structure, with `.json` appended.

**Why mirror the repo's real structure instead of, say, a flat folder
keyed by chunk ID:** a flat `chunks/<chunkId>.json` layout would be
functionally equivalent for lookups, but it would be opaque to a human
or a future tool trying to browse the output — there would be no way to
tell, by looking at the output folder, which source file a given record
came from without opening it. Mirroring the real path makes the output
folder self-describing: `output/src/features/admin/AlumniAdminGrid.tsx.json`
tells you exactly what it's about before you open it. Appending `.json`
(rather than, say, replacing the extension) guarantees it can never
collide with the real source file even if the mirror root and the
source root were ever the same directory.

### `needs_reanalysis(output_root, source_root, file_path)`

**What it does:** returns `(should_reanalyze, current_content_hash)`.
True when there's no stored record, the stored record has no
`contentHash` to compare, the hashes differ, **or**
`stored.extractorVersion` (default 1 if missing) is not
`EXTRACTOR_VERSION`. False only on an exact hash match **and** current
extractor version.

Version bumps so far (see comments in `mirror_store.py`): function
context on `importantFunctions`, handler `lineRange`, then
`fileDescription` for the file card — each of those would otherwise
have reused stale JSON forever on an unchanged file.

**Why a content hash (SHA-256 of raw file bytes) instead of a file
modification timestamp:** a timestamp changes on a `git checkout`, a
file touch, a CI checkout with different mtimes, or simply re-cloning
the same commit — none of which represent an actual content change.
Reusing stale analysis because a timestamp looked "new," or
re-analyzing unnecessarily because a timestamp looked "stale," are both
wrong in ways a content hash simply can't be: identical bytes always
hash identically regardless of when or how they were touched, so the
reuse decision is tied to the one thing that actually matters —
whether the code changed.

**Why "no stored `contentHash`" is also treated as "needs re-analysis"
rather than trusting an old record with a missing hash:** a record with
no hash to compare against provides no basis for a reuse decision —
treating absence-of-evidence as "assume unchanged" would be an
unjustified optimism this project's confidence-first stance explicitly
avoids elsewhere (e.g. the `assumed` flag pattern in Phase 3). Treating
it as "re-analyze" is the conservative, always-correct default.

### `extract/reuse_pipeline.py: extract_repo_with_reuse(root, project_type, output_root, ...)`

**What it does:** wraps Phase 3's per-chunk builders with the reuse
check, then **always** recomputes `featureMapping` over the full chunk
set, even when most individual chunks were reused.

**Why recompute `featureMapping` on every run instead of also caching
it per-chunk:** `featureMapping` depends on the *relationship* between
chunks (which frontend call matches which backend route), not on any
one chunk's own content. If chunk A is reused unchanged but chunk B
(which A links to) was just modified, A's cached `featureMapping` could
now point at a stale or incorrect link. Recomputing this one, cheap,
mechanical pass over the full set every run is far simpler and safer
than trying to invalidate cross-chunk links selectively — and the
module's own docstring calls this out explicitly: "cheap and
mechanical — only the per-file extraction itself is skipped on reuse."

### `storage/pull_request_lookup.py: find_last_pull_request_url(owner, repo, file_path)`

**What it does:** uses `gh api` to find the most recent commit that
touched `file_path`, then the PR (if any) associated with that commit's
SHA. Returns `None` on any failure (no access, no commits, no linked
PR, network error, missing `gh` binary) — never raises, never
fabricates a URL.

**Why best-effort/never-raise instead of propagating a failure up to
the caller:** `pullRequest` is a required *key* in the schema but is
explicitly allowed to be `null` — a shallow clone genuinely has no PR
metadata, and a third-party example repo attached read-only has no API
access to its own PR history. Raising on every one of those entirely
expected conditions would force every caller to wrap this in a
try/except just to keep the pipeline moving; returning `None` and
letting the existing "null + explanatory note" behavior take over
(already in place from Phase 3) is strictly simpler and matches how the
rest of this pipeline treats "genuinely unavailable" information —
honestly absent, never guessed.

**Why `file_path` is now `urllib.parse.quote()`-encoded before being
interpolated into the `gh api` query string:** a path containing `&`,
`#`, `%`, or a space, interpolated raw, would either inject a bogus
extra query parameter or simply produce a malformed/wrong URL — a
correctness bug a code review caught (see
[`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)). URL
-encoding the one untrusted, variable component of the query string is
the standard, minimal fix — it does not change behavior for any file
path that didn't already contain a reserved character.

**Why this module deliberately does NOT force-attach a third-party
example repo (like alumni-web) just to read its PR history:** the
alumni-web repo is read-only in this environment by design — it is "the
first proof case" for dynamic repo input, not something this project
owns or should be mutating access rules for just to exercise one
field. The module's docstring states this directly: the mechanism is
verified against this project's *own* repo instead (where real
API access genuinely exists), which is sufficient to prove the
mechanism works, without overreaching into another project's access
model.

## Verified against the real repo

Historical Alumni-web snapshot: run 1 `{reused: 0, reanalyzed: 22}`;
run 2, no source changes `{reused: 22, reanalyzed: 0}`. The dedicated
test suite still proves reuse in isolation (same `lastUpdated` /
`contentHash` on a no-op second run; exactly one chunk re-extracts
after a single-file edit). After an `EXTRACTOR_VERSION` bump, a
no-source-change second run **will** reanalyze until records are
rewritten at the new version.

The PR-lookup mechanism was separately verified against this project's
own repo, correctly finding the real commit for `README.md` and
correctly returning `None` for it (that commit was pushed directly, not
via a PR — an accurate result, not a bug).
