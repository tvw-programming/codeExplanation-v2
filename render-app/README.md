# Remotion video

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Welcome to your Remotion project!

## Commands

**Install Dependencies**

```console
npm i --loglevel=error
```

**Start Preview**

```console
npm run dev
```

**Render video**

```console
npx remotion render
```

**Upgrade Remotion**

```console
npx remotion upgrade
```

## Documentation viewer (MUI)

This project also ships a documentation browser for the
`/documentation` folder at the repo root — a tree sidebar (grouped by
Start Here / Pipeline Phases / Reference / Roadmap) on the left,
rendered markdown on the right. It's a small React + MUI app in
`docs-viewer-src/`, built with Vite into `public/docs-viewer/`, and
served as static files by Remotion's own dev server alongside the
video-rendering UI — so no second server or toolchain is needed.

```console
npm run build:docs   # builds docs-viewer-src/ -> public/docs-viewer/
npm run dev           # then open http://localhost:3000/docs-viewer/
```

Re-run `npm run build:docs` any time `../documentation/*.md` changes
(the build copies nothing automatically — see `docs-viewer-src/vite.config.ts`
and `public/docs/` for where the markdown source files are read from).

Every component in render-app — this docs viewer and the
`CodeExplainerChunk` Remotion composition in `src/` — shares one MUI
theme (`shared/theme.ts`) and the same `@mui/material`/`@mui/x-tree-view`
dependency versions declared in this project's own `package.json`.

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Help

We provide help on our [Discord server](https://discord.gg/6VzzNDwUwV).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).
