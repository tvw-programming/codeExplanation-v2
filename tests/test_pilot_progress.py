"""run_pilot's progress callback — the signal the viewer frontend shows
while a multi-minute run is in flight.

The callback must report phases in the order they happen, must not
change anything about a run that does not pass one, and must never be
able to take the pipeline down.
"""

import json
import shutil

import pytest

from src.pilot.run_pilot import PHASES, run_pilot

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None, reason="espeak-ng not installed in this environment"
)


def _build_repo(root):
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
    features_dir = root / "src" / "features" / "widgets"
    features_dir.mkdir(parents=True)
    (features_dir / "WidgetList.tsx").write_text(
        "export default function WidgetList() {\n"
        "  return <div>widgets</div>;\n"
        "}\n"
    )


def test_progress_reports_each_phase_in_order(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)

    events = []
    run_pilot(repo, tmp_path / "output", render=False, progress=events.append)

    phases = [event["phase"] for event in events]
    assert phases == ["detect", "extract", "validate", "narrate", "done"]
    # Rendering is off, so no render phase is announced.
    assert "render" not in phases
    assert all(phase in PHASES for phase in phases)


def test_progress_carries_the_chunk_count_once_extraction_has_run(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)

    events = []
    run_pilot(repo, tmp_path / "output", render=False, progress=events.append)

    by_phase = {event["phase"]: event for event in events}
    # Nothing is known before extraction; afterwards the count is real.
    assert by_phase["detect"]["chunksTotal"] == 0
    assert by_phase["narrate"]["chunksTotal"] == 1
    assert by_phase["done"]["chunksRendered"] == 0


def test_a_callback_that_raises_does_not_fail_the_run(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)

    def explode(_event):
        raise RuntimeError("the progress consumer went away")

    report = run_pilot(repo, tmp_path / "output", render=False, progress=explode)

    assert report["chunkCount"] == 1


def test_omitting_the_callback_leaves_the_report_identical(tmp_path):
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    for repo in (repo_a, repo_b):
        repo.mkdir()
        _build_repo(repo)

    without = run_pilot(repo_a, tmp_path / "out-a", render=False)
    with_cb = run_pilot(repo_b, tmp_path / "out-b", render=False, progress=lambda _e: None)

    # repoRoot differs by construction; everything else must match.
    without.pop("repoRoot")
    with_cb.pop("repoRoot")
    assert without == with_cb


@requires_espeak
def test_render_phase_counts_chunks_as_they_are_rendered(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)

    events = []
    run_pilot(repo, tmp_path / "output", render=True, progress=events.append)

    render_events = [e for e in events if e["phase"] == "render"]
    # One announcement of the phase, then one per finished chunk.
    assert len(render_events) == 2
    assert render_events[0]["chunksRendered"] == 0
    assert render_events[-1]["chunksRendered"] == 1
    assert render_events[-1]["chunksTotal"] == 1
