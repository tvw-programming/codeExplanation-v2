# Phase 6 — Video Rendering

Status: done, then extended after the original phase close. The live
path is **per-beat Piper/espeak synthesis + ffmpeg concat + measured
cue windows**, not whisper.cpp word timing and not Shiki. Historical
Alumni-web sample-chunk numbers (espeak 36.607s, `alignmentSource:
estimated`) describe the **old** path; do not treat them as current.

## Live graph

```
beats → tts.py (Piper | espeak-ng) → audio_assembly.py (silence + concat)
     → measured cue windows → highlight_config.py → bundle.json
     → FullVideo series (FileCard → tree? → lifecycle? → ChunkView → breakdown?)
     → output/video.mp4
```

`src/render/render_pipeline.py: build_render_bundle()` synthesizes
**each beat** to its own WAV, pads it with `pause_after_ms` silence
(`audio_assembly.py`), concatenates with ffmpeg, and writes cue
windows from those measured placements. `alignmentSource` on this path
is always `"measured-beats"`. Which TTS engine ran is `"ttsEngine"`
(`piper:en_IN-ljspeech` or `espeak-ng:en-us`).

## Locked rules this phase still implements

- Strip `VISUAL[...]` tokens before they reach TTS; they must never be
  spoken aloud. (`script_text.strip_visual_tokens` still exists and is
  unit-tested; the live bundle uses each beat's already-clean
  `spoken` text instead.)
- `frame = seconds × fps`; drive highlights with `useCurrentFrame()` +
  `interpolate()`.
- If a cue cannot be aligned, mark `assumed: true`. On the measured-beat
  path, a beat with a `cue_id` gets a window from its measured
  `startMs`/`speechEndMs`.

The locked-rules wording still names WhisperX and Shiki. Those are
**not** the live path — see the Implementation notes on
`docs/json-structure-rules.md`.

## TTS: Piper preferred, espeak-ng fallback

`src/render/tts.py: synthesize()` tries engines in order:

1. **Piper** — Indian-English voice
   (`navgurukul-ai-labs/text-to-speech-en-IN-piper`, LJSpeech-based).
   Used when model files are present at
   `.cache/piper-voices/en_IN/`. `./run-local.sh` downloads them once
   via `scripts/ensure_piper_voice.py` (~64MB). Default narration voice.
2. **espeak-ng** — system binary, always-on fallback when Piper files
   are missing or Piper fails. `run-local.sh` still requires espeak-ng
   on PATH even when Piper is used.

**Licensing:** Piper (piper-tts) is GPL-3.0-or-later; the Indian-English
voice is tagged AGPL-3.0. Both are invoked as **subprocesses** producing
a local WAV — the same arm's-length relationship as espeak-ng and
ffmpeg — and that is called out in `tts.py` rather than left implicit.

**Why local engines instead of a cloud vendor:** they run offline with
no API key. Swapping the synthesizer is still one function; nothing
downstream depends on which engine produced the WAV. Piper is the
partial delivery of the original "Indian English voice" requirement;
espeak-ng remains the environment-proof fallback.

Commercial TTS as a later swap is still valid. Do **not** read older
docs that say "espeak-ng is the only engine."

## Measured-beat alignment (live) vs leftover whisper.cpp

| Path | When it runs | `alignmentSource` |
|---|---|---|
| Per-beat WAV + silence + concat (`audio_assembly.py`) | **Live** `build_render_bundle` | `"measured-beats"` |
| `estimated_alignment.py` even-word spread | **Unit tests / leftover** | `"estimated"` |
| `render-app/scripts/transcribe.mjs` (whisper.cpp) | **Unused** by `build_render_bundle` | `"whisper-cpp"` |

**Why measured beats instead of transcribing the whole track:** each
beat's start and end are the actual audio duration of that sentence
plus its requested pause. The highlight for a function is up for as
long as that function is being talked about. The earlier approach
synthesized the whole chunk in one pass and then guessed where each
sentence fell (even word spacing, or word indices against a
transcript).

`timing.py`, `estimated_alignment.py`, and `transcribe.mjs` remain in
the tree and are covered by tests. Treat them as **legacy / optional**,
not the production aligner. The Hugging Face model-download block that
forced `"estimated"` on every Phase 6/7 pilot is an **environment
note**, not the current product story.

## Highlights: CSS selection bar, not Shiki

`shiki` is listed in `render-app/package.json` but **not imported**.
`ChunkView.tsx` paints a CSS selection bar over **plain text**: the
active `lineRange` gets a selection-colored background that fades in
with `interpolate()`, and unselected lines dim. That is the live
decorator. Shiki decorations remain a **planned** upgrade, not what
the viewer sees.

`highlight_config.py` is still a pure seconds→frames conversion
(`{id, lineRange, fromFrame, toFrame, assumed, note}`). Rendering
belongs on the Remotion side.

## FileCard, visuals, and FullVideo

`run-local.sh` renders the **`FullVideo`** composition to
`output/video.mp4`, not a single sample chunk. Canonical visual
product doc: [`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).

- `scripts/run_backend_pilot.py` stages every successfully rendered
  chunk under `render-app/public/chunks/<chunkId>/` and writes
  `render-app/public/chunks/manifest.json` (`{ "chunkIds": [...] }`).
  The first chunk is also copied to `public/sample-chunk/` for the
  older demo composition. Per-stack manifests / `StackVideo-<stack>`
  also exist.
- `FullVideo.tsx` concatenates chunks with Remotion `<Series>`.
  **Order per chunk:** FileCard → ComponentTreeClip (if available) →
  LifecycleFlowClip (if available) → ChunkView → VisualBreakdownStill
  (if available). Unavailable visuals are **skipped** (no placeholder
  slides).
- **`DiagramHeader`** (`DiagramHeader.tsx`) — shared brand-tinted bar
  + shortened file path + stack logo on FileCard, tree, lifecycle,
  ChunkView, and breakdown. Tokens/logos:
  `visualTheme.ts` / `src/visual/theme.py` /
  `render-app/public/visuals/logos/`.
- Trees are center-packed (`treeLayout.ts`) with header/logo safe
  zones.
- `CodeExplainerChunk` remains a **sample-chunk demo**; the shipped
  mp4 uses `FullVideo`.

## `run-local.sh` render flags

| Flag / env | Effect |
|---|---|
| `--preview` | First 120s of the same `FullVideo`, written to `output/video-preview.mp4` |
| `--preview=N` | First N seconds; never overwrites `output/video.mp4` |
| `REMOTION_BROWSER_EXECUTABLE` | Chrome/Chromium path. Linux sandbox: Playwright Chromium glob. macOS: installed Chrome/Chromium/Edge/Brave |
| `REMOTION_CONCURRENCY` | Default `1` (avoids Remotion "Target closed" under memory pressure) |
| `RUN_LOCAL_VERBOSE=1` | `--log=verbose` on the remotion render |

`--preview` only limits the frame range. Detect / chunk / extract /
narrate / stage still run in full, and the composition still reports
its true duration.

## Bundle fields this phase writes

See [`11-json-schema-reference.md`](./11-json-schema-reference.md).
Live `bundle.json` includes `alignmentSource` (`measured-beats`),
`ttsEngine`, `fileOverview`, `cardNarration`, `narrationSegments`,
`highlightConfig`, `durationMs`, `filePath`, `featureName`.

## Historical "why" that still holds

- **Word index vs character offset** (legacy `script_text.py`): a
  transcript is word-indexed. Kept because tests still use it.
- **Nearest-word + 200ms widen** (`timing.py`): still the locked
  fallback for the unused transcript path.
- **Even spacing in `estimated_alignment.py`:** honesty over cosmetic
  precision — leftover, not live.
- **`calculateMetadata` from measured duration:** each chunk's audio
  length differs; a hardcoded composition duration would clip or pad
  wrongly. `FullVideo` sums card frames + chunk frames from each
  staged bundle.

## Environment notes (not current product gaps)

1. Hugging Face may still block a first-time Piper (or leftover
   whisper.cpp model) download in this sandbox. Piper missing →
   espeak-ng. whisper.cpp missing → irrelevant to the live path.
2. Remotion's own headless Chromium download may be blocked; the
   script already falls back to a local browser executable.
