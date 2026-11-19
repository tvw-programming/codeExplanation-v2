"""status.json — the live progress the viewer polls during a run.

The file is rewritten repeatedly while a browser reads it, so the two
things that matter are that a reader always sees a complete document
and that a failure to publish never breaks the pipeline.
"""

import json

from src.pilot.status import PHASE_LABELS, StatusWriter


def test_start_publishes_a_complete_document(tmp_path):
    path = tmp_path / "status.json"

    StatusWriter(path).start(source="https://example.test/repo.git")

    state = json.loads(path.read_text())
    assert state["phase"] == "starting"
    assert state["done"] is False
    assert state["error"] is None
    assert state["source"] == "https://example.test/repo.git"
    assert state["videos"] == {}
    assert state["startedAt"] and state["updatedAt"]


def test_progress_events_update_phase_and_counts(tmp_path):
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()

    writer.on_progress({"phase": "render", "chunksTotal": 22, "chunksRendered": 7})

    state = json.loads(path.read_text())
    assert state["phase"] == "render"
    assert state["phaseLabel"] == PHASE_LABELS["render"]
    assert (state["chunksTotal"], state["chunksRendered"]) == (22, 7)


def test_start_discards_a_previous_run(tmp_path):
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()
    writer.mark_video_ready("go")
    writer.finish()

    writer.start()

    state = json.loads(path.read_text())
    assert state["videos"] == {}
    assert state["done"] is False


def test_declaring_stacks_preserves_videos_already_rendered(tmp_path):
    """run-local.sh re-declares the stack set mid-run; a video that has
    already finished must not go back to unwatchable."""
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()
    writer.set_stacks({
        "react": {"composition": "StackVideo-react", "file": "video-react.mp4"},
        "go": {"composition": "StackVideo-go", "file": "video-go.mp4"},
    })
    writer.mark_video_ready("go")

    writer.set_stacks({
        "react": {"composition": "StackVideo-react", "file": "video-react.mp4"},
        "go": {"composition": "StackVideo-go", "file": "video-go.mp4"},
    })

    state = json.loads(path.read_text())
    assert state["videos"]["go"]["ready"] is True
    assert state["videos"]["react"]["ready"] is False
    assert state["stacks"] == ["go", "react"]


def test_mark_video_ready_works_for_a_stack_never_declared(tmp_path):
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()

    writer.mark_video_ready("python", "video-python-preview.mp4")

    state = json.loads(path.read_text())
    assert state["videos"]["python"] == {
        "composition": "StackVideo-python",
        "file": "video-python-preview.mp4",
        "ready": True,
    }


def test_failure_is_recorded_and_terminal(tmp_path):
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()

    writer.fail("espeak-ng is not installed")

    state = json.loads(path.read_text())
    assert state["phase"] == "failed"
    assert state["done"] is True
    assert state["error"] == "espeak-ng is not installed"


def test_every_write_leaves_valid_json_behind(tmp_path):
    """Writes go through a temp file and os.replace, so a reader never
    catches a half-written document."""
    path = tmp_path / "status.json"
    writer = StatusWriter(path)
    writer.start()

    for i in range(25):
        writer.on_progress({"phase": "render", "chunksTotal": 25, "chunksRendered": i})
        json.loads(path.read_text())

    # No temp files left behind.
    assert [p.name for p in tmp_path.iterdir()] == ["status.json"]


def test_an_unwritable_destination_does_not_raise(tmp_path):
    """Publishing progress is never worth failing a run over."""
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")

    writer = StatusWriter(blocked / "status.json")
    writer.start()
    writer.update(phase="render")
    writer.finish()


def test_update_on_a_missing_file_starts_a_run(tmp_path):
    path = tmp_path / "status.json"

    state = StatusWriter(path).update(phase="rendering")

    assert state["phase"] == "rendering"
    assert state["phaseLabel"] == PHASE_LABELS["rendering"]
    assert json.loads(path.read_text())["phase"] == "rendering"
