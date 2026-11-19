# 18 — The repo viewer (`frontend/`)

A React app that shows the **analysed repo** — one file tree per
detected technology — and plays a clicked file's explanation. It is a
separate npm package at `frontend/`, started by `run-local.sh` as its
**first** step.

It is not the docs viewer. `render-app/docs-viewer-src/` renders this
`documentation/` folder; this one renders the repo the pipeline just
analysed.

---

## Why a file click can play without rendering anything new

The pipeline renders **one video per stack** (`output/video-go.mp4`).
A file's explanation is a contiguous span inside it: `main.go` is the
first 217.9 s of the Go video, `middleware.go` the next 174.8 s. Playing
a file is therefore a seek, not a render — `currentTime = 217.867`,
pause at `392.667`.

For that to be true, the offsets must be the ones the renderer actually
used. They are, by construction:

```
render-app/src/segmentTiming.ts     ← the only place a duration is decided
        │
        ├── FullVideo.tsx                 lays <Series.Sequence> out with it
        └── scripts/build-segment-index.ts publishes the same layout as JSON
```

Both go through `segmentsForStack()`. Changing a timing constant moves
the render and the index together; neither can drift from the other.
`scripts/check-segment-index.ts` (run by `tests/test_segment_index_check.py`)
asserts the published index tiles the video exactly — no gap, no
overlap, no missing chunk, every file opening on its FileCard.

### Chapters

A chunk contributes up to five segments, in play order: **card → tree →
lifecycle → code → breakdown**. A visual segment exists only when both
its narration audio *and* the thing it draws are present — the same
honesty rule `FullVideo` renders by (doc 17), applied by one shared
function rather than repeated. The viewer shows the surviving ones as a
chapter strip under the player, so you can jump to "Lifecycle" without
scrubbing.

---

## What the pipeline publishes for it

| File | Written by | Holds |
|---|---|---|
| `render-app/public/chunks/project.json` | `src/pilot/project_manifest.py` | Detected stacks, each with a role (`frontend` / `backend` / `other`), chunk count and video name |
| `render-app/public/chunks/<stack>/segments.json` | `render-app/scripts/build-segment-index.ts` | Per file: path, start/end seconds, chapters, purpose, layer |
| `render-app/public/status.json` | `src/pilot/status.py` | Live phase, chunks rendered, which videos are watchable, error |

All three are generated, all three are gitignored, and all three may be
**absent**: the viewer starts before the pipeline, so "not there yet" is
the normal first state rather than an error.

### The left/right split is derived, not hardcoded

`role_for_stack()` compares a staged stack against Phase 1's
`projectType.frontend` and `projectType.backend[]`. Point the pipeline
at a Vue + Spring Boot repo and the sidebar shows a Vue section above a
Spring Boot one with no code change here. A stack detection could not
place is `other` and sorts last — it is not guessed into a side.

Staged directories hyphenate (`spring-boot`) because Remotion
composition ids disallow underscores, while detection reports
`spring_boot`; the comparison normalises both.

---

## Live progress

`run_pilot(progress=...)` emits a small event at each phase boundary
(`detect`, `extract`, `validate`, `narrate`, `render`, `done`) and once
per chunk during rendering. `run_backend_pilot.py` passes
`StatusWriter.on_progress`, which rewrites `status.json` atomically
(temp file + `os.replace`) — a browser polling it every 3 s reads a
complete document or the previous one, never half of either.

`run-local.sh` continues the story for the stages that are not Python:
`--phase indexing`, `--phase rendering`, and a `--video-ready <stack>`
per finished render, so a stack becomes watchable as soon as *its* video
lands instead of when the last one does.

The callback is advisory: a progress consumer that raises is swallowed,
because a broken banner must not take a 40-minute run down.

---

## Serving the data

`frontend/vite.config.ts` mounts the pipeline's real directories under
`/data` with `sirv`:

| URL | Directory |
|---|---|
| `/data/chunks` | `render-app/public/chunks` |
| `/data/videos` | `output` |
| `/data/visuals` | `render-app/public/visuals` |
| `/data/state` | `render-app/public` (for `status.json`) |

Two things this buys that a copy step would not: a chunk staged five
minutes from now is served the moment it lands, and `sirv` answers HTTP
**range** requests — which is the whole feature, since seeking to 217 s
of a 300 MB mp4 is a range request.

A miss under `/data` is answered **404**, not Vite's SPA fallback: an
`index.html` served where the app asked for an mp4 would be handed to a
`<video>` element to decode.

---

## Running it

```console
./run-local.sh                # viewer first, then the pipeline
./run-local.sh --web-only     # browse what is already on disk
./run-local.sh --skip-web     # no viewer
./run-local.sh --stop-web     # stop one left running
```

Viewer at **`http://localhost:5174/`** (`$WEB_PORT`). Deep links carry
the selection: `?stack=go&file=api/cmd/server/main.go`.

### Preview renders

`--preview` renders only the opening of each video to
`video-<stack>-preview.mp4`. The viewer prefers the full render, falls
back to the preview, says so, and greys out files whose start lies past
the end of the file that exists — rather than seeking into nothing.

---

## Tests

| What | Where |
|---|---|
| Timing layout, chapter gating, index invariants | `render-app/scripts/check-segment-index.ts` (via `tests/test_segment_index_check.py`) |
| Progress callback phases and back-compat | `tests/test_pilot_progress.py` |
| Role mapping, stack ordering | `tests/test_project_manifest.py` |
| Atomic status writes, ready flags | `tests/test_status_file.py` |
| Path folding, chain collapsing | `frontend/src/fileTree.test.ts` |
| Seek/stop/preview-gating arithmetic | `frontend/src/segments.test.ts` |

The two frontend files run under vitest: `cd frontend && npm test`.
