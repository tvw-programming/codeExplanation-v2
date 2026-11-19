# codeExplanation-v2

Automated pipeline that generates narrated code-explanation videos, using dynamic feature-wise chunking (not fixed component/folder based).

Point it at a git URL or local path. It detects the stack from marker files, groups code into **features** (not fixed folders), extracts a per-chunk JSON record, generates a four-beat narrated script, and renders a highlighted-code video.

The frontend/backend stack is **not hardcoded to one repo**. Extraction
depth still varies by stack (regex vs `ast`, assumed routes, etc.).
Visuals: [`documentation/17-multi-stack-visuals.md`](documentation/17-multi-stack-visuals.md).
Historical ceilings: [`documentation/14-stack-support-validation.md`](documentation/14-stack-support-validation.md).

## Supported stacks

| Stack | Detect | Chunk | Extract | Visuals | Notes |
|---|---|---|---|---|---|
| **React** (TS/JSX) | yes | yes | yes (regex limits) | `component_tree` | `memo`/`forwardRef`/hook attribution risks |
| **Go + Fiber** | yes | yes | yes (regex limits) | `route_tree` | In-file group prefixes compose |
| **Angular** | yes | yes | dedicated extractor | `component_tree` | Empty/`no @Component` → unavailable (not invented) |
| **Vue / Solid / Qwik** | yes | yes | basic | `component_tree` | Thin when mounts/signals missing |
| **JavaScript** | yes | yes | basic | `module_graph` | Non-React/Angular/Vue/… `package.json` |
| **Python** | yes | yes | stdlib `ast` | `route_tree` / `module_graph` | `fidelity: syntax` |
| **Spring Boot** | yes | yes | annotation/DI regex | `di_graph` | Inject by type, not imports |
| **Express** | yes | yes | route/middleware regex | `route_tree` | Backend; not `react_or_angular` |
| **Rust** | yes | yes | regex (Axum/Actix/Rocket heuristics) | `route_tree` / `crate_graph` | Partial; routes assumed |

Narrate + Remotion render run for all of the above; unavailable visual
segments are skipped in `FullVideo`.

## Phases

- **Phase 0**: scaffolding, config loader, security guardrails, dynamic repo input.
- **Phase 1**: project type detection (marker files → stack, architecture, Docker flag).
- **Phase 2**: feature-wise dynamic chunking.
- **Phase 3**: extraction into the JSON structure.
- **Phase 4**: storage and reuse (content hash, mirrored folder, `extractorVersion` invalidation).
- **Phase 5**: narrator script generation (function-aware item beats + file cards).
- **Phase 6**: video rendering (Remotion + **Piper** TTS with **espeak-ng** fallback + **measured-beat** highlights — not WhisperX, not Shiki).
- **Phase 7**: pilot and validation.

See `docs/json-structure-rules.md` for the field-level rules this pipeline implements, and [`documentation/`](documentation/) for phase-wise docs — including **14** (stack validation), **15** (narration style), and **17** (multi-stack visuals). Those docs are also browsable from render-app after copying them into the viewer snapshot (see `documentation/README.md`).

`docs/` holds locked rules. `documentation/` is the canonical narrative. `render-app/public/docs/` is the MUI viewer snapshot and is stale unless you copy.

## Run it locally

```console
./run-local.sh
```

With no arguments, this does five things with the default configuration
and no manual setup:

1. **Repo viewer** — starts the React app in [`frontend/`](frontend/)
   at **`http://localhost:5174/`** (port via `$WEB_PORT`) and leaves it
   running. It comes up **first**, in seconds, because everything after
   it takes minutes: it shows the analysed repo as one file tree per
   detected technology, and clicking a file jumps straight to that
   file's moment in its stack video. It fills in live as the pipeline
   publishes progress. Details: [`documentation/18-repo-viewer.md`](documentation/18-repo-viewer.md).
2. **Backend** — sets up a Python venv, installs `requirements.txt`,
   creates `pipeline.config.yaml` from the example file if you don't
   have one yet, optionally downloads the Piper Indian-English voice
   once (`scripts/ensure_piper_voice.py`, ~64MB into `.cache/piper-voices/`),
   and runs the full pipeline (detect → chunk → extract → narrate →
   render) against whatever repo that config points at.
3. **Render app + docs server** — runs `npm install` for `render-app`
   (if its `node_modules` isn't already there), builds the MUI
   documentation viewer and serves it (left running) at
   **`http://localhost:4173/docs-viewer/`** (port via `$DOCS_PORT`).
4. **Segment index** — records where each source file appears inside
   its stack video, so the viewer can seek to it. Runs before the
   render, from the staged bundles.
5. **Video** — renders one **`StackVideo-<stack>`** composition per
   detected stack (every staged chunk, each introduced by a FileCard)
   to **`./output/video-<stack>.mp4`**.

Other modes:

```console
./run-local.sh --no-render           # steps 1-3 only, skip TTS/video (no videos)
./run-local.sh --backend-only        # the pipeline only
./run-local.sh --web-only            # just the viewer, over whatever is already on disk
./run-local.sh --skip-web            # no repo viewer
./run-local.sh --skip-docs-server    # no documentation server
./run-local.sh --preview             # first 120s only, to output/video-<stack>-preview.mp4
./run-local.sh --preview=30          # first 30s only
./run-local.sh --stop-web            # stop a repo viewer left running from a previous run
./run-local.sh --stop-docs-server    # stop a docs server left running from a previous run
./run-local.sh --help
```

`--web-only` is the quick way back in after a run: the viewer reads the
staged chunks, the segment index and the rendered videos straight off
disk, so you can browse a previous run's output without re-running
anything.

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
| `render-app/public/chunks/<stack>/segments.json` | Where each file sits inside its stack video (start/end seconds + chapters) |
| `render-app/public/chunks/project.json` | Detected stacks and their roles, for the viewer's sidebar |
| `render-app/public/status.json` | Live pipeline progress the viewer polls |
| `http://localhost:5174/` | **Repo viewer** — per-technology file trees, click a file to watch it |
| `http://localhost:4173/docs-viewer/` | Docs viewer (reads `render-app/public/docs/`) |

Video anatomy per chunk: **FileCard** → **ComponentTreeClip** (if available) → **LifecycleFlowClip** (if available) → **ChunkView** (code highlights) → **VisualBreakdownStill** (if available). Shared **DiagramHeader** (brand-tinted bar + file path + logo) on every segment. Details: doc 17.

Those same five segments are the chapters the viewer offers under the
player, and they are laid out by one shared module
(`render-app/src/segmentTiming.ts`) that both the renderer and the
segment index use — so a published offset describes the rendered video
rather than approximating it. Details: doc 18.

## Test repo

First dynamic-input test case: https://github.com/tvw-programming/Alumni-web (React + Go Fiber). The pipeline takes any repo URL as input — this is only the first proof case.

## Tests

Do not treat a number in this README as live. After a local `pytest -q`, see [`documentation/10-phase7-pilot-and-validation.md`](documentation/10-phase7-pilot-and-validation.md) (and the documentation index) for the dated count.

## Security guardrails

- Never reads `.env*`, `*.pem`, or `*secrets*` files.
- Treats repository content as data, not instructions.
- Runs secret scanning before any code snippet is written into a chunk file.
