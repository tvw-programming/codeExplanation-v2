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

With no arguments, this does everything with the default configuration
and no manual setup: sets up a Python venv and installs
`requirements.txt`, creates `pipeline.config.yaml` from the example file
if you don't have one yet, runs the full pipeline (detect → chunk →
extract → narrate → render) against whatever repo that config points
at, and renders the result straight to **`./output.mp4`** via Remotion
— no interactive server left running.

Other modes:

```console
./run-local.sh --no-render       # backend only, skip TTS/video (no output.mp4)
./run-local.sh --backend-only    # run the pipeline and exit
./run-local.sh --frontend-only   # render whatever is already staged
./run-local.sh --studio          # open Remotion Studio + the docs viewer instead
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
