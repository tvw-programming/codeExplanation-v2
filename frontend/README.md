# frontend — the repo viewer

A React app that shows the **repo the pipeline analysed** — one file
tree per detected technology — and plays a clicked file's explanation by
seeking into that stack's video.

Not to be confused with `render-app/docs-viewer-src/`, which renders
this project's own `documentation/`.

```console
npm install
npm run dev     # http://localhost:5174/   ($WEB_PORT)
npm test        # vitest over the pure logic
```

`./run-local.sh` starts this first, before the pipeline, because a full
run takes many minutes and the viewer fills in live as it progresses.
`./run-local.sh --web-only` brings up just this, over whatever a
previous run left on disk.

## How it gets its data

Nothing is bundled: `vite.config.ts` mounts the pipeline's real output
directories under `/data` with `sirv`, so a chunk staged five minutes
from now is served the moment it lands, and video seeking works (sirv
answers HTTP range requests).

| URL | Directory | Written by |
|---|---|---|
| `/data/chunks/project.json` | `render-app/public/chunks` | `src/pilot/project_manifest.py` |
| `/data/chunks/<stack>/segments.json` | `render-app/public/chunks` | `render-app/scripts/build-segment-index.ts` |
| `/data/state/status.json` | `render-app/public` | `src/pilot/status.py` |
| `/data/videos/video-<stack>.mp4` | `output` | `run-local.sh` (Remotion) |

Every one of them may be absent — the viewer starts before the pipeline,
so "not there yet" is the normal first state, not an error.

Full write-up: [`../documentation/18-repo-viewer.md`](../documentation/18-repo-viewer.md).
