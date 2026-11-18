"""Helper for run-local.sh: resolves whatever source `pipeline.config.yaml`
points at (any git URL or local path — see src/detect/source_resolver.py)
and runs the full Phase 7 pilot (src/pilot/run_pilot.py) against it with
one default configuration, no manual CLI arguments required.

When rendering is on (the default), it also stages one successfully
-rendered chunk's bundle.json/narration.wav/source file into
render-app/public/sample-chunk/ — the exact fixed path the
CodeExplainerChunk Remotion composition reads from (see
render-app/src/CodeExplainerChunk.tsx) — so run-local.sh's subsequent
`npx remotion render` step always has real data to render, for
whichever repo pipeline.config.yaml happens to point at, not just the
one chunk that was committed as a fixed proof sample.

Usage (always run from the repo root, which run-local.sh does for you):
    python scripts/run_backend_pilot.py [--no-render]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config.load_config import load_config, ConfigError  # noqa: E402
from src.detect.source_resolver import resolve_source, SourceResolutionError  # noqa: E402
from src.pilot.run_pilot import run_pilot  # noqa: E402

SAMPLE_CHUNK_DIR = REPO_ROOT / "render-app" / "public" / "sample-chunk"


def _chunk_id_to_file_path(output_root: Path) -> dict[str, str]:
    """Reads every mirrored chunk record Phase 4 wrote under
    <output_root>/chunks/ and maps chunkId -> the real source filePath,
    so a render result (identified only by chunkId) can be traced back
    to the actual source file to show in the video."""
    mapping: dict[str, str] = {}
    chunks_dir = output_root / "chunks"
    if not chunks_dir.is_dir():
        return mapping
    for json_path in chunks_dir.rglob("*.json"):
        try:
            record = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        chunk_id = record.get("chunkId")
        file_path = record.get("filePath")
        if chunk_id and file_path:
            mapping[chunk_id] = file_path
    return mapping


def _stage_sample_chunk(report: dict, resolved_root: Path, output_root: Path) -> str | None:
    """Picks the first chunk whose render bundle has no error, and
    copies its bundle.json/narration.wav/source file to
    render-app/public/sample-chunk/ (the fixed path the Remotion
    composition reads). Returns the chosen chunkId, or None if nothing
    rendered successfully."""
    render_results = report.get("render")
    if not isinstance(render_results, list):
        return None

    chosen = next((r for r in render_results if "error" not in r), None)
    if chosen is None:
        return None
    chunk_id = chosen["chunkId"]

    file_path = _chunk_id_to_file_path(output_root).get(chunk_id)
    if not file_path:
        return None

    bundle_src = output_root / "render" / chunk_id / "bundle.json"
    audio_src = output_root / "render" / chunk_id / "narration.wav"
    source_src = resolved_root / file_path
    if not (bundle_src.is_file() and audio_src.is_file() and source_src.is_file()):
        return None

    SAMPLE_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bundle_src, SAMPLE_CHUNK_DIR / "bundle.json")
    shutil.copyfile(audio_src, SAMPLE_CHUNK_DIR / "narration.wav")
    # The composition always fetches "source.tsx" by that fixed name,
    # regardless of the real file's extension (Go, Python, ... source
    # displays exactly as well as TSX does — it's shown as plain text).
    shutil.copyfile(source_src, SAMPLE_CHUNK_DIR / "source.tsx")
    return chunk_id


def main() -> int:
    render = "--no-render" not in sys.argv[1:]

    config_path = REPO_ROOT / "pipeline.config.yaml"
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"[backend] Config error: {exc}", file=sys.stderr)
        return 1

    source_value = config.resolve_source()
    workdir = REPO_ROOT / ".local-run" / "source"
    output_root = REPO_ROOT / ".local-run" / "output"

    print(f"[backend] Source (from pipeline.config.yaml): {source_value}")
    try:
        resolved = resolve_source(source_value, workdir)
    except SourceResolutionError as exc:
        print(f"[backend] Could not resolve source: {exc}", file=sys.stderr)
        return 1

    print(f"[backend] Resolved to local directory: {resolved.local_root}")
    print(f"[backend] Running the full pipeline (render={'on' if render else 'off'}) ...")

    report = run_pilot(resolved.local_root, output_root, render=render)

    print(f"[backend] Done. {report['chunkCount']} chunk(s) processed.")
    print(f"[backend] Schema validation: {report['schemaValidation']['valid']}/"
          f"{report['schemaValidation']['total']} valid.")
    print(f"[backend] Full report written to: {output_root / 'pilot_report.json'}")

    if render:
        staged_chunk_id = _stage_sample_chunk(report, resolved.local_root, output_root)
        if staged_chunk_id:
            print(f"[backend] Staged chunk '{staged_chunk_id}' for video rendering "
                  f"-> {SAMPLE_CHUNK_DIR}")
        else:
            print("[backend] No successfully-rendered chunk to stage for video "
                  "rendering.", file=sys.stderr)
            render_results = report.get("render")
            first_error = None
            if isinstance(render_results, list):
                first_error = next((r.get("error") for r in render_results if "error" in r), None)
            if first_error:
                print(f"[backend] Render error: {first_error}", file=sys.stderr)
                if "espeak-ng" in first_error:
                    print("[backend] Install espeak-ng (e.g. `brew install espeak-ng` on "
                          "macOS, `apt-get install espeak-ng` on Debian/Ubuntu) and re-run, "
                          "or use --no-render to skip TTS/video.", file=sys.stderr)
            else:
                print("[backend] See pilot_report.json's render section for details.",
                      file=sys.stderr)
            return 2
    else:
        print("[backend] Rendering was skipped (--no-render); run-local.sh will "
              "not be able to produce output.mp4 from this run.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
