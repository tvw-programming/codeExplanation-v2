import json
import shutil

import pytest

from src.pilot.run_pilot import run_pilot

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None, reason="espeak-ng not installed in this environment"
)


def _build_repo(root):
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
    features_dir = root / "src" / "features" / "widgets"
    features_dir.mkdir(parents=True)
    (features_dir / "WidgetList.tsx").write_text(
        "export default function WidgetList() {\n"
        "  const handleClick = () => {\n"
        "    console.log('clicked');\n"
        "  };\n"
        "  return <div onClick={handleClick}>widgets</div>;\n"
        "}\n"
    )


def test_run_pilot_without_render_covers_detection_through_narration(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)
    output = tmp_path / "output"

    report = run_pilot(repo, output, render=False)

    assert report["chunkCount"] == 1
    assert report["extraction"]["reuseProvenCorrect"] is True
    assert report["schemaValidation"]["total"] == 1
    assert report["narration"]["chunkCount"] == 1
    assert report["render"] == "skipped"
    assert (output / "pilot_report.json").is_file()


@requires_espeak
def test_run_pilot_with_render_produces_a_real_bundle_per_chunk(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo(repo)
    output = tmp_path / "output"

    report = run_pilot(repo, output, render=True)

    assert len(report["render"]) == 1
    assert "error" not in report["render"][0]
    assert report["render"][0]["durationMs"] > 0
