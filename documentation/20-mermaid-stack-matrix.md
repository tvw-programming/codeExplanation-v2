# Mermaid stack matrix

Which stacks get which Mermaid diagram kinds, and when we **skip**
instead of inventing edges. Complements the Remotion visuals matrix in
[`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md) and the
docs/video placement map in
[`19-mermaid-architecture-docs.md`](./19-mermaid-architecture-docs.md).

**Rules (locked):** Mermaid is docs/chat only — never a FullVideo
segment (Q1). JSON SoT (`visualGraph` / `lifecycleFlows`). Assumed
facts → `-.->` or sequence `Note … assumed`. Empty / unavailable /
too_large → no fence (Q5). Never invent edges.

## Detect → diagram kinds

| Stack | Detection signal | Structure Mermaid | Lifecycle Mermaid | Skip when |
|---|---|---|---|---|
| **React** | `package.json` + React deps | `flowchart TD` (`component_tree` mounts) | `sequenceDiagram` from `lifecycleFlows` | No mounts / no flows / >40 nodes; nested JSX prop braces + memo/forwardRef names when proven |
| **Angular** | `package.json` + Angular deps | `flowchart TD` selector tree + confirmed template mounts | Sequence when flows exist | Empty `@Component` / no edges → unavailable; unmatched tags skipped; relative `templateUrl` (incl. `../`) class+html stays one chunk when uniquely resolved |
| **Vue / Solid / Qwik** | FE deps in `package.json` | `flowchart TD` mounts when present | Sequence when flows present | Thin extractors; missing mounts → skip |
| **JavaScript** | `package.json` without concrete FE | `flowchart TD` (`module_graph`) | Sequence when call/lifecycle edges exist | No import/call edges |
| **Go Fiber** | `go.mod` + Fiber import | `flowchart TD` (`route_tree`) | Sequence middleware→handler | No routes; unresolved prefixes / non-literal `Add` skipped; brace-scoped literal `Route()` composes; Impl only from explicit `var _` asserts |
| **Express** | `express` in `package.json` | `flowchart TD` (`route_tree`; nested + cross-file `require()` mounts; path arrays; regex→assumed) | Sequence middleware→handler (incl. per-route METHOD args) | No routes/edges; non-literal / ambiguous mounts assumed |
| **Python** | `requirements.txt` / `pyproject.toml` / `setup.py` | `flowchart TD` route or module graph | Sequence when flows exist | No edges; `APIRouter`/`Blueprint` + unique `include_router`/`include()` join; in-file view/CBV methods; unresolved mounts **assumed** (`fidelity: syntax`) |
| **Spring Boot** | Maven/Gradle + spring-boot | `flowchart TD` (`di_graph` by injection type / Lombok/setter/@Inject) | Sequence when flows exist | No inject edges; never draw Impl from imports alone; bare `@RequestMapping`→ALL; placeholder paths assumed |
| **Java** (non-Spring) | JVM markers without spring-boot | Same DI path when edges exist | Same | Empty → unavailable |
| **Rust** | `Cargo.toml` | `flowchart TD` route / crate graph | Sequence when flows exist | Regex ceilings; macros may miss; handlers + in-file / unique cross-file `.nest` via PrefixGraph; unresolved nest skips |

Dispatch: `src/detect/project_type.py` → `src/extract/<stack>/` →
`src/visual/pipeline.py` `attach_visuals()` →
`export_mermaid` / `export_lifecycle_mermaid` →
`architecture.md` + `interactive.json`.

Hardening notes + layout: Project store
`docs/extractor-hardening-plan.md`. `EXTRACTOR_VERSION` **21**.
Sample Mermaid under `visuals/` is regenerated from checked-in
`visualGraph` / `lifecycleFlows` only (`scripts/regen_mermaid_artifacts.py`)
— never by inventing edges.

## Honesty / confidence in diagrams

| Level | Meaning | Mermaid rendering |
|---|---|---|
| **Reliable** | Marker + extractor edges present | Solid `-->` / sequence messages |
| **Uncertain** | Heuristic only (unresolved route prefix, assumed wrap) | Dashed `-.->` or `Note … assumed` |
| **Unsupported** | No edges / placeholder / empty-valid | **No diagram**; prose skip reason |

Agentic narration markers (`langchain`, MCP, etc.) are **metadata only**
until extractors prove call edges — markers alone never become Mermaid
topology.

## Caps and artifacts

| Cap / artifact | Value |
|---|---|
| Structure node cap (chat + docs export) | `MERMAID_NODE_CAP = 40` → `too_large` skip |
| Lifecycle flows / steps | `MERMAID_FLOW_CAP = 4`, `MERMAID_STEP_CAP = 24` |
| `interactive.json` | `mermaid`, `mermaidLifecycle`, optional `*SkipReason` |
| `architecture.md` | Honesty chrome + fenced diagrams beside the JSON |
| CI | `npm run check:mermaid` (Mermaid.js `parse`) |

## Monorepo notes

- Multiple backend roots → **per-chunk** Mermaid, not one mega-diagram.
- Conflicting FE deps → prefer concrete FE over plain `javascript`;
  document which dep won in chunk meta when relevant.
- Unclaimed extension hints without a marker file → **not** promoted to
  a stack; no architecture diagram.

## Not in this matrix (deferred)

`classDiagram` / `erDiagram` from `dataModels`, Mermaid C4, deployment
topology, PlantUML/D2, live Mermaid inside Remotion.
