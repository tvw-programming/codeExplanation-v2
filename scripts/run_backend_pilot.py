"""Helper for run-local.sh: resolves whatever source `pipeline.config.yaml`
points at (any git URL or local path — see src/detect/source_resolver.py)
and runs the full Phase 7 pilot (src/pilot/run_pilot.py) against it with
one default configuration, no manual CLI arguments required.

When rendering is on (the default), it stages EVERY successfully
-rendered chunk's bundle.json/narration.wav/source file into
render-app/public/chunks/<stack>/<chunkId>/, grouped by detected stack
(react, go, python, spring_boot, etc.), with a separate manifest.json
per stack at render-app/public/chunks/<stack>/manifest.json. Each stack
produces its own video file (output/video-<stack>.mp4). A combined
manifest.json is also written at render-app/public/chunks/manifest.json
listing all stacks for the FullVideo composition (backward compat).

The first chunk is still staged into the older
render-app/public/sample-chunk/ path for the single-chunk
CodeExplainerChunk composition, kept for quick demos/debugging.

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
from src.config.phase_style import (  # noqa: E402
    combined_manifest_payload,
    stack_manifest_payload,
)
from src.detect.source_resolver import resolve_source, SourceResolutionError  # noqa: E402
from src.pilot.project_manifest import write_project_manifest  # noqa: E402
from src.pilot.run_pilot import run_pilot  # noqa: E402
from src.pilot.status import StatusWriter  # noqa: E402

SAMPLE_CHUNK_DIR = REPO_ROOT / "render-app" / "public" / "sample-chunk"
CHUNKS_DIR = REPO_ROOT / "render-app" / "public" / "chunks"
PROJECT_MANIFEST = CHUNKS_DIR / "project.json"


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

    # Visual clip audio (Q4 measured-beat). Optional per Q5 skip rules —
    # FullVideo omits segments when these files / bundle fields are absent.
    render_dir = output_root / "render" / chunk_id
    for visual_wav in ("tree.wav", "lifecycle.wav", "breakdown.wav"):
        src = render_dir / visual_wav
        if src.is_file():
            shutil.copyfile(src, dest_dir / visual_wav)
    return True


def _bundle_has_visual_clips(bundle_path: Path) -> bool:
    """True when the staged bundle carries a graph (or flows) for FullVideo."""
    if not bundle_path.is_file():
        return False
    try:
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("visualGraph") and (
        data.get("treeNarration") or data.get("breakdownNarration")
    ):
        return True
    if (data.get("lifecycleFlows") or []) and data.get("lifecycleNarration"):
        return True
    return False


def _prioritize_visual_chunks(stack_dir: Path, chunk_ids: list[str]) -> list[str]:
    """Put chunks with tree/lifecycle/breakdown first (stable within each group).

    Dependency-first extract order often parks Go Fiber's only route_tree
    file (e.g. cmd/server/main.go) after ~25+ minutes of handler/repo
    chunks that correctly have visualAvailability=unavailable. --preview
    then never reaches the graph. Playback order does not affect already-
    baked narration scripts, so reordering the Remotion manifest is safe.
    """
    with_visuals: list[str] = []
    without: list[str] = []
    for cid in chunk_ids:
        if _bundle_has_visual_clips(stack_dir / cid / "bundle.json"):
            with_visuals.append(cid)
        else:
            without.append(cid)
    return with_visuals + without


def _stage_all_chunks(
    report: dict,
    resolved_root: Path,
    output_root: Path,
    phase_style: dict[str, str],
) -> dict[str, list[str]]:
    """Stages EVERY successfully-rendered chunk into
    render-app/public/chunks/<stack>/<chunkId>/, grouped by the stack
    each chunk belongs to, and writes one manifest.json per stack at
    render-app/public/chunks/<stack>/manifest.json. A combined
    manifest.json at render-app/public/chunks/manifest.json is also
    written for backward compatibility (the FullVideo composition).

    Also stages the first chunk into the older
    render-app/public/sample-chunk/ path for the single-chunk
    CodeExplainerChunk composition.

    Returns {stack: [chunkId, ...]} of actually staged chunks."""
    render_results = report.get("render")
    if not isinstance(render_results, list):
        return {}

    chunk_stacks: dict[str, str] = report.get("chunkStacks", {})

    # Start from a clean slate: a previous run's chunks for a
    # different repo/subset shouldn't linger and end up in this run's
    # video.
    if CHUNKS_DIR.is_dir():
        shutil.rmtree(CHUNKS_DIR)

    # Stage each chunk under its stack subdirectory.
    staged_by_stack: dict[str, list[str]] = {}
    first_staged: str | None = None

    for result in render_results:
        if "error" in result:
            continue
        chunk_id = result["chunkId"]
        # Remotion composition IDs allow only a-z, A-Z, 0-9, CJK and
        # hyphens — no underscores. Sanitize the stack name so the
        # directory matches the composition ID (e.g. spring_boot ->
        # spring-boot).
        stack = chunk_stacks.get(chunk_id, "unknown").replace("_", "-")
        stack_dir = CHUNKS_DIR / stack
        if _stage_one_chunk(chunk_id, stack_dir / chunk_id, resolved_root, output_root):
            staged_by_stack.setdefault(stack, []).append(chunk_id)
            if first_staged is None:
                first_staged = chunk_id
                # Also keep a flat symlink/copy at CHUNKS_DIR/<chunkId>
                # so the combined manifest's paths still resolve.
                _stage_one_chunk(chunk_id, CHUNKS_DIR / chunk_id, resolved_root, output_root)

    # Write per-stack manifests — visual-bearing chunks first so
    # StackVideo-<stack> and --preview show trees/lifecycle early.
    for stack, chunk_ids in list(staged_by_stack.items()):
        stack_dir = CHUNKS_DIR / stack
        stack_dir.mkdir(parents=True, exist_ok=True)
        ordered = _prioritize_visual_chunks(stack_dir, chunk_ids)
        staged_by_stack[stack] = ordered
        n_visual = sum(
            1 for cid in ordered
            if _bundle_has_visual_clips(stack_dir / cid / "bundle.json")
        )
        if n_visual and ordered and ordered[0] != chunk_ids[0]:
            print(
                f"[backend] {stack}: prioritized {n_visual} visual chunk(s) "
                f"first in StackVideo-{stack} (was buried after non-visual files).",
                flush=True,
            )
        (stack_dir / "manifest.json").write_text(
            json.dumps(
                stack_manifest_payload(stack, ordered, phase_style),
                indent=2,
            ),
            encoding="utf-8",
        )

    # Write combined manifest for backward compatibility (FullVideo).
    all_staged = [cid for ids in staged_by_stack.values() for cid in ids]
    if all_staged:
        # Stage ALL chunks flat under CHUNKS_DIR too so the combined
        # manifest resolves (FullVideo reads chunks/<chunkId>/).
        for result in render_results:
            if "error" in result:
                continue
            chunk_id = result["chunkId"]
            if chunk_id in {c for ids in staged_by_stack.values() for c in ids}:
                dest = CHUNKS_DIR / chunk_id
                if not dest.is_dir():
                    _stage_one_chunk(chunk_id, dest, resolved_root, output_root)

        stacks_map = {
            stack: chunk_ids for stack, chunk_ids in staged_by_stack.items()
        }
        (CHUNKS_DIR / "manifest.json").write_text(
            json.dumps(
                combined_manifest_payload(all_staged, stacks_map, phase_style),
                indent=2,
            ),
            encoding="utf-8",
        )

    # Legacy single-chunk sample — prefer a visual-bearing chunk when one exists.
    sample_id = first_staged
    for stack, chunk_ids in staged_by_stack.items():
        if chunk_ids and _bundle_has_visual_clips(CHUNKS_DIR / stack / chunk_ids[0] / "bundle.json"):
            sample_id = chunk_ids[0]
            break
    if sample_id:
        _stage_one_chunk(sample_id, SAMPLE_CHUNK_DIR, resolved_root, output_root)

    # Describe the analysed project for the viewer frontend: which
    # stacks exist and which of them is the frontend. Derived from
    # Phase 1 detection, so a Vue + Spring Boot repo needs no change
    # here (see src/pilot/project_manifest.py).
    if staged_by_stack:
        write_project_manifest(
            PROJECT_MANIFEST,
            resolved_root,
            report.get("projectType") or {},
            staged_by_stack,
        )
        print(f"[backend]   -> {PROJECT_MANIFEST}")

    return staged_by_stack


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

    # Publish live progress for the viewer frontend, which is already
    # running by now (run-local.sh starts it first) and polls this file.
    status = StatusWriter()
    status.start(source=source_value, render=render)

    print(f"[backend] Source (from pipeline.config.yaml): {source_value}")
    try:
        resolved = resolve_source(source_value, workdir)
    except SourceResolutionError as exc:
        print(f"[backend] Could not resolve source: {exc}", file=sys.stderr)
        status.fail(f"Could not resolve source: {exc}")
        return 1

    print(f"[backend] Resolved to local directory: {resolved.local_root}")
    print(f"[backend] Running the full pipeline (render={'on' if render else 'off'}) ...")

    report = run_pilot(
        resolved.local_root, output_root, render=render, progress=status.on_progress
    )

    print(f"[backend] Done. {report['chunkCount']} chunk(s) processed.")
    print(f"[backend] Schema validation: {report['schemaValidation']['valid']}/"
          f"{report['schemaValidation']['total']} valid.")
    print(f"[backend] Full report written to: {output_root / 'pilot_report.json'}")

    if render:
        status.update(phase="staging")
        staged_by_stack = _stage_all_chunks(
            report,
            resolved.local_root,
            output_root,
            config.phase_style,
        )
        total_staged = sum(len(ids) for ids in staged_by_stack.values())
        if staged_by_stack:
            stacks_summary = ", ".join(
                f"{stack}({len(ids)})" for stack, ids in staged_by_stack.items()
            )
            print(f"[backend] Staged {total_staged}/{report['chunkCount']} "
                  f"chunk(s) across {len(staged_by_stack)} stack(s): {stacks_summary}")
            for stack in staged_by_stack:
                print(f"[backend]   -> {CHUNKS_DIR / stack}/manifest.json")
            # The videos do not exist yet — run-local.sh flips each
            # `ready` as its render finishes.
            status.set_stacks({
                stack: {
                    "composition": f"StackVideo-{stack}",
                    "file": f"video-{stack}.mp4",
                    "ready": False,
                }
                for stack in staged_by_stack
            })
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
            status.fail(first_error or "No successfully-rendered chunk to stage.")
            return 2
    else:
        print("[backend] Rendering was skipped (--no-render); run-local.sh will "
              "not be able to produce output.mp4 from this run.")
        status.finish()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
