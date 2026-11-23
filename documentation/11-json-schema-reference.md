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
| `eventHandlers` | no | Every handler, none skipped; assumed+note if uncertain; **`lineRange` is `[bindLine, bindLine]`** | `ts_extractor.py: extract_event_handlers()` + `json_builder.py` |
| `apiCalls` | no | Postman-style: method, URL/pattern, assumed if URL is a variable | `ts_extractor.py: extract_api_calls()` |
| `importantFunctions` | no | Name/signature/description/lineRange + mandatory 120-line-trimmed snippet, plus function-context keys | `ts_extractor.py`/`go_extractor.py: extract_functions()` + `function_context.py` |
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
| `extractorVersion` | yes (implementation) | Integer; currently `11`. Hash match is **not** enough to reuse — version mismatch forces re-analysis | `mirror_store.EXTRACTOR_VERSION` / `json_builder.py` |
| `fileDescription` | no | File header comment; FileCard purpose | `file_header_comment()` |
| `lastUpdated` | yes | ISO-8601 UTC timestamp of last analysis | `common.py: now_iso()` |
| `pullRequest` | yes (key); value may be `null` | Full PR URL, when determinable | `pull_request_lookup.py: find_last_pull_request_url()` |

## Extra function-context keys (on each `importantFunctions` entry)

Implemented by `function_context.build_function_context()`:

`description`, `descriptionSource` (`"doc-comment"` or null),
`exported`, `calledBy`, `calls`, `params`, `raisesError`, `isAsync`,
`reactHooks`, `apiCalls` (in-range), `sideEffects` (in-range),
`lineCount`. Plus snippet flags `secretsRedacted`, `truncated`,
`continuationNote`.

`outputs` is always `[]` (known gap). Empty Angular records remain
schema-valid with empty content lists; visuals go `unavailable` rather
than inventing a graph (doc 17).

## Visual envelope (on the stored chunk record after `attach_visuals`)

| Field | Rule | Implemented by |
|---|---|---|
| `fidelity` | `regex` / `syntax` / `typed` | stack builders + `pipeline.attach_visuals` |
| `visualAvailability` | per-capability `available` / `partial` / `unavailable` + reasons | `availability.py` / `pipeline.py` |
| `visualGraph` | structure graph or **`null`** (never invented) | `graph_builder.py` |
| `lifecycleFlows` | developer-centric flows; may be `[]` | `lifecycle_builder.py` |
| `visualTheme` | brand tokens + `logoPath` | `theme.py` |
| `securityFlags` | optional path/middleware/unsafe flags | `security_flags.py` |
| `extractorVersion` | currently `11` | `mirror_store.EXTRACTOR_VERSION` |

## Narration/render fields (produced outside the stored chunk record)

These live on the Phase 5/6 outputs (`NarrationScript`, `bundle.json`),
not on the stored chunk JSON itself:

| Field | Produced by | Notes |
|---|---|---|
| `purpose` / `connections` / item beats / `recap` | `script_builder.py: build_beats()` / `build_item_beats()` | four-beat *structure*; flow is per-item spoken text, not "The X function runs next" |
| `visualCues` (`VISUAL[HIGHLIGHT:id]` tokens) | `visual_cues.py: generate_visual_cues()` | `importantFunctions`, `eventHandlers`, and `routes` with a `lineRange` |
| `pronunciationTable` | `pronunciation.py: build_pronunciation_table()` | built; **not applied** to TTS |
| `highlightConfig` (`fromFrame`/`toFrame`/`assumed`) | `highlight_config.py: build_highlight_config()` | `frame = seconds × fps`; CSS bar in `ChunkView`, not Shiki |
| `alignmentSource` | `render_pipeline.py: build_render_bundle()` | live value **`"measured-beats"`**; leftover modules may still emit `"whisper-cpp"` / `"estimated"` |
| `ttsEngine` | `tts.py` via the bundle | `piper:en_IN-ljspeech` or `espeak-ng:en-us` |
| `fileOverview` | `file_overview.py` | FileCard payload (callers, layer, risks, `unavailable`) |
| `cardNarration` | `render_pipeline._build_card_narration()` | spoken intro over the card (`card.wav`) |
| `treeNarration` / `lifecycleNarration` / `breakdownNarration` | `render_pipeline.py` | measured-beat voiceovers for visual clips; omitted → FullVideo skips that segment |
| `narrationSegments` | `narration_segments.py` | per-beat start/end frames from measured placements |

## Narrator script rules (not a JSON field, governs how the above is spoken)

See `docs/json-structure-rules.md`'s "Narrator script rules" section
for the full prose rule set (four beats, 90–180s target, 130wpm+12.5%
pauses, pronunciation table, continuity glossary, long-function
splitting). [`08-phase5-narration.md`](./08-phase5-narration.md) covers
why each of these is implemented the way it is.
