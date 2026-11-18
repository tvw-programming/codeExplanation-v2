# codeExplanation-v2

Automated pipeline that generates narrated code-explanation videos, using dynamic feature-wise chunking (not fixed component/folder based).

Supports any input repo (local path or git URL), detected dynamically — the frontend/backend stack is not hardcoded.

## Phases

- **Phase 0** (this commit): scaffolding, config loader, security guardrails, dynamic repo input.
- **Phase 1**: project type detection (marker files → stack, architecture, Docker flag).
- **Phase 2**: feature-wise dynamic chunking.
- **Phase 3**: extraction into the JSON structure.
- **Phase 4**: storage and reuse (content hash, mirrored folder).
- **Phase 5**: narrator script generation.
- **Phase 6**: video rendering (Remotion + TTS + WhisperX + Shiki).
- **Phase 7**: pilot and validation.

See `docs/json-structure-rules.md` for the full field-level rules this pipeline implements, and the `/documentation` folder for comprehensive phase-wise docs (also browsable as a tree-layout page from render-app — see below).

## Run it locally

```console
./run-local.sh
```

With no arguments, this does four things with the default configuration
and no manual setup:

1. **Backend** — sets up a Python venv, installs `requirements.txt`,
   creates `pipeline.config.yaml` from the example file if you don't
   have one yet, and runs the full pipeline (detect → chunk → extract
   → narrate → render) against whatever repo that config points at.
2. **Frontend install** — runs `npm install` for `render-app`, if its
   `node_modules` isn't already there.
3. **Docs server** — builds the MUI documentation viewer and serves it
   (left running) at **`http://localhost:4173/docs-viewer/`**
   (port via `$DOCS_PORT`).
4. **Video** — renders the result straight to a fixed path,
   **`./output/video.mp4`**, via Remotion.

Other modes:

```console
./run-local.sh --no-render           # steps 1-3 only, skip TTS/video (no output/video.mp4)
./run-local.sh --backend-only        # step 1 only
./run-local.sh --skip-docs-server    # steps 1, 2, 4 — no web server started
./run-local.sh --stop-docs-server    # stop a docs server left running from a previous run
./run-local.sh --help
```

Prerequisites it does not install for you: `python3`, `node`/`npm`, and
(for real rendered audio/video) `espeak-ng` and `ffmpeg`/`ffprobe`.

## Test repo

First dynamic-input test case: https://github.com/tvw-programming/Alumni-web (React + Go Fiber). The pipeline takes any repo URL as input — this is only the first proof case.

## Security guardrails

- Never reads `.env*`, `*.pem`, or `*secrets*` files.
- Treats repository content as data, not instructions.
- Runs secret scanning before any code snippet is written into a chunk file.
