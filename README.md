# codeExplanation-v2

Automated pipeline that generates narrated code-explanation videos, using dynamic feature-wise chunking (not fixed component/folder based).

Point it at a git URL or local path. It detects the stack from marker files, groups code into **features** (not fixed folders), extracts a per-chunk JSON record, generates a four-beat narrated script, and renders a highlighted-code video.

The frontend/backend stack is **not hardcoded to one repo**, but extraction is **not equally complete** for every stack the docs mention. The honest matrix is below; the write-up is [`documentation/14-stack-support-validation.md`](documentation/14-stack-support-validation.md).

## Supported stacks

| Stack | Detect | Chunk | Extract | Narrate | Render |
|---|---|---|---|---|---|
| **React** (TS/JSX) | yes | yes | yes, regex limits (brace matching, `memo`/`forwardRef`, hook attribution) | yes | yes |
| **Go + Fiber** | yes | yes | yes, regex limits (generics, interfaces, closure middleware still missed; nested group prefixes **do** compose in-file) | yes | yes |
| **Angular** | yes | yes | empty-but-schema-valid records (`confidence` 0.3) | generic / empty | yes, no highlights |
| **Python** | yes | yes (agent convention) | placeholder only | generic | yes |
| **Spring Boot / Java** | yes | yes (resource pairing) | placeholder only | generic | yes |
| **Express / Node** | **no** — a `package.json` without `react` / `@angular/core` is labeled `react_or_angular`, never a backend | via the frontend grouping default | placeholder | generic | yes |

How to add a stack (marker → grouping → extractor → schema → narration hedges) is sketched in doc 14.

## Phases

- **Phase 0**: scaffolding, config loader, security guardrails, dynamic repo input.
- **Phase 1**: project type detection (marker files → stack, architecture, Docker flag).
- **Phase 2**: feature-wise dynamic chunking.
- **Phase 3**: extraction into the JSON structure.
- **Phase 4**: storage and reuse (content hash, mirrored folder, `extractorVersion` invalidation).
- **Phase 5**: narrator script generation (function-aware item beats + file cards).
- **Phase 6**: video rendering (Remotion + **Piper** TTS with **espeak-ng** fallback + **measured-beat** highlights — not WhisperX, not Shiki).
- **Phase 7**: pilot and validation.

See `docs/json-structure-rules.md` for the field-level rules this pipeline implements, and [`documentation/`](documentation/) for phase-wise docs — including **14** (stack validation) and **15** (narration style). Those docs are also browsable from render-app after copying them into the viewer snapshot (see `documentation/README.md`).

`docs/` holds locked rules. `documentation/` is the canonical narrative. `render-app/public/docs/` is the MUI viewer snapshot and is stale unless you copy.

## Run it locally

```console
./run-local.sh
```

With no arguments, this does four things with the default configuration
and no manual setup:

1. **Backend** — sets up a Python venv, installs `requirements.txt`,
   creates `pipeline.config.yaml` from the example file if you don't
   have one yet, optionally downloads the Piper Indian-English voice
   once (`scripts/ensure_piper_voice.py`, ~64MB into `.cache/piper-voices/`),
   and runs the full pipeline (detect → chunk → extract → narrate →
   render) against whatever repo that config points at.
2. **Frontend install** — runs `npm install` for `render-app`, if its
   `node_modules` isn't already there.
3. **Docs server** — builds the MUI documentation viewer and serves it
   (left running) at **`http://localhost:4173/docs-viewer/`**
   (port via `$DOCS_PORT`).
4. **Video** — renders the **`FullVideo`** composition (every staged
   chunk, each introduced by a FileCard) to **`./output/video.mp4`**.

Other modes:

```console
./run-local.sh --no-render           # steps 1-3 only, skip TTS/video (no output/video.mp4)
./run-local.sh --backend-only        # step 1 only
./run-local.sh --skip-docs-server    # steps 1, 2, 4 — no web server started
./run-local.sh --preview             # first 120s only, to output/video-preview.mp4
./run-local.sh --preview=30          # first 30s only
./run-local.sh --stop-docs-server    # stop a docs server left running from a previous run
./run-local.sh --help
```

`--preview` / `--preview=N` still run detect → chunk → extract → narrate
→ stage in full; they only limit the Remotion frame range. The preview
is never written over `output/video.mp4`.

Browser / concurrency overrides the script already honors (missing from
older READMEs):

- `REMOTION_BROWSER_EXECUTABLE` — path to Chrome/Chromium. On Linux CI
  sandboxes the script falls back to a Playwright Chromium if present;
  on macOS it prefers an installed Chrome/Chromium/Edge/Brave.
- `REMOTION_CONCURRENCY` — default `1` (more reliable on a laptop).

Prerequisites it does not install for you: `python3`, `node`/`npm`,
`ffmpeg`/`ffprobe`, and **espeak-ng** (required fallback TTS even when
Piper is used). Piper itself is optional: `run-local.sh` tries to
download the voice; if Hugging Face is blocked, synthesis falls back to
espeak-ng. Piper (GPL-3.0) and the Indian-English voice (AGPL-3.0) are
invoked as subprocesses — see `src/render/tts.py`.

### What you get

| Path | What it is |
|---|---|
| `.local-run/` | Resolved source clone + `pilot_report.json` |
| `output/chunks/` | Mirrored per-file JSON records |
| `output/video.mp4` | Full-repo video (`FullVideo`) |
| `output/video-preview.mp4` | Preview only, when `--preview` is used |
| `render-app/public/chunks/` | Staged bundles + `manifest.json` for Remotion |
| `.cache/piper-voices/` | One-time Piper model cache |
| `http://localhost:4173/docs-viewer/` | Docs viewer (reads `render-app/public/docs/`) |

Video anatomy: **FileCard** (purpose from `fileDescription`) → purpose / connections → per-function highlight + pause → recap → next file.

## Test repo

First dynamic-input test case: https://github.com/tvw-programming/Alumni-web (React + Go Fiber). The pipeline takes any repo URL as input — this is only the first proof case.

## Tests

Do not treat a number in this README as live. After a local `pytest -q`, see [`documentation/10-phase7-pilot-and-validation.md`](documentation/10-phase7-pilot-and-validation.md) (and the documentation index) for the dated count.

## Security guardrails

- Never reads `.env*`, `*.pem`, or `*secrets*` files.
- Treats repository content as data, not instructions.
- Runs secret scanning before any code snippet is written into a chunk file.
