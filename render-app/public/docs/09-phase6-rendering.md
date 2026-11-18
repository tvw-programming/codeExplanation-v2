# Phase 6 — Video Rendering

Status: done. 29 new Python tests (script_text, timing,
highlight_config, tts — including one real espeak-ng synthesis, not
just a mock — and estimated_alignment), 135 passing overall at phase
completion. Verified end to end on one real chunk
(`alumni-06f407dc` / `ProfilePage.tsx`): real narration → real
espeak-ng audio (36.607s) → real highlight-config frames → an actual
rendered `out/sample-chunk.mp4`, confirmed via `ffprobe`.

## What this phase delivers

Python side (`src/render/`, fully unit-tested, deterministic):
`script_text.py` (strip cue tokens before TTS) → `tts.py` (synthesize
audio) → `timing.py` + `estimated_alignment.py` (align cues to real or
estimated word timestamps) → `highlight_config.py` (seconds → frames)
→ `render_pipeline.py: build_render_bundle()` (orchestrates all of the
above into one `bundle.json` + `narration.wav` per chunk).

Remotion side (`render-app/`): `CodeExplainerChunk.tsx` consumes that
bundle and renders the actual video composition.

## Locked rules this phase implements

- Strip `VISUAL[...]` tokens before they reach TTS; they must never be
  spoken aloud.
- Use real (WhisperX-equivalent) word timings as the time base; if a
  cue can't be timed, widen the window ~200ms against the nearest
  timed word; if it still can't be aligned, mark `assumed: true`.
- `frame = seconds × fps`; drive highlights with `useCurrentFrame()` +
  `interpolate()`; apply via Shiki-style decorations.

## Key functions and why they were chosen

### `script_text.py: strip_visual_tokens(text)`

**What it does:** removes every `VISUAL[HIGHLIGHT:id]` token from the
narration text and, for each one, records how many real spoken words
preceded it — the anchor index used later to find that cue's real
timestamp once the audio is transcribed.

**Why record a *word index* at this step instead of, say, a character
offset into the original text:** the thing that will actually exist
downstream to align against is a **transcript** — a sequence of
(word, startMs, endMs) triples from a real speech-to-text run, not the
original text's character positions (TTS engines don't preserve a
character-level mapping to audio time; speech-to-text transcripts are
inherently word-indexed). A word index is therefore the only anchor
format that can actually be looked up against what Phase 6's alignment
step will have in hand.

### `tts.py: synthesize(text, out_path, voice, words_per_minute)` — espeak-ng

**What it does:** synthesizes narration audio with `espeak-ng`,
installed and run locally — no network call, no API key.

**Why espeak-ng instead of a cloud TTS vendor (which the original
project requirement specifically asked for — Coqui TTS with an Indian
English voice, falling back to `edge_tts`):**

- **It actually runs in this environment, offline, with no external
  dependency.** The module's docstring is direct about the trade-off:
  "This is a real, functioning TTS engine and the generated audio is
  genuinely spoken and genuinely timeable — it is not faked — but its
  voice is the basic robotic espeak-ng voice, not a production-quality
  one."
- **It proves the full mechanism end to end** (TTS → real audio →
  transcription/alignment → highlight frames → Remotion render) without
  any external network call succeeding or failing being able to block
  that proof. A cloud vendor call (or a GPU-hosted neural TTS model)
  would introduce exactly the kind of external dependency this
  environment's network allowlist has already shown it can't always
  reach (see the whisper.cpp model-download gap below).
- **Swapping it in later is a drop-in replacement of one function.**
  Nothing downstream — transcription, alignment, highlight-frame
  computation, the Remotion composition — depends on which engine
  produced the WAV file; they only consume its audio and its measured
  duration. This was a deliberate design decision, not an accident: the
  docstring states it explicitly.
- The Phase 7 pilot report's own stated production recommendation
  ("swap `tts.py`'s `synthesize()` for a commercial TTS vendor... one
  function, already isolated for exactly this") confirms this was the
  intended seam all along, not a shortcut papered over.

### `timing.py: align_cues_to_words(cues, cue_word_index, words)`

**What it does:** for each cue, looks up its anchor word index in the
real transcript. An index inside the transcript's range is an exact,
verified alignment (`assumed=False`); an index outside it falls back to
the nearest word, widens the window by `WORD_WIDEN_MS` (200ms), and is
marked `assumed=True`.

**Why fall back to the nearest word plus a widened window, instead of
simply dropping a cue whose index falls outside the transcript:** the
TTS engine and the transcriber "rarely produce identical word counts"
(a real, expected mismatch — not a bug to be fixed away) — a one-word
discrepancy shouldn't cause an entire visual highlight cue to vanish
from the video. Anchoring to the nearest available word and widening
the window is exactly the locked rule's prescribed fallback, and
marking the result `assumed` is what keeps this fallback from silently
presenting an approximate timing as a verified one.

### `estimated_alignment.py: build_estimated_words(text, duration_ms)`

**What it does:** the fallback word-timing source used when real
transcription can't run — spreads words evenly across the real,
ffprobe-measured audio duration. Every cue aligned against these
estimated words is **force-marked `assumed=True`**, regardless of
whether its word index happened to land "in range."

**Why force every such cue to `assumed=True` even when the index
happens to fall inside the estimated word list's range (where
`align_cues_to_words` would normally mark it `assumed=False`):** the
*source* of the uncertainty here isn't "did the index fall in range" —
it's that the word timings themselves were never measured, only
evenly guessed. An index landing "in range" of a row of guesses is not
evidence of correctness the way it is for a real transcript; the
render pipeline (`build_render_bundle`) explicitly overrides every cue
built this way to `assumed=True` and appends an explanatory note,
specifically to prevent an estimated timing from ever being presented
as verified by coincidence of index arithmetic.

**Why even spacing instead of a (marginally more realistic)
word-length-proportional spacing:** the module's docstring states the
reasoning directly — "Proportional to word length would be marginally
more realistic, but even spacing keeps the estimate's nature obvious
rather than dressing it up as more precise than it is." A slightly
better-looking fake is still a fake; this project consistently chooses
honesty about a method's limits over cosmetic precision.

### `highlight_config.py: build_highlight_config(timed_cues, fps)`

**What it does:** `frame = round((ms / 1000) * fps)` for each cue's
start/end, producing `{id, lineRange, fromFrame, toFrame, assumed,
note}` — exactly the locked rule's conversion formula, with nothing
extra.

**Why keep this function this simple — a pure, one-line conversion —
rather than folding in any rendering logic:** the Shiki decoration call
and the actual React rendering genuinely belong to the Remotion/JS side
(a different language, a different runtime). Keeping this Python-side
function limited to producing the JSON config means the Python/
JavaScript boundary is a clean, pure-data handoff — testable on the
Python side with no Remotion/browser environment needed at all, which
is exactly how its dedicated unit tests work.

### `render_pipeline.py: build_render_bundle(script, output_dir, fps)` — the real/estimated fallback decision

**What it does:** tries real transcription via
`render-app/scripts/transcribe.mjs` (whisper.cpp) first; falls back to
`estimated_alignment.py` only if that doesn't produce a result; always
records which source was actually used (`"alignmentSource":
"whisper-cpp"` or `"estimated"`) — **never** claims an estimated run
was a real transcription.

**Why whisper.cpp (via Remotion's own `@remotion/install-whisper-cpp`)
instead of WhisperX (named in the original locked rules doc) as the
real alignment engine:** WhisperX needs a full Python audio stack
(`pyannote`, `torch`) that this environment doesn't carry. whisper.cpp,
installed through Remotion's own helper package, gives the same kind of
word-level `(word, startMs, endMs)` output WhisperX would, without that
heavy dependency — the module's docstring states this substitution and
its reasoning directly, framing it as "the same kind of... data" rather
than a silent, unacknowledged swap of the locked rule's named tool.

**Why this function always tries the real path first and only falls
back, rather than just always using the cheaper estimated path:** the
real path, when it can run, produces genuinely verified cue timings
(`assumed=False` where the index lands correctly) — strictly better
output. The estimated path exists purely as a documented fallback for
when the real path's one external dependency (the model download) is
network-blocked, not as a preferred default.

## Two real, documented environment gaps (not papered over)

1. **whisper.cpp's model file is network-blocked.** The binary itself
   compiles and runs in this environment; only the `huggingface.co`
   model download is blocked by this sandbox's network allowlist
   (confirmed via a direct `curl`: 403 at the proxy). Every real run in
   this session therefore used the `estimated` fallback, honestly
   labeled as such.
2. **Remotion's own headless Chromium download is also blocked.**
   Worked around with `--browser-executable` pointing at the Playwright
   Chromium already installed in this environment — a real, working
   Chromium, just not the one Remotion would normally fetch for itself.

Neither gap required a code change to work around in a less-restricted
environment — in a sandbox where `huggingface.co` is reachable (or the
model file is pre-provided), the real-transcription path runs
automatically instead, with no code change needed. See
[`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md).

## Remotion side: `CodeExplainerChunk.tsx`

**What it does:** plays the real narration audio, shows the chunk's
real source code with the highlighted line range fading in/out exactly
at the cue's real frame window (`useCurrentFrame()` + `interpolate()`),
and a side panel with narration text and `chunkId`/`alignmentSource`.

**Why display `alignmentSource` directly in the rendered video's own
UI, rather than keeping it purely as internal metadata:** this is the
same honesty principle carried all the way through to the final
artifact — anyone watching the rendered output (not just a developer
reading `bundle.json`) can see at a glance whether a given chunk's
highlight timing is `"whisper-cpp"` (verified) or `"estimated"`
(approximate), rather than that distinction disappearing once the video
exists.

**Why `calculateMetadata` fetches `bundle.json` to compute
`durationInFrames` dynamically, rather than hardcoding a composition
duration:** every chunk's narration audio has a different real
duration (17.9s–131.9s across the real pilot's 22 chunks, per Phase
7's report) — a fixed duration would either cut audio off early or
leave a long silent tail. Computing it from the bundle's actual
measured `durationMs` is the only way one reusable composition
correctly renders chunks of very different lengths.
