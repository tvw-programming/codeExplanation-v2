# Phase 2 — Feature-Wise Dynamic Chunking

Status: done, 40 tests passing at phase completion. **Historical**
Alumni-web snapshot: 14 features, 22 chunks, 3 files correctly flagged
for further splitting.

`needs_further_split` is still only a flag — nothing consumes it to
perform a statement-level split. Flat files sitting **directly** in an
organizing folder (`features/` / `pages/` / `routes/` / …) are now
claimed (fixed after a silent empty-chunking bug; described in doc 14).

## What this phase delivers

Two steps, implemented as two sub-modules tied together by
`src/chunk/chunker.py: chunk_repo(root, project_type)`:

1. **Feature grouping** (`feature_grouping.py`) — organize files into
   features, the unit this whole pipeline is built around.
2. **Size-based chunk splitting** (`chunk_splitter.py`) — turn each
   feature into one or more `ChunkPlan`s bounded by a line-count budget.

## Locked rules this phase implements

- The unit is the **feature**, not a fixed component or folder.
- Stack-specific grouping: organizing folder for React/Angular,
  resource-name pairing for Go/Spring Boot, agent convention for
  Python.
- Size bands: `<=200` lines → one chunk; `200–800` → one chunk per file;
  `>800` → one chunk per file, oversized ones flagged
  `needs_further_split`.

## Key functions and why they were chosen

### `group_react_or_angular_features(root, src_root, stack)`

**What it does:** if an organizing folder (`features/`, `pages/`,
`routes/`, `views/`, `modules/`) exists, each of its immediate
subdirectories is one feature; **files sitting directly in that
organizing folder** (a flat `src/pages/Home.tsx` layout) are claimed
exactly once as a feature named after the organizing folder; any other
top-level subdirectory of `src_root` is also its own feature; remaining
loose files with no subdirectory are grouped into one feature named
after `src_root` itself.

Older wording of this doc said only *subdirectories* of the organizing
folder became features. That dropped every flat page/route file and
could produce `features: []` on a successful-looking run. The fix lives
in `feature_grouping.py` (regression tests in
`tests/test_feature_grouping.py`).

**Why look for *any* of five conventional organizing-folder names
instead of assuming one specific layout (e.g. always `features/`):**
different React/Angular codebases use different naming conventions for
the same concept — a `pages/` directory in a Next.js-flavored app and a
`features/` directory in a feature-sliced app serve the same structural
role. Checking a short list of the common names, in priority order,
lets the same function correctly group a wider range of real repos
without needing per-repo configuration — directly serving the "nothing
hardcoded to the alumni-web repo's actual folder names" principle
stated in the module's own docstring.

**Why loose top-level files get grouped into one feature (named after
the src root) instead of either being dropped or each becoming its own
single-file feature:** dropping them would silently lose content a
human reviewer would expect to see explained. Making each one its own
feature would fragment what's often tightly related top-level
scaffolding (e.g. `App.tsx`, `index.tsx`) into noise. Grouping them
together under one sensible name is the choice that best matches how a
person describing the codebase out loud would actually talk about
those files.

### `_group_by_resource_pairing(root, backend_root, extension, stack)` (shared by Go and Spring Boot/Java)

**What it does:** within directories that look like resource layers
(`handler`/`controller`/`repository`/`service` and their plurals),
pairs files by a shared resource-name stem (`alumni_handler.go` +
`alumni_repository.go` → one `alumni` feature). Any other directory
becomes its own feature from its direct files.

**Why one shared function for both Go and Spring Boot/Java instead of
two near-duplicate implementations:** the underlying shape of the
problem — "a resource is split across conventional architectural
layers, and the layers need to be reassembled into one feature" — is
identical between a Go Fiber handler/repository pair and a Spring Boot
controller/service pair; only the file extension and the suffix-stripping
regex differ, and both of those are already parameters. Writing one
function instead of two halves the surface area for a grouping bug to
hide in, and any improvement to the pairing logic benefits both stacks
at once.

**Why `RESOURCE_SUFFIX_PATTERN` strips a fixed list of suffixes
(`_handler`, `Handler`, `_repository`, `Repository`, ...) to find the
shared resource name, rather than e.g. a Levenshtein/fuzzy-match between
filenames:** the suffix convention is how these frameworks' own idioms
name files — it's not a coincidence to detect statistically, it's a
known vocabulary to strip. A fuzzy match would be slower, harder to
reason about when it's wrong, and would risk incorrectly pairing two
unrelated resources that merely have similar names.

### `group_python_agent_features(root, backend_root)`

**What it does:** groups a main file, router, config, and test file that
share an "agent" name stem (`payments_agent.py` + `payments_router.py` +
`payments_config.py` + `test_payments_agent.py` → one `payments`
feature). Anything that matches no recognized suffix becomes its own
single-file feature "so nothing is silently dropped."

**Why a suffix-matching convention tailored to an "agent" naming style
instead of reusing the Go/Spring Boot resource-pairing function:**
Python backend codebases in this project's intended domain (per the
locked requirement) are organized around agents, not
handler/repository/controller layers — a materially different
convention that the shared resource-pairing regex wouldn't recognize.
Rather than force-fitting Python into the Go/Spring Boot shape (which
would silently misgroup real Python agent code), this phase keeps a
separate, convention-appropriate grouping function. (Python extraction
itself — Phase 3 — is a documented, honest gap: no real Python repo was
available to validate real extraction against, so only grouping exists
today; see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md).)

**Why unmatched files become their own single-file features instead of
being dropped:** consistent with the "nothing silently dropped" stance
seen throughout this phase — an unrecognized filename pattern is a gap
in the matching heuristic, not evidence the file doesn't matter.

### `plan_chunks_for_feature(feature, root, small_max, medium_max)`

**What it does:** sums the feature's total line count, classifies it
`small`/`medium`/`large`, and either returns one `ChunkPlan` (small) or
one `ChunkPlan` per file (medium/large), flagging any individual file
over `small_max_lines` as `needs_further_split`.

**Why file boundaries are the split unit for medium/large features,
rather than attempting a statement-level split at this phase:** "logical
boundaries" at the statement/function level require a real parser for
the language in question — that belongs to Phase 3's extraction step,
which already has to parse the file's structure to pull out functions
and routes. A file boundary, by contrast, is already a genuine logical
boundary that this phase can decide correctly without any parser at
all. Deferring the finer split to the phase that already needs parsing
avoids duplicating parsing logic, and `needs_further_split` is the
explicit, documented handoff between the two phases — not a silent
TODO.

**The handoff is still unused.** Nothing in Phase 3 (or later) reads
`needs_further_split` to actually split an oversized file. Keep
statement-level split as **roadmap**.

### `make_chunk_id(feature_name, file_path)`

**What it does:** produces a chunk ID like `auth-login-3f9a2c` — a
readable feature-name slug plus an 8-character SHA-256 hash of
`file_path:feature_name`.

**Why a hash of (file path + feature name) instead of, say, a running
counter or a hash of file path alone:** the locked rule requires IDs
"stable across runs unless the file moves." A counter would be unstable
the moment chunk ordering changed between runs (e.g. a new file added
earlier in the walk order) — identical content would get a different
ID on every run, breaking Phase 4's content-hash reuse keying and
Phase 5's glossary continuity. Hashing path+feature name together
(rather than path alone) also means the same file appearing in two
different feature contexts would still get distinguishable IDs, while
remaining fully deterministic and human-skimmable thanks to the
readable slug prefix.

## Verified against the real repo

Historical Alumni-web snapshot: 14 features, 22 chunks, 3 files
correctly flagged `needs_further_split` — from that repo's actual
layout, with no repo-specific grouping code. Not a live dashboard. The
flagged files were **not** further split.
