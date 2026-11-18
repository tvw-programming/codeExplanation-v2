# JSON Schema Reference

The complete per-chunk record schema, as locked in `docs/json-structure-rules.md`
and implemented by `src/extract/json_builder.py`. This file restates it
grouped by purpose, with the implementation note for each field.

Source of truth: `docs/json-structure-rules.md`. If this file and that
one ever disagree, the `docs/` file wins.

## Identity fields (always required)

| Field | Required | Rule | Implemented by |
|---|---|---|---|
| `chunkId` | yes | Feature-name prefix + short hash of file path + feature name; stable unless the file moves | `chunk_splitter.py: make_chunk_id()` |
| `filePath` | yes | Primary (defining) file, relative, forward slashes | `ChunkPlan.file_path` |
| `featureName` | yes | Short human-readable name from folder/main file | `Feature.name` |
| `projectType` | yes | `{frontend, backend, architecture, dockerized}`; no `"unknown"` fallback | `ProjectType.to_dict()` |
| `language` | yes | Dynamic, from file extension; top ten handled first but not a fixed list | `common.py: detect_language()` |
| `lineRange` | yes | `[start, end]` of the chunk in the primary file; `start <= end` | `[1, len(lines)]` in `json_builder.py` |
| `frameworkOrLibrary` | yes | Array, primary first; only actually-imported libraries, cross-checked against real `package.json`/`go.mod` | `_resolve_frontend_framework_or_library()` / `_resolve_go_framework_or_library()` |

## Content fields (optional, populated when present)

| Field | Required | Rule | Implemented by |
|---|---|---|---|
| `inputs` | no | Props/inputs/request params/function args | `json_builder.py` (from `ts.find_props_interface`) |
| `outputs` | no | Callbacks/return values/response bodies | not yet populated (always `[]`) — see gaps doc |
| `eventHandlers` | no | Every handler, none skipped; assumed+note if uncertain | `ts_extractor.py: extract_event_handlers()` |
| `apiCalls` | no | Postman-style: method, URL/pattern, assumed if URL is a variable | `ts_extractor.py: extract_api_calls()` |
| `importantFunctions` | no | Name/signature/description/lineRange + mandatory 120-line-trimmed snippet | `ts_extractor.py`/`go_extractor.py: extract_functions()` |
| `sideEffects` | no | DB writes, external calls, global state, timers, logging | `extract_side_effects()` (both extractors) |
| `dependencies` | no | Internal file imports, with what each is used for | `json_builder.py` (from internal `imports`) |
| `dataModels` | no | Interfaces/structs/models with mandatory snippet | `ts_extractor.py: extract_interfaces()` / `go_extractor.py: extract_structs()` |
| `routes` | no | Path/type/routing library/protected/handler | `go_extractor.py: extract_routes()` |

## Cross-chunk and confidence fields (always required)

| Field | Required | Rule | Implemented by |
|---|---|---|---|
| `featureMapping` | yes | Other chunks this one mounts/calls/depends on, by chunkId; symmetric; may be empty | `feature_mapping.py: match_calls_to_routes()` + sibling-link pass in `extractor.py` |
| `confidence` | yes | 0–1, from how many claims were marked assumed | `common.py: confidence_from_flags()` |
| `confidenceLevel` | yes | `high` (≥0.85) / `medium` (≥0.6) / `low` | `common.py: confidence_level()` |
| `notes` | no | Anything a reviewer should verify; never spoken in narration | built per-builder in `json_builder.py` |

## Storage fields (Phase 4, required as keys)

| Field | Required | Rule | Implemented by |
|---|---|---|---|
| `contentHash` | yes | SHA-256 of the primary file's raw bytes | `common.py: content_hash()` |
| `lastUpdated` | yes | ISO-8601 UTC timestamp of last analysis | `common.py: now_iso()` |
| `pullRequest` | yes (key); value may be `null` | Full PR URL, when determinable | `pull_request_lookup.py: find_last_pull_request_url()` |

## Narration/render fields (produced outside the stored chunk record)

These live on the Phase 5/6 outputs (`NarrationScript`, `bundle.json`),
not on the stored chunk JSON itself:

| Field | Produced by | Notes |
|---|---|---|
| `purpose` / `connections` / `flow` / `recap` | `script_builder.py: build_narration_script()` | the four locked beats |
| `visualCues` (`VISUAL[HIGHLIGHT:id]` tokens) | `visual_cues.py: generate_visual_cues()` | only for `importantFunctions` entries with a `lineRange` |
| `pronunciationTable` | `pronunciation.py: build_pronunciation_table()` | per-identifier spoken form |
| `highlightConfig` (`fromFrame`/`toFrame`/`assumed`) | `highlight_config.py: build_highlight_config()` | `frame = seconds × fps` |
| `alignmentSource` (`"whisper-cpp"` / `"estimated"`) | `render_pipeline.py: build_render_bundle()` | always honestly recorded |

## Narrator script rules (not a JSON field, governs how the above is spoken)

See `docs/json-structure-rules.md`'s "Narrator script rules" section
for the full prose rule set (four beats, 90–180s target, 130wpm+12.5%
pauses, pronunciation table, continuity glossary, long-function
splitting). [`08-phase5-narration.md`](./08-phase5-narration.md) covers
why each of these is implemented the way it is.
