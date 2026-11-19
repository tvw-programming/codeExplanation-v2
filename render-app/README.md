# render-app — pipeline video + docs viewer

This is the Remotion front end of **codeExplanation-v2**, not a stock
Remotion starter. The Python pipeline (`./run-local.sh` from the repo
root) stages per-chunk bundles here; this app turns them into video
and also hosts the documentation viewer.

## Compositions

Registered in `src/Root.tsx`:

| Composition | What it is | Who renders it |
|---|---|---|
| **`FullVideo`** | Every staged chunk, back-to-back, each introduced by a **FileCard** | `./run-local.sh` → `output/video.mp4` |
| **`CodeExplainerChunk`** | One sample chunk from `public/sample-chunk/` | Studio / `npx remotion render CodeExplainerChunk` |
| `MyComposition` | Remotion scaffold leftover | unused by the pipeline |

`FullVideo` reads `public/chunks/manifest.json` (`chunkIds`) and, for
each id, `public/chunks/<id>/bundle.json` + `narration.wav` (and
`card.wav` when the file card has narration). Staging is done by
`scripts/run_backend_pilot.py`, not by this app.

Highlights are a **CSS selection bar** over plain text in
`ChunkView.tsx`. `shiki` is in `package.json` but not imported.

## Commands

From this directory:

```console
npm i --loglevel=error
npm run dev                 # Remotion Studio — preview FullVideo / CodeExplainerChunk
npx remotion render FullVideo ../output/video.mp4
```

From the **repo root**, prefer `./run-local.sh` (backend + optional
`--preview` / `--preview=N` + browser/concurrency fallbacks). See the
root `README.md`.

Preview a truncated opening of the same composition:

```console
./run-local.sh --preview        # 120s → output/video-preview.mp4
./run-local.sh --preview=30
```

Useful env vars (honored by `run-local.sh`):
`REMOTION_BROWSER_EXECUTABLE`, `REMOTION_CONCURRENCY` (default 1),
`RUN_LOCAL_VERBOSE=1`.

## Documentation viewer (MUI)

A tree sidebar (Start Here / Pipeline Phases / Reference / Roadmap)
plus rendered markdown. Source app: `docs-viewer-src/`, built with Vite
into `public/docs-viewer/`.

```console
npm run build:docs   # builds docs-viewer-src/ → public/docs-viewer/
npm run dev           # then open http://localhost:3000/docs-viewer/
```

**`npm run build:docs` does not copy markdown.** The viewer reads
`public/docs/manifest.json` + `public/docs/*.md` — a **snapshot** of
the canonical files in `../documentation/`. After editing
documentation, copy `documentation/{01–15,README}.md` into
`public/docs/` and refresh `manifest.json`. Recipe:
[`documentation/README.md`](../documentation/README.md).

`./run-local.sh` serves the built viewer at
`http://localhost:4173/docs-viewer/` (port via `$DOCS_PORT`).

The viewer and the Remotion compositions share one MUI theme
(`shared/theme.ts`).

## Remotion docs / license

Remotion fundamentals: https://www.remotion.dev/docs/the-fundamentals
License: some entities need a company license —
https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
