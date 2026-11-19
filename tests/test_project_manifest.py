"""project.json — how the viewer learns which technologies to show and
which side each belongs on.

The split must come from Phase 1 detection, not from a list of stack
names baked into the code: these tests point it at stacks the project
has never been run against to prove that.
"""

import json

from src.pilot.project_manifest import (
    build_project_manifest,
    role_for_stack,
    write_project_manifest,
)


def test_frontend_and_backend_roles_come_from_detection():
    project_type = {"frontend": "react", "backend": ["go"], "architecture": "monolith"}

    assert role_for_stack("react", project_type) == "frontend"
    assert role_for_stack("go", project_type) == "backend"


def test_roles_are_not_hardcoded_to_react_and_go():
    """A Vue + Spring Boot repo must split the same way, with no code
    change here — that is the whole point of reading detection."""
    project_type = {"frontend": "vue", "backend": ["spring_boot"], "architecture": "monolith"}

    assert role_for_stack("vue", project_type) == "frontend"
    # Staged directories hyphenate (Remotion composition ids disallow
    # underscores), detection does not — they must still match.
    assert role_for_stack("spring-boot", project_type) == "backend"
    # And the names this project usually sees are now just "other".
    assert role_for_stack("react", project_type) == "other"
    assert role_for_stack("go", project_type) == "other"


def test_an_undetected_stack_is_other_rather_than_guessed():
    project_type = {"frontend": None, "backend": [], "architecture": "unknown"}

    assert role_for_stack("unknown", project_type) == "other"
    assert role_for_stack("", project_type) == "other"


def test_manifest_orders_frontend_first_then_backends_then_others(tmp_path):
    manifest = build_project_manifest(
        tmp_path / "Alumni-web",
        {"frontend": "react", "backend": ["go"], "architecture": "monolith"},
        {"go": ["a", "b"], "unknown": ["c"], "react": ["d", "e", "f"]},
    )

    assert [s["name"] for s in manifest["stacks"]] == ["react", "go", "unknown"]
    assert [s["role"] for s in manifest["stacks"]] == ["frontend", "backend", "other"]
    assert manifest["repoName"] == "Alumni-web"


def test_each_stack_carries_its_video_and_composition():
    manifest = build_project_manifest(
        "/tmp/repo",
        {"frontend": "react", "backend": ["go"]},
        {"react": ["a"], "go": ["b"]},
    )

    react = next(s for s in manifest["stacks"] if s["name"] == "react")
    assert react["video"] == "video-react.mp4"
    assert react["previewVideo"] == "video-react-preview.mp4"
    assert react["composition"] == "StackVideo-react"
    assert react["chunkCount"] == 1


def test_a_single_stack_repo_produces_exactly_one_section():
    manifest = build_project_manifest(
        "/tmp/api",
        {"frontend": None, "backend": ["python"], "architecture": "monolith"},
        {"python": ["a", "b"]},
    )

    assert len(manifest["stacks"]) == 1
    assert manifest["stacks"][0]["role"] == "backend"


def test_a_stack_with_nothing_staged_is_absent():
    """A detected stack whose chunks all failed to render must not get a
    tree the viewer cannot play anything from."""
    manifest = build_project_manifest(
        "/tmp/repo",
        {"frontend": "react", "backend": ["go"]},
        {"react": ["a"]},
    )

    assert [s["name"] for s in manifest["stacks"]] == ["react"]


def test_write_project_manifest_writes_readable_json(tmp_path):
    dest = tmp_path / "chunks" / "project.json"

    written = write_project_manifest(
        dest, tmp_path / "repo", {"frontend": "react", "backend": ["go"]}, {"react": ["a"]}
    )

    assert dest.is_file()
    assert json.loads(dest.read_text()) == written
