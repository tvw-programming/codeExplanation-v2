# Multi-stack visuals

Shipped: React (#3), Go Fiber (#4), remaining stacks (#5), brand header
chrome + center-packed trees (#6). `EXTRACTOR_VERSION = 8`.

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

## Honesty skips

Unavailable visual segments are **omitted** — no placeholder slides.
`FullVideo` only adds a clip when its frame count is non-zero and the
graph/flows/narration artifacts are present.

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

| Stack | Extractor | Typical graph | Honesty note |
|---|---|---|---|
| React | `ts_extractor` | `component_tree` | Regex limits remain |
| Go Fiber | `go_extractor` | `route_tree` | In-file group prefixes compose |
| Angular | `angular_extractor` | `component_tree` | Dedicated path; empty → unavailable |
| Vue / Solid / Qwik | basic extractors | `component_tree` | Thin when mounts/signals missing |
| JavaScript | `javascript_extractor` | `module_graph` | Import/export edges |
| Python | `python_extractor` (`ast`) | `route_tree` / `module_graph` | `fidelity: syntax` |
| Express | `express_extractor` | `route_tree` | Backend stack; not `react_or_angular` |
| Spring Boot | `spring_extractor` | `di_graph` | Inject by type, never imports-as-inject |
| Rust | `rust_extractor` | `route_tree` / `crate_graph` | Regex; routes assumed; macros may miss |

Dispatch: `extractor.py` / `reuse_pipeline.py` → `stack_records.py` →
`attach_visuals()`.

## Tests

`tests/test_react_visuals.py`, `tests/test_go_fiber_visuals.py`,
`tests/test_multi_stack_visuals.py`, `tests/test_visual_theme_tokens.py`,
`tests/test_tree_layout_check.py`. Suite count:
[`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md).
