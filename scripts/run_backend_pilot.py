"""Helper for run-local.sh: resolves whatever source `pipeline.config.yaml`
points at (any git URL or local path — see src/detect/source_resolver.py)
and runs the full Phase 7 pilot (src/pilot/run_pilot.py) against it with
one default configuration, no manual CLI arguments required.

When rendering is on (the default), it stages EVERY successfully
-rendered chunk's bundle.json/narration.wav/source file into
render-app/public/chunks/<chunkId>/, plus a manifest.json listing them
in order — the fixed path the FullVideo Remotion composition reads
from (see render-app/src/FullVideo.tsx) to render one continuous video
covering the whole repository, not just a single sample chunk. It also
stages the first chunk into the older render-app/public/sample-chunk/
path for the single-chunk CodeExplainerChunk composition, kept for
quick single-chunk demos/debugging.

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
CHUNKS_DIR = REPO_ROOT / "render-app" / "public" / "chunks"


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


def _stage_one_chunk(chunk_id: str, dest_dir: Path, resolved_root: Path, output_root: Path) -> bool:
    """Copies one chunk's bundle.json/narration.wav/source file into
    dest_dir. Returns False (and copies nothing) if any of the three
    expected files can't be found."""
    file_path = _chunk_id_to_file_path(output_root).get(chunk_id)
    if not file_path:
        return False

    bundle_src = output_root / "render" / chunk_id / "bundle.json"
    audio_src = output_root / "render" / chunk_id / "narration.wav"
    source_src = resolved_root / file_path
    if not (bundle_src.is_file() and audio_src.is_file() and source_src.is_file()):
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bundle_src, dest_dir / "bundle.json")
    shutil.copyfile(audio_src, dest_dir / "narration.wav")
    # The compositions always fetch "source.tsx" by that fixed name,
    # regardless of the real file's extension (Go, Python, ... source
    # displays exactly as well as TSX does — it's shown as plain text).
    shutil.copyfile(source_src, dest_dir / "source.tsx")

    # The file card's own narration. Optional: synthesis may have been
    # skipped, and the card still renders (at its minimum duration)
    # without it, so a missing card.wav must not fail the staging.
    card_src = output_root / "render" / chunk_id / "card.wav"
    if card_src.is_file():
        shutil.copyfile(card_src, dest_dir / "card.wav")
    return True


def _stage_all_chunks(report: dict, resolved_root: Path, output_root: Path) -> list[str]:
    """Stages EVERY successfully-rendered chunk into
    render-app/public/chunks/<chunkId>/, in the same order run_pilot
    processed them, and writes render-app/public/chunks/manifest.json
    listing them in that order — what the FullVideo composition reads
    to render the complete, multi-chunk video. Also stages the first
    one into the older render-app/public/sample-chunk/ path for the
    single-chunk CodeExplainerChunk composition.

    Returns the list of chunkIds actually staged (in order)."""
    render_results = report.get("render")
    if not isinstance(render_results, list):
        return []

    # Start from a clean slate: a previous run's chunks for a
    # different repo/subset shouldn't linger and end up in this run's
    # video.
    if CHUNKS_DIR.is_dir():
        shutil.rmtree(CHUNKS_DIR)

    staged: list[str] = []
    for result in render_results:
        if "error" in result:
            continue
        chunk_id = result["chunkId"]
        if _stage_one_chunk(chunk_id, CHUNKS_DIR / chunk_id, resolved_root, output_root):
            staged.append(chunk_id)

    if staged:
        (CHUNKS_DIR / "manifest.json").write_text(
            json.dumps({"chunkIds": staged}, indent=2), encoding="utf-8",
        )
        _stage_one_chunk(staged[0], SAMPLE_CHUNK_DIR, resolved_root, output_root)

    return staged


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
        staged_chunk_ids = _stage_all_chunks(report, resolved.local_root, output_root)
        if staged_chunk_ids:
            print(f"[backend] Staged {len(staged_chunk_ids)}/{report['chunkCount']} "
                  f"chunk(s) for the full video -> {CHUNKS_DIR}")
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
