"""Proves the Phase 4 reuse rule actually skips re-extraction on an
unchanged file, and re-extracts only the one file that changed — not
just that the hash-comparison function returns the right boolean."""

import json
import time
from pathlib import Path

from src.detect.project_type import detect_project_type
from src.extract.reuse_pipeline import extract_repo_with_reuse
from src.storage.mirror_store import output_path_for, read_stored


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_repo(root: Path) -> None:
    _write(root / "package.json", json.dumps({"dependencies": {"react": "^19.0.0"}}))
    _write(root / "src" / "features" / "widgets" / "WidgetList.tsx", """
export default function WidgetList() {
  return <div>widgets</div>;
}
""")
    _write(root / "src" / "features" / "profile" / "ProfilePage.tsx", """
export default function ProfilePage() {
  return <div>profile</div>;
}
""")


def test_first_run_creates_all_stored_chunks(tmp_path):
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    _build_repo(repo)
    project_type = detect_project_type(repo)

    records, stats = extract_repo_with_reuse(repo, project_type, output)

    assert stats["reused"] == 0
    assert stats["reanalyzed"] == stats["total"] == 2
    for record in records:
        stored = read_stored(output, record["filePath"])
        assert stored is not None
        assert stored["chunkId"] == record["chunkId"]


def test_second_run_with_no_changes_reuses_everything(tmp_path):
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    _build_repo(repo)
    project_type = detect_project_type(repo)

    extract_repo_with_reuse(repo, project_type, output)
    records_2, stats_2 = extract_repo_with_reuse(repo, project_type, output)

    assert stats_2["reused"] == stats_2["total"] == 2
    assert stats_2["reanalyzed"] == 0


def test_changing_one_file_reanalyzes_only_that_one(tmp_path):
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    _build_repo(repo)
    project_type = detect_project_type(repo)

    records_1, _ = extract_repo_with_reuse(repo, project_type, output)
    widget_record_1 = next(r for r in records_1 if "WidgetList" in r["filePath"])
    profile_record_1 = next(r for r in records_1 if "ProfilePage" in r["filePath"])

    time.sleep(0.01)  # ensure a later run would get a different lastUpdated if re-extracted
    _write(repo / "src" / "features" / "widgets" / "WidgetList.tsx", """
export default function WidgetList() {
  return <div>widgets v2</div>;
}
""")

    records_2, stats_2 = extract_repo_with_reuse(repo, project_type, output)
    widget_record_2 = next(r for r in records_2 if "WidgetList" in r["filePath"])
    profile_record_2 = next(r for r in records_2 if "ProfilePage" in r["filePath"])

    assert stats_2["reanalyzed"] == 1
    assert stats_2["reused"] == 1

    # The changed file got a new contentHash and a new lastUpdated.
    assert widget_record_2["contentHash"] != widget_record_1["contentHash"]
    assert widget_record_2["lastUpdated"] != widget_record_1["lastUpdated"]

    # The untouched file's record is byte-for-byte reused: same lastUpdated,
    # same contentHash — proof it was not re-extracted, not just that its
    # hash happens to match.
    assert profile_record_2["lastUpdated"] == profile_record_1["lastUpdated"]
    assert profile_record_2["contentHash"] == profile_record_1["contentHash"]


def test_output_path_mirrors_source_structure(tmp_path):
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    _build_repo(repo)
    project_type = detect_project_type(repo)

    extract_repo_with_reuse(repo, project_type, output)

    expected = output_path_for(output, "src/features/widgets/WidgetList.tsx")
    assert expected.is_file()
    assert str(expected).startswith(str(output))
    assert "src/features/widgets/WidgetList.tsx" in str(expected)
