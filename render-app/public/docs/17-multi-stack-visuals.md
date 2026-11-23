# Multi-stack visuals

Shipped: React (#3), Go Fiber (#4), remaining stacks (#5), brand header
chrome + center-packed trees (#6). `EXTRACTOR_VERSION = 21`.

Attach: `src/visual/pipeline.py: attach_visuals()`. Render:
`render-app/src/FullVideo.tsx`. Layout: `treeLayout.ts`. Header:
`DiagramHeader.tsx`.

Regex / cross-file ceilings that still apply are in
[`14-stack-support-validation.md`](./14-stack-support-validation.md)
(historical body; read the current-status banner first).

## FullVideo segment order

Per chunk:

1. **FileCard** — when `fileOverview` exists
2. **ComponentTreeClip** — when `visualGraph` + tree narration exist
3. **LifecycleFlowClip** — when `lifecycleFlows` + lifecycle narration exist
4. **ChunkView** — always (code + measured-beat highlights)
5. **VisualBreakdownStill** — when graph + breakdown narration exist

TTS for visual clips uses measured beats (`alignmentSource:
"measured-beats"`), same as narration.

**Mermaid is docs/chat only** — it does not insert FullVideo segments.
Per-chunk `architecture.md` + `interactive.json` fields `mermaid` /
`mermaidLifecycle` mirror the same JSON. See
[`19-mermaid-architecture-docs.md`](./19-mermaid-architecture-docs.md).

## Honesty skips

Unavailable visual segments are **omitted** — no placeholder slides.
`FullVideo` only adds a clip when its frame count is non-zero and the
graph/flows/narration artifacts are present.

**Manifest order:** `run_backend_pilot` writes each `StackVideo-<stack>`
manifest with visual-bearing chunks first (stable within each group).
That way `--preview` reaches Go Fiber `route_tree` files (often only
`cmd/server/main.go`) instead of spending minutes on handler/repo
chunks that correctly stay `unavailable`.

| Record field | Role |
|---|---|
| `visualAvailability.*` | `available` / `partial` / `unavailable` per capability |
| `visualGraph` | Object or **`null`** — never invented |
| `lifecycleFlows` | List; empty when unavailable |
| `fidelity` | `regex` / `syntax` / `typed` |

Examples: empty Angular (no `@Component`), empty Python (no edges),
Rust file with only `fn`s (no `mod`/`use`/routes) → unavailable tree
and lifecycle → FileCard + ChunkView only.

## Brand colors, logos, DiagramHeader

- Tokens: `src/visual/theme.py` ↔ `render-app/src/visualTheme.ts`
  (hyphens → underscores, e.g. `spring-boot` → `spring_boot`).
- Logos: `render-app/public/visuals/logos/` (Go: `go-fiber.svg`).
- **`DiagramHeader`** — shared AppBar-style chrome on FileCard, tree,
  lifecycle, ChunkView, and breakdown: brand-tinted bar
  (`onDark`/`primary` at ~20% alpha), brand underline, monospace
  shortened file path, stack logo top-right inside the bar
  (`HEADER_HEIGHT` from `treeLayout.ts`).
- Trees are **center-packed** with header/logo safe zones
  (`check-tree-layout.ts` / `tests/test_tree_layout_check.py`).
- Artifacts: `visuals/<stack>/<chunkId>/`. Optional per-stack Remotion
  compositions: `StackVideo-<stack>`.

## Stack matrix (visuals)

| Stack | Extractor package | Typical graph | Honesty note |
|---|---|---|---|
| React | `src/extract/react/` | `component_tree` | Brace/memo/HOC/hook honesty; regex limits remain |
| Go Fiber | `src/extract/go/` | `route_tree` | In-file prefixes; generics/interfaces/factories; All/Add; brace-scoped `Route()`; `var _` asserts only |
| Angular | `src/extract/angular/` | `component_tree` | Selector index → template mounts; signal/decorator I/O; relative templateUrl bundles (incl. `../`); unmatched tags skipped; empty → unavailable |
| Vue / Solid / Qwik | `src/extract/{vue,solid,qwik}/` | `component_tree` | Thin when mounts/signals missing |
| JavaScript | `src/extract/javascript/` | `module_graph` | Import/export edges |
| Python | `src/extract/python/` (`ast`) | `route_tree` / `module_graph` | In-file `APIRouter`/`Blueprint` + mounts compose; cross-file `include_router`/`register_blueprint`/`include()` on unique resolve; Django handlers cross-file `UNKNOWN` |
| Express | `src/extract/express/` | `route_tree` | Nested + cross-file `require()` mounts (unique literal); path arrays; regex→assumed; per-route METHOD mw |
| Spring Boot | `src/extract/spring/` | `di_graph` | By type + Lombok/setter/@Inject; bare `@RequestMapping`→ALL; never imports-as-inject / never invent Impl |
| Rust | `src/extract/rust/` | `route_tree` / `crate_graph` | Real handlers; in-file + unique cross-file `.nest` (PrefixGraph); unresolved nest skips |

**Mermaid twin (docs/chat):** same stacks → flowchart / sequence kinds and
skip reasons in
[`20-mermaid-stack-matrix.md`](./20-mermaid-stack-matrix.md).

**Layout:** all stacks use `src/extract/<stack>/{extract,record}.py`.
Flat `*_extractor.py` / `json_builder.py` are shims. `stack_records.py`
re-exports. Dispatch: `extractor.py` / `reuse_pipeline.py` → per-stack
`record.py` → `attach_visuals()`.

## Tests

`tests/test_react_visuals.py`, `tests/test_go_fiber_visuals.py`,
`tests/test_multi_stack_visuals.py`, `tests/test_extractor_hardening.py`,
`tests/test_visual_theme_tokens.py`, `tests/test_tree_layout_check.py`.
Suite count:
[`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md).
