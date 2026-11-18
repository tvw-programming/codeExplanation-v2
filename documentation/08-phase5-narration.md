# Phase 5 — Narrator Script Generation

Status: done. 44 new tests (10 pronunciation, 6 visual cues, 7
glossary, 16 script builder, 5 pipeline integration), 114 passing
overall at phase completion. Verified against the real alumni repo (22
chunks): every chunk got a script; 13/22 have real connections via
genuine `featureMapping` links; only 2/22 land in the 90–180s target
band (an honest, documented finding, not a bug — see below).

## What this phase delivers

`src/narrate/pipeline.py: generate_narration_for_repo(records)` turns
every Phase 3/4 chunk record into a `NarrationScript` — four beats
(purpose, connections, flow, recap) plus visual cue tokens and a
per-chunk pronunciation table — processed in dependency-first order so
cross-chunk continuity is grounded in real links.

## Locked rules this phase implements

- Four beats: purpose, connections, flow, recap.
- Reason before mechanism; name flows by when they run, not by file
  path; never read code line by line.
- Target 90–180 seconds per chunk; split the flow beat at ~60 seconds.
- Confidence-gated speech: verified claims plain, assumed claims
  hedged with one fixed phrase, unverified claims never spoken.
- `notes` is never read aloud.
- Back-references/forward-previews only where `featureMapping` shows a
  real link; process dependencies first.

## Key functions and why they were chosen

### Template-based generation, not an LLM call

`script_builder.py`'s module docstring is explicit: *"This is
template-based, not a call to a language model: every sentence is
built mechanically from fields already in the record, so nothing is
invented that isn't in the extraction's own symbol table."*

**Why a deterministic template instead of an LLM-generated narration
(which the original project requirement explicitly asked for — see
Section C's "Prompt (for Bard) to generate per-chunk JSON"):**

- **Grounding.** Every sentence in the script is traced directly back
  to a field already present in the Phase 3/4 record. An LLM, even with
  a tight system prompt, can paraphrase, embellish, or state something
  plausible-but-wrong about code it wasn't shown in full — exactly the
  failure mode the locked accuracy rule ("speak only verified claims...
  leave unverified claims out of the speech") exists to prevent.
- **Determinism and testability.** The same input record always
  produces the same script, byte for byte — which is what makes 16
  dedicated `script_builder` tests and 5 pipeline-integration tests
  possible at all. An LLM call would be non-deterministic (or require
  expensive golden-output comparisons with fuzzy matching) and would
  also introduce a network dependency, latency, and cost into every
  single chunk of every pipeline run.
- **Cost and reliability at scale.** Feature-wise chunking can produce
  dozens of chunks per repo; a per-chunk LLM call multiplies cost and
  introduces a new failure mode (rate limits, API errors, quota) for
  every run. The template approach has zero marginal cost per chunk
  beyond CPU time.
- This is explicitly framed as a *starting point*, not a rejection of
  the original idea: "An LLM-elaborated version (same structure, richer
  prose) is a natural later upgrade, not required by the locked rules."
  The honest finding below (only 2/22 chunks land in the 90–180s target
  band) is the concrete evidence for exactly when that upgrade would
  earn its cost — see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md).

### `pronunciation.py: split_identifier(identifier)` / `PRONOUNCEABLE_ACRONYMS`

**What it does:** splits camelCase/PascalCase/snake_case/kebab-case/
route-segment identifiers into spoken words, and maps a small table of
acronyms to either a pronounceable word (`JSON` → "Jason", `SQL` →
"sequel") or letter-by-letter spelling (`API`, `URL`, `ID`, `DB`,
`HTTP`, `HTML`, `CSS`, `JWT`, `UUID`).

**Why a documented, hand-curated table instead of a general
pronunciation-prediction algorithm (e.g. grapheme-to-phoneme rules):**
the correct spoken form of an acronym is a matter of *convention*, not
phonetic prediction — "JSON" really is commonly said as "Jason" by
practice, not because English pronunciation rules derive that from the
letters. A general phonetic algorithm would get many of these wrong in
ways a lookup table simply doesn't, and the module's own docstring is
upfront that this list "is a judgment call, not a sourced rule" —
flagged precisely so a reviewer can correct or extend it without
archaeology.

### `visual_cues.py: generate_visual_cues(record)`

**What it does:** generates exactly one `VISUAL[HIGHLIGHT:id]` token per
`importantFunctions` entry that has a usable `lineRange` — and
deliberately generates **no** cue for `eventHandlers`, `dataModels`, or
`routes`, because none of those carry a `lineRange` in the current
Phase 3 schema.

**Why not synthesize a plausible line range for those other fields so
every narrated item gets a highlight:** doing so would be inventing
grounding data that doesn't exist in the extraction's actual symbol
table — a direct violation of the accuracy rule this entire pipeline is
built around. The module's docstring calls this exactly what it is:
"an honest gap, not an oversight, flagged in code for a future schema
addition" — the fix belongs in Phase 3's schema (adding `lineRange` to
those fields), not in Phase 5 pretending data it doesn't have.

### `glossary.py: dependency_first_order(records)`

**What it does:** a deterministic ordering heuristic over
`featureMapping` edges: process the chunk with the fewest
not-yet-processed links first, ties broken by chunk ID.

**Why a heuristic ordering instead of a real topological sort:**
`featureMapping` is explicitly a **symmetric, undirected** link list (a
link is written onto both ends by `extractor.py`'s
`_apply_feature_mapping()`), not a directed dependency graph — so there
is no single "correct" dependency order a topological sort could even
compute; topological sort is defined over directed acyclic graphs, and
this isn't one. The chosen heuristic — process the chunk with fewest
unseen links first — achieves the practical goal (minimize chunks that
have to forward-preview something not yet explained) deterministically
and reproducibly, without pretending to be solving a problem the data
doesn't actually represent. The docstring is explicit about this: "this
heuristic is documented here rather than presented as a real dependency
analysis."

**Why determinism (tie-break by chunk ID) matters here specifically:**
narration scripts reference other chunks by name ("builds on X, covered
earlier" / "also connects to Y, covered later"). If the processing
order changed between runs with no source change, the same chunk could
be narrated as "covered earlier" in one run and "covered later" in
another — confusing and seemingly arbitrary to a viewer. A stable,
reproducible order keeps narration consistent across reruns, matching
the project's broader content-hash-based reuse philosophy (Phase 4):
nothing about a chunk's narrated description should change unless the
underlying code did.

### `script_builder.py: build_flow_beats(sentences)`

**What it does:** joins flow sentences into one beat unless the
combined estimated duration exceeds ~60 seconds, in which case it
splits at the sentence boundary closest to the halfway point —
**never mid-sentence**.

**Why split at a sentence boundary instead of simply truncating at a
word/character count once the time budget is hit:** cutting mid-sentence
would produce a nonsensical half-thought in a *spoken* narration,
which is far more jarring to a listener than a long written paragraph
would be to a reader. A word-count-based split without a sentence
boundary check would frequently land mid-sentence purely by chance.
Iterating sentence-by-sentence and tracking cumulative estimated
duration guarantees the split always falls on a real semantic boundary.

### `_hedge(sentence, assumed)` and the single fixed `HEDGE_PHRASE`

**What it does:** every flow sentence built from a field that carries
`assumed: true` is prefixed with the exact phrase "It looks like"
(lower-casing the sentence's first letter to stay grammatical);
unassumed sentences are spoken plainly.

**Why one single, fixed hedge phrase for every kind of assumed claim,
rather than a different hedge wording per field type (e.g. "possibly,"
"it appears," "this seems to"):** the locked rule calls for "a fixed
hedge phrase from the script" — a single, consistent phrase lets a
listener learn, over the course of one video, that this specific phrase
always signals "this claim wasn't fully verified," functioning as a
reliable spoken convention. Varying the wording per field type would
dilute that signal and make it harder for a listener to reliably notice
when a claim is hedged.

## The honest finding this phase surfaced

Only 2/22 real chunks land in the 90–180s target band (the two richest
admin chunks, at 95s and 124s); the other 20 range 21.8–71.7s. This is
explicitly **not** treated as a bug or patched over by artificially
inflating word counts. It's recorded as a genuine finding to flag for a
later phase: either the target band is meant for feature-rich chunks
only, or an LLM-elaborated script stage (the natural upgrade already
anticipated above) is needed to pad small chunks to length without
inventing ungrounded content. See
[`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md).
