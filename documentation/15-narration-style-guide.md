# Narration Style Guide

How these videos speak. This is the voice-and-tone counterpart to the
structural rules in `08-phase5-narration.md`: that document says what
the narrator must say, this one says how it should sound and why.

Most of what follows is already enforced in code
(`src/narrate/script_builder.py`, `function_narration.py`). Where that
is the case it is marked **[enforced]** with the mechanism, so a reader
can tell a rule that holds automatically from a rule that depends on
whoever writes the next template. Rules that are not yet enforced are
marked **[by convention]** — these are the ones to check in review.

---

## 1. The voice

**A competent colleague walking you through unfamiliar code.** Not a
lecturer, not a marketing video, not a documentation generator reading
field names aloud.

Concretely, that means:

| | |
|---|---|
| **Register** | Plain professional. Contractions are fine. No slang, no jokes, no exclamation marks. |
| **Person** | Third person about the code (`it takes`, `this runs`), never "we" or "you" — the narrator is not a participant and is not instructing anyone. |
| **Tense** | Present. Code does things now: "it raises an error", not "it will raise" or "it raised". **[enforced]** — a locked rule in `08-phase5-narration.md`. |
| **Sentence length** | One idea per sentence. **[enforced]** |
| **Pace** | 130 words per minute, plus a 12.5% pause allowance. **[enforced]** — `WORDS_PER_MINUTE`, `PAUSE_FACTOR`. |

The test for register: would a senior engineer say this out loud to a
new joiner looking at the screen with them? "The handleSubmit handler
responds to a user action event" passes. "Let's dive into this awesome
component!" does not.

## 2. Confidence is a speech act

This is the rule the whole project turns on, and it is the one most
easily broken by someone writing a new template.

**A sentence's grammar must match how well the fact is known.** There
are exactly three levels, and no fourth.

| Certainty | How it is spoken | Example |
|---|---|---|
| **Verified** — read directly from the source | Stated plainly, no hedge | "The ProfilePage function runs next." |
| **Assumed but grounded** — inferred from real evidence that could be wrong | One fixed hedge phrase, always the same words | "**It looks like** the inline_onClose_L50 handler responds to a user action event." |
| **Not grounded** | **Not spoken at all** | — |

**[enforced]** — `HEDGE_PHRASE = "It looks like"` and `_hedge()` in
`script_builder.py`. The phrase is deliberately fixed: varying it
("perhaps", "it seems", "possibly") would make the hedge sound like
prose style rather than a signal, and a viewer could no longer tell
hedged claims from plain ones by ear.

Two corollaries that are easy to get wrong:

- **Never narrate around a gap.** If the extractor found no callers,
  say so — "Nothing else in this chunk calls it and it is not
  exported" — rather than skipping the subject and leaving the viewer
  to assume it has callers.
- **A doc comment is attributed, not asserted.** It is the author's
  claim about the code, which the extractor has not verified against
  the code. So: "Its own documentation says: …", never the comment's
  text delivered as fact. **[enforced]** —
  `build_function_narration()`.

## 3. What is never spoken

- **The `notes` field.** It is written for a reviewer reading JSON, not
  for a listener. **[enforced]**
- **Anything absent from the extraction's symbol table.** Narration is
  template-built from record fields, so this holds structurally rather
  than by discipline. **[enforced]** — see the module docstring in
  `script_builder.py`.
- **Secrets.** Doc comments pass through `redact_secrets()` before they
  can be spoken, because a comment can carry a credential as easily as
  a line of code can, and here it would be read aloud. **[enforced]** —
  `function_context.py`.
- **Markup.** Backticks, asterisks and embedded HTML in a doc comment
  are stripped before TTS, or the narrator reads punctuation aloud.
  **[enforced]** — `speakable()`.
- **Filler.** No "as we can see", "let's take a look", "now moving on".
  There is no audience rapport to build.
- **Repeated boilerplate.** A line that would appear on nearly every
  function ("this function is undocumented") is noise, not information.
  It was removed for exactly this reason. **[by convention]**

## 4. Structure of a section

Four beats, in this order. **[enforced]** — `build_beats()`.

1. **Purpose** — what this file is for, before any mechanism.
2. **Connections** — how it relates to chunks covered elsewhere, or
   plainly that it stands alone.
3. **Flow** — the items in turn: what each does, who calls it, why it
   matters. Split in two if it would run past ~60 seconds. **[enforced]**
4. **Recap** — what was covered, and explicitly what was not.

Purpose before mechanism is the load-bearing one. A viewer who does not
yet know what a file is for cannot absorb how it works.

## 5. Pacing and silence

Silence is part of the narration, not an absence of it.

- Every item beat is followed by **1–3 seconds of real silence**,
  scaled by how many lines there are to read. **[enforced]** —
  `pause_after_ms()`, rendered as actual samples by
  `audio_assembly.py`.
- The viewer is reading code while listening. Narration that runs
  continuously gives them no moment to look at the thing being
  described.
- A section runs **90–180 seconds** as a target. **[enforced]** —
  `TARGET_MIN_SECONDS` / `TARGET_MAX_SECONDS`.

## 6. Naming things

- **Identifiers are spoken as written.** `handleSubmit` is
  "handleSubmit", not "handle submit". The viewer is reading the name
  on screen and needs to match what they hear to what they see.
- **Paths are spoken in full the first time** and may be shortened
  afterwards.
- **Never invent a friendly name** for a symbol. If a Fiber v3 inline
  handler is literally anonymous, it is not given a helpful label —
  naming a thing the viewer cannot find on screen is worse than saying
  it is unnamed.

## 7. Writing a new template

Before adding one, check it against these:

1. Could this sentence be false for some input? If yes, it needs the
   hedge or it needs to not exist.
2. Does every noun in it come from a record field?
3. Would it read as filler on the twentieth file in a row?
4. Does it name something the viewer can see on screen right now?
5. Does it survive TTS — no markup, no symbols read aloud, no
   sentence so long the listener loses the subject?

If a template cannot pass (1), the honest output is to say nothing
about that subject. **Refusing to narrate beats guessing** — a video
that omits the route table is recoverable; one that states a URL which
does not exist in the running app is not, because the viewer has no way
to tell.
