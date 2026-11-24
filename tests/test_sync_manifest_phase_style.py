"""sync_manifest_phase_style patches staged manifests from pipeline.config.yaml."""

from __future__ import annotations

import json
import textwrap

from scripts.sync_manifest_phase_style import CHUNKS_DIR, sync_manifests


def _minimal_config(tmp_path, lifecycle: str = "fancy") -> None:
    content = textwrap.dedent(
        f"""
        source:
          type: git
          git: "https://github.com/example/repo"
          prefer: git
        chunking:
          small_max_lines: 200
          medium_max_lines: 800
          target_narration_seconds: [90, 180]
        storage:
          mirror_root: "./output/chunks"
        security:
          never_read_patterns: [".env*"]
          secret_scan_before_write: true
        video:
          phaseStyle:
            fileCard: fancy
            componentTree: fancy
            lifecycle: {lifecycle}
            chunkView: fancy
            visualBreakdown: fancy
        """
    )
    (tmp_path / "pipeline.config.yaml").write_text(content)


def test_sync_manifests_updates_combined_and_stack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    chunks = tmp_path / "render-app" / "public" / "chunks"
    (chunks / "react").mkdir(parents=True)
    combined = {
        "chunkIds": ["c1"],
        "stacks": {"react": ["c1"]},
        "phaseStyle": {"fileCard": "classic"},
    }
    (chunks / "manifest.json").write_text(json.dumps(combined), encoding="utf-8")
    stack = {"stack": "react", "chunkIds": ["c1"], "phaseStyle": {"fileCard": "classic"}}
    (chunks / "react" / "manifest.json").write_text(json.dumps(stack), encoding="utf-8")

    _minimal_config(tmp_path, lifecycle="fancy")
    monkeypatch.setattr(
        "scripts.sync_manifest_phase_style.CHUNKS_DIR",
        chunks,
    )
    updated, style = sync_manifests(tmp_path / "pipeline.config.yaml")
    assert updated == 2
    assert style["lifecycle"] == "fancy"

    combined_after = json.loads((chunks / "manifest.json").read_text(encoding="utf-8"))
    assert combined_after["phaseStyle"]["fileCard"] == "fancy"
    assert combined_after["phaseStyle"]["lifecycle"] == "fancy"

    stack_after = json.loads((chunks / "react" / "manifest.json").read_text(encoding="utf-8"))
    assert stack_after["phaseStyle"]["chunkView"] == "fancy"