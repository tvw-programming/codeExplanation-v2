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

`detection`, `llm`, and `audio` are loaded into
`PipelineConfig.detection` / `PipelineConfig.raw` and **are not read**
by the live pipeline. `video.phaseStyle` **is** read at startup and
embedded on Remotion manifests at staging time. `video.fps` /
`video.resolution` remain unused.

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

### `detection` (unused at runtime)

```yaml
detection:
  markers:
    js_ecosystem: ["package.json"]
    python: ["requirements.txt", "pyproject.toml", "setup.py"]
    go: ["go.mod"]
    spring_boot: ["pom.xml", "build.gradle"]
    rust: ["Cargo.toml"]
    docker: ["Dockerfile", "docker-compose.yml"]
```

This block is **documentation-only**. `detect_project_type()` in
`src/detect/project_type.py` uses its own `MARKER_FILES` /
`DOCKER_MARKERS` tables. Extending detection means editing that Python
table (and a grouping function); editing this YAML does nothing.

**Code table** (`MARKER_FILES` + `DOCKER_MARKERS`):

| Stack key | Marker files in code |
|---|---|
| `js_ecosystem` | `package.json` (flavored to react/angular/vue/solid/qwik/javascript; `express` → backend) |
| `python` | `requirements.txt`, `pyproject.toml`, `setup.py` |
| `go` | `go.mod` |
| `spring_boot` | `pom.xml`, `build.gradle`, **`build.gradle.kts`** (YAML example omits `.kts`) |
| `rust` | `Cargo.toml` |
| Docker (separate flag) | `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml` |

See [`04-phase1-project-type-detection.md`](./04-phase1-project-type-detection.md).

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
| (implicit) `large` | Above `medium_max_lines`: same per-file split, but each oversized file is also flagged `needs_further_split=True` for a future statement-level split (not yet implemented — the flag is unused). |
| `target_narration_seconds` | The narrator's target band (90–180s). Used by `script_builder.py` to classify `within_target_range` and by the Phase 7 pilot report. The Alumni-web 2/22 figure is a **historical** snapshot of the old short templates; re-measure rather than citing it as current. |

### `storage`

```yaml
storage:
  mirror_root: "./output/chunks"
  required_fields: ["contentHash", "lastUpdated", "pullRequest"]
```

`mirror_root` is where Phase 4 writes one JSON file per chunk, at
`<mirror_root>/<filePath>.json` — mirroring the source repo's own
directory layout exactly (see Phase 4 doc for why). Reuse also keys off
`extractorVersion` (currently `4` in `mirror_store.py`), which is not a
config field.

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

### `llm` / `audio` (unused at runtime)

```yaml
llm:
  provider: anthropic
  api_key_env: ANTHROPIC_API_KEY

audio:
  tts_provider: null   # unused; live path is Piper then espeak-ng
```

These sections are stored on `PipelineConfig.raw` and **never read**.

- `llm` is a **roadmap** placeholder for an LLM-elaborated narration
  stage. The implemented pipeline does not call an LLM anywhere; every
  script is built mechanically. See the Phase 5 doc and the gaps doc.
- `audio.tts_provider` is unused. Live engines are **Piper**
  (`piper:en_IN-ljspeech`) then **espeak-ng** (`espeak-ng:en-us`). Which
  one actually ran is recorded on the render bundle as `ttsEngine`.

### `video` (`phaseStyle` live; fps/resolution unused)

```yaml
video:
  fps: 30
  resolution: "1280x720"
  phaseStyle:
    fileCard: classic            # classic | fancy
    componentTree: classic
    lifecycle: classic
    chunkView: classic
    visualBreakdown: classic
    architectureDocs: classic
```

| Field | Meaning |
|---|---|
| `fps` / `resolution` | Unused. Remotion hardcodes **30 fps** and **1280×720**; `highlight_config.py` defaults `fps=30`. |
| `phaseStyle` | Loaded by `src/config/phase_style.py` into `PipelineConfig.phase_style`. **Every key defaults to `classic`** when omitted. Values must be `classic` or `fancy` only; unknown keys fail closed. Staging embeds the resolved map on chunk manifests. `FullVideo` passes each key into the matching clip; `classic` keeps today's layout. |

## Piper voice cache

`./run-local.sh` (when rendering is on) runs
`python scripts/ensure_piper_voice.py` once. That downloads ~64MB of
Indian-English Piper model files from Hugging Face into
`.cache/piper-voices/en_IN/` (`en_IN-ljspeech.onnx` + config JSON).

- Non-fatal: if Hugging Face is blocked, the script warns and exits 0;
  `tts.py` falls back to espeak-ng.
- Not a per-render network call — same shape as `npm install`.
- Licensing: Piper engine is GPL-3.0-or-later; the voice model is tagged
  AGPL-3.0. Both are invoked as subprocesses (see `src/render/tts.py`).

espeak-ng remains a **required** system binary even when Piper is
present (fallback + `run-local.sh` preflight).

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
