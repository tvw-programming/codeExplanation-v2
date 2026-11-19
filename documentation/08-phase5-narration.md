# Phase 5 — Narrator Script Generation

Status: done, then extended. The live narrator is richer than the
original four concatenated beats whose flow sentences were "The X
function runs next." Historical Alumni-web counts (22 scripts, 13/22
with `featureMapping` links, **2/22 in the 90–180s band**) are a
snapshot of those **old short templates**. Re-measure; do not cite 2/22
as current.

Voice and tone: [`15-narration-style-guide.md`](./15-narration-style-guide.md).
When 08 and 15 disagree on identifiers, **15 wins and matches runtime**:
identifiers are spoken **as written**.

## What this phase delivers

`src/narrate/pipeline.py: generate_narration_for_repo(records)` turns
every Phase 3/4 chunk record into a `NarrationScript` processed in
dependency-first order.

Live structure (`script_builder.py: build_beats` + `build_item_beats`):

1. **Purpose** beat — what this file/feature is for.
2. **Connections** beat — real `featureMapping` back-refs / forward
   previews, or "stands on its own."
3. **Item beats** — one beat per important function, route, event
   handler, and API call. Function text comes from
   `function_narration.py` (doc comments, callers/callees, body facts,
   `pause_after_ms`). This is what the viewer **hears**, not a single
   "The X function runs next" sentence per symbol.
4. **Recap** beat — what was covered, and what was not.

Each item beat can carry a `cue_id` (highlight) and a real pause.
Pauses are not estimated: Phase 6 pads the beat WAV with silence
(`audio_assembly.py`).

Separately, `file_overview.py` builds a **file card** payload
(callers/callees, layer, risks, `unavailable` reasons). Phase 6 speaks
it over `FileCard.tsx` before the walkthrough. That card is not
mentioned in the original four-beat rule set; it is extra, grounded
intro copy from `fileDescription` and the record.

A per-chunk **pronunciation table is still built**
(`pronunciation.py`) and **never applied to TTS**. Runtime matches
doc 15 (spoken as written), not the camelCase-splitting rule below.

## Locked rules this phase implements

- Four beats: purpose, connections, flow (now a sequence of item
  beats), recap.
- Reason before mechanism; name flows by when they run, not by file
  path; never read code line by line.
- Target 90–180 seconds per chunk; split the flow beat at ~60 seconds.
  **Keep as a target; it is unmet for small files.**
- Confidence-gated speech: verified claims plain, assumed claims
  hedged with one fixed phrase (`"It looks like"`), unverified claims
  never spoken.
- `notes` is never read aloud.
- Back-references/forward-previews only where `featureMapping` shows a
  real link; process dependencies first.

## Key functions and why they were chosen

### Template-based generation, not an LLM call

`script_builder.py`'s module docstring is explicit: every sentence is
built mechanically from fields already in the record.

**Why a deterministic template instead of an LLM-generated narration:**

- **Grounding.** Every sentence traces back to a Phase 3/4 field. An
  LLM can paraphrase or state something plausible-but-wrong.
- **Determinism and testability.** Same input → same script.
- **Cost and reliability at scale.** Dozens of chunks; no per-chunk
  API cost or quota failure mode.

An LLM-elaborated version (same structure, richer prose) remains a
**roadmap** upgrade — the `llm:` config block is unused. The old 2/22
in-band finding is historical evidence for when that upgrade would
earn its cost, not a live dashboard. See
[`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md).

### `function_narration.py` + `build_item_beats`

**What it does:** for each `importantFunctions` entry, speak a short
summary then a longer grounded description: attributed doc comment
("Its own documentation says: …"), callers / callees / exported,
errors raised, hooks, in-range API calls and side effects. `pause_after_ms`
scales 1–3 seconds of real silence by `lineCount` so the viewer can
read the highlighted body.

**Why not "The X function runs next" for every symbol:** that sentence
names the function and nothing else. The extra fields from
`function_context.py` (`description`, `exported`, `calledBy`, `calls`,
`raisesError`, `reactHooks`, …) exist so the narrator can describe a
function instead of only naming it. Empty facts are omitted, not
invented.

Routes, event handlers, and API calls still use short templates, with
the same hedge rule. Inline JSX handlers add one extra sentence that
they are bound inline.

### `file_overview.py`

**What it does:** a structured card for each file: purpose (from
`fileDescription` / header comment), layer, callers, callees, routes,
side effects, risks, and an `unavailable` map explaining missing
fields instead of showing empty rows.

**Why a card before the walkthrough:** `FullVideo` concatenates every
chunk. Without a boundary, the last line of one file cuts to the first
line of the next. The card is the visible chapter title.

### `pronunciation.py` — built, not spoken

**What it does:** splits camelCase/PascalCase/snake_case/kebab-case
identifiers and maps a small acronym table (`JSON` → "Jason", `API`
letter-by-letter, …).

**What actually reaches TTS:** the identifier **as written**
(`handleSubmit`, not "handle submit"). Doc 15 is the live rule. The
table is kept for a **future** TTS pass (SSML is not implemented). Do
not document camelCase splitting as what the viewer hears.

### `visual_cues.py: generate_visual_cues(record)`

**What it does:** one `VISUAL[HIGHLIGHT:id]` token per entry in
`CUE_SOURCE_FIELDS` (`importantFunctions`, `eventHandlers`, `routes`)
that has a usable `lineRange`. `eventHandlers` **do** carry
`lineRange` now (`json_builder.py`, single-line range at the bind
site), so handler sentences get a highlight. `dataModels` still do
not; no cue is fabricated for them.

**Why not invent a line range:** same accuracy rule as extraction.

### `glossary.py: dependency_first_order(records)`

Unchanged: `featureMapping` is a symmetric undirected link list, so
this is "fewest unseen links first," ties broken by chunk ID — not a
topological sort. Determinism keeps "covered earlier" / "covered
later" stable across reruns.

### `build_flow_beats` / item-beat splitting

Flow still splits near ~60s at a **sentence boundary**. Item beats
are the spoken flow; `build_flow_sentences` remains as the older
concatenated form used by estimates and tests.

### `_hedge` and `HEDGE_PHRASE`

One fixed phrase, "It looks like," for every assumed claim.

## Length target

90–180s remains the locked target (`TARGET_MIN_SECONDS` /
`TARGET_MAX_SECONDS`). Function-aware item beats plus real pauses
make small files longer than the original templates, but the band is
still **unmet** for many small files and is not padded with ungrounded
content. Treat Alumni-web 2/22 as historical.
