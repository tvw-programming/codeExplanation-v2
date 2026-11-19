"""Phase 7 — the full pilot: runs every stage of the pipeline
(detection -> chunking -> extraction+reuse -> schema validation ->
narration -> render bundles) end to end over one repo, and reports
honest pass/fail numbers rather than a single "it works" verdict.

Run directly against a real repo:
    python -m src.pilot.run_pilot /path/to/repo /path/to/output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from src.detect.project_type import detect_project_type
from src.extract.reuse_pipeline import extract_repo_with_reuse
from src.narrate.pipeline import generate_narration_for_repo
from src.narrate.file_overview import build_file_overviews
from src.render.render_pipeline import build_render_bundle
from src.validate.schema_check import validate_records


ProgressFn = Callable[[dict], None]

#: Phases in the order run_pilot reports them. The viewer frontend
#: renders a progress banner from these, so a new phase has to be added
#: here as well as emitted.
PHASES = ("detect", "extract", "validate", "narrate", "render", "done")


def run_pilot(
    repo_root: str | Path,
    output_root: str | Path,
    render: bool = True,
    progress: ProgressFn | None = None,
) -> dict:
    """Runs every stage end to end and returns the pilot report.

    `progress`, when given, is called with a small dict at each phase
    boundary and once per chunk during rendering:
    ``{"phase": ..., "chunksTotal": n, "chunksRendered": k}``. It exists
    so a caller can publish live progress (run_backend_pilot.py writes
    it to status.json for the viewer frontend) during a run that takes
    many minutes. It is advisory only: a callback that raises must not
    take the pipeline down with it.
    """
    repo_root = Path(repo_root)
    output_root = Path(output_root)

    chunks_total = 0
    chunks_rendered = 0

    def emit(phase: str, **extra) -> None:
        if progress is None:
            return
        event = {
            "phase": phase,
            "chunksTotal": chunks_total,
            "chunksRendered": chunks_rendered,
        }
        event.update(extra)
        try:
            progress(event)
        except Exception:  # noqa: BLE001 - progress reporting is never fatal
            pass

    emit("detect")
    project_type = detect_project_type(repo_root)

    emit("extract", projectType=project_type.to_dict())
    records, extraction_stats, chunk_stacks = extract_repo_with_reuse(repo_root, project_type, output_root / "chunks")
    # Run again immediately to prove reuse actually triggers on this repo
    # as-is, not just that the mechanism exists.
    _, reuse_check_stats, _ = extract_repo_with_reuse(repo_root, project_type, output_root / "chunks")

    chunks_total = len(records)

    emit("validate")
    schema_result = validate_records(records)

    emit("narrate")
    narration = generate_narration_for_repo(records)
    narration_seconds = sorted(round(r["script"].estimated_seconds, 1) for r in narration.values())
    in_target_band = sum(1 for r in narration.values() if r["script"].within_target_range)

    # Caller/callee links are a property of the record set as a whole,
    # so they are resolved once here rather than per chunk.
    file_overviews = build_file_overviews(records, repo_root)

    render_results = []
    if render:
        chunks_total = len(narration)
        emit("render")
        for chunk_id, entry in narration.items():
            bundle = build_render_bundle(
                entry["script"],
                output_root / "render" / chunk_id,
                record=entry.get("record"),
                overview=file_overviews.get(chunk_id),
            )
            if "error" in bundle:
                render_results.append({"chunkId": chunk_id, "error": bundle["error"]})
            else:
                cues = bundle["highlightConfig"]
                render_results.append({
                    "chunkId": chunk_id,
                    "durationMs": bundle["durationMs"],
                    "alignmentSource": bundle["alignmentSource"],
                    "numCues": len(cues),
                    "allCuesAssumed": all(c["assumed"] for c in cues) if cues else None,
                })
            chunks_rendered += 1
            emit("render", chunkId=chunk_id)

    report = {
        "repoRoot": str(repo_root),
        "projectType": project_type.to_dict(),
        "chunkCount": len(records),
        "extraction": {
            "firstRun": extraction_stats,
            "secondRunReuseCheck": reuse_check_stats,
            "reuseProvenCorrect": reuse_check_stats["reused"] == reuse_check_stats["total"],
        },
        "schemaValidation": {
            "total": schema_result["total"],
            "valid": schema_result["validCount"],
            "invalid": schema_result["invalidCount"],
            "problems": schema_result["problems"],
        },
        "narration": {
            "chunkCount": len(narration),
            "withinTargetBand": in_target_band,
            "estimatedSecondsDistribution": narration_seconds,
        },
        "render": render_results if render else "skipped",
        "chunkStacks": chunk_stacks,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "pilot_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    emit("done")
    return report


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.pilot.run_pilot <repo_root> <output_root> [--no-render]")
        sys.exit(1)
    repo_root, output_root = sys.argv[1], sys.argv[2]
    render = "--no-render" not in sys.argv
    report = run_pilot(repo_root, output_root, render=render)
    print(json.dumps({k: v for k, v in report.items() if k != "render" or not render}, indent=2)[:2000])


if __name__ == "__main__":
    main()
