"""video.phaseStyle loader, validation, and manifest embedding."""

from __future__ import annotations

import textwrap

import pytest

from src.config.load_config import ConfigError, load_config
from src.config.phase_style import (
    DEFAULT_PHASE_STYLE,
    PHASE_STYLE_KEYS,
    combined_manifest_payload,
    resolve_phase_style,
    stack_manifest_payload,
)


def test_default_phase_style_all_fancy():
    assert all(v == "fancy" for v in DEFAULT_PHASE_STYLE.values())
    assert all(v == "fancy" for v in resolve_phase_style({}).values())
    assert resolve_phase_style({"video": {}}) == resolve_phase_style({})
    assert resolve_phase_style(None) == resolve_phase_style({})


def test_resolve_phase_style_partial_explicit_only():
    resolved = resolve_phase_style({
        "video": {
            "phaseStyle": {
                "chunkView": "classic",
            },
        },
    })
    assert resolved["chunkView"] == "classic"
    for key in PHASE_STYLE_KEYS - {"chunkView"}:
        assert resolved[key] == "fancy", key


def test_resolve_phase_style_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown phaseStyle keys"):
        resolve_phase_style({
            "video": {"phaseStyle": {"notARealPhase": "classic"}},
        })


def test_resolve_phase_style_rejects_bad_value():
    with pytest.raises(ValueError, match="must be 'classic' or 'fancy'"):
        resolve_phase_style({
            "video": {"phaseStyle": {"chunkView": "neon"}},
        })


def test_resolve_phase_style_rejects_non_mapping():
    with pytest.raises(ValueError, match="must be a mapping"):
        resolve_phase_style({"video": {"phaseStyle": "classic"}})


def test_load_config_surfaces_phase_style_on_dataclass(tmp_path):
    content = textwrap.dedent("""
    source:
      type: git
      git: "https://github.com/example/repo"
      local_path: null
      prefer: git
    chunking:
      small_max_lines: 200
      medium_max_lines: 800
      target_narration_seconds: [90, 180]
    storage:
      mirror_root: "./output/chunks"
      required_fields: ["contentHash"]
    security:
      never_read_patterns: [".env*"]
      secret_scan_before_write: true
    video:
      phaseStyle:
        lifecycle: classic
    """)
    path = tmp_path / "pipeline.config.yaml"
    path.write_text(content)
    config = load_config(path)
    assert config.phase_style["lifecycle"] == "classic"
    assert config.phase_style["fileCard"] == "fancy"
    assert config.phase_style["componentTree"] == "fancy"


def test_load_config_phase_style_validation_fails_closed(tmp_path):
    content = textwrap.dedent("""
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
        extraKey: classic
    """)
    path = tmp_path / "pipeline.config.yaml"
    path.write_text(content)
    with pytest.raises(ConfigError, match="Unknown phaseStyle keys"):
        load_config(path)


def test_manifest_payloads_embed_resolved_phase_style():
    style = resolve_phase_style({
        "video": {"phaseStyle": {"chunkView": "classic"}},
    })
    stack = stack_manifest_payload("react", ["c1"], style)
    assert stack["phaseStyle"] == style
    assert stack["phaseStyle"]["chunkView"] == "classic"
    assert stack["phaseStyle"]["visualBreakdown"] == "fancy"

    combined = combined_manifest_payload(["c1"], {"react": ["c1"]}, style)
    assert combined["phaseStyle"] == style
    assert "chunkIds" in combined
    assert "stacks" in combined