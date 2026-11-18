# Configuration

## File: `pipeline.config.yaml`

Copy `pipeline.config.example.yaml` to `pipeline.config.yaml` and fill in
real values. **Never commit the real file if it ever contains secrets**
(it shouldn't need to — see Phase 0's security guardrails — but the
example file's own header comment says so explicitly).

Loaded by `src/config/load_config.py: load_config(path)`, which returns
a `PipelineConfig` dataclass. Missing top-level sections (`source`,
`chunking`, `storage`, `security`) raise `ConfigError` immediately
rather than defaulting silently — config correctness is checked once, at
startup, not discovered mid-run.

### `source`

```yaml
source:
  type: git            # git | local_path
  git: "https://github.com/tvw-programming/Alumni-web"
  local_path: null
  prefer: git           # which to use if both are set
```

| Field | Meaning |
|---|---|
| `type` | Declared intent — `git` or `local_path`. Informational; `prefer` is what actually decides. |
| `git` | A git URL. Passed to `source_resolver.resolve_source()`, which clones it (shallow, `--depth 1`) into the configured workdir. |
| `local_path` | A path already on disk — used as-is, no clone. |
| `prefer` | If both `git` and `local_path` are set, which one `PipelineConfig.resolve_source()` returns. |

`PipelineConfig.resolve_source(override=None)` lets a CLI argument (e.g.
`--repo`) win over anything in the file — this is **the** mechanism that
keeps "any repo as input" true in practice: nothing needs to be edited
in `pipeline.config.yaml` to point a single pilot run at a different
repo.

### `detection`

```yaml
detection:
  markers:
    react_or_angular: ["package.json"]
    python: ["requirements.txt", "pyproject.toml", "setup.py"]
    go: ["go.mod"]
    spring_boot: ["pom.xml", "build.gradle"]
    docker: ["Dockerfile", "docker-compose.yml"]
```

Documents the marker files Phase 1 looks for. (Note: `detect_project_type()`
in `src/detect/project_type.py` currently keeps its own `MARKER_FILES`
table as the actual source of truth used at runtime — this config block
mirrors it for documentation/extension purposes. Extending either to a
new stack means adding a marker and a grouping function; see
[`04-phase1-project-type-detection.md`](./04-phase1-project-type-detection.md).)

### `chunking`

```yaml
chunking:
  small_max_lines: 200
  medium_max_lines: 800
  target_narration_seconds: [90, 180]
```

| Field | Meaning |
|---|---|
| `small_max_lines` | A feature at or under this many total lines becomes exactly one chunk. |
| `medium_max_lines` | Above `small_max_lines` and at or under this: one chunk **per file** in the feature. |
| (implicit) `large` | Above `medium_max_lines`: same per-file split, but each oversized file is also flagged `needs_further_split=True` for a future statement-level split (not yet implemented — see gaps doc). |
| `target_narration_seconds` | The narrator's target band (90–180s). Used by `script_builder.py` to decide when a flow beat needs splitting and by the Phase 7 pilot report to measure how many chunks land in-band. |

### `storage`

```yaml
storage:
  mirror_root: "./output/chunks"
  required_fields: ["contentHash", "lastUpdated", "pullRequest"]
```

`mirror_root` is where Phase 4 writes one JSON file per chunk, at
`<mirror_root>/<filePath>.json` — mirroring the source repo's own
directory layout exactly (see Phase 4 doc for why).

### `security`

```yaml
security:
  never_read_patterns:
    - ".env*"
    - "*.pem"
    - "*secrets*"
  secret_scan_before_write: true
```

Mirrors `src/security/guardrails.py`'s `DEFAULT_BLOCKED_PATTERNS` and the
project's non-negotiable rule that secret scanning runs before any
snippet reaches a chunk file. See
[`03-phase0-scaffolding-and-security.md`](./03-phase0-scaffolding-and-security.md).

### `llm` / `audio` / `video`

```yaml
llm:
  provider: anthropic
  api_key_env: ANTHROPIC_API_KEY

audio:
  tts_provider: null   # fill in when Phase 5/6 begins

video:
  fps: 30
  resolution: "1280x720"
```

- `llm` is a placeholder for a future LLM-elaborated narration stage
  (see the Phase 5 doc's "why template, not an LLM call" section and
  the gaps doc) — the implemented pipeline does **not** currently call
  an LLM anywhere; every script is built mechanically.
- `audio.tts_provider` documents that `tts.py` currently hardcodes
  `espeak-ng` as a local, offline, no-API-key engine; swapping in a
  real value here (and a matching branch in `tts.py: synthesize()`)
  is the documented upgrade path to a commercial TTS vendor.
- `video.fps` / `video.resolution` feed `highlight_config.py`'s
  `frame = seconds * fps` conversion and the Remotion composition's
  `width`/`height` (currently `1280x720`, `fps: 30`, matching the
  Remotion `<Composition>` definition in `render-app/src/CodeExplainerChunk.tsx`).

## Running against a different repo

No code change is required. Either:

- edit `pipeline.config.yaml`'s `source.git` (or `source.local_path`), or
- pass the repo path/URL directly to the phase-7 pilot entry point:

```bash
python -m src.pilot.run_pilot /path/to/any/repo /path/to/output [--no-render]
```

`run_pilot()` calls `detect_project_type()` on whatever `repo_root` it is
given — there is no branch anywhere in the pilot, extraction, chunking,
or narration code that checks for "alumni-web" or any other specific
repo name.
