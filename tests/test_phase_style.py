"""video.phaseStyle loader, validation, and manifest embedding."""

from __future__ import annotations

import textwrap

import pytest

from src.config.load_config import ConfigError, load_config
from src.config.phase_style import (
    DEFAULT_PHASE_STYLE,
    PHASE_STYLE_KEYS,
    STRUCTURE_PHASE_STYLE_DEFAULT_FANCY,
    combined_manifest_payload,
    resolve_phase_style,
    stack_manifest_payload,
)


def test_resolve_phase_style_defaults_structure_fancy():
    resolved = resolve_phase_style({})
    for key in STRUCTURE_PHASE_STYLE_DEFAULT_FANCY:
        assert resolved[key] == "fancy", key
    for key in PHASE_STYLE_KEYS - STRUCTURE_PHASE_STYLE_DEFAULT_FANCY:
        assert resolved[key] == "classic", key
    assert resolve_phase_style({"video": {}}) == resolved
    assert resolve_phase_style(None) == resolved


def test_resolve_phase_style_partial_explicit_only():
    resolved = resolve_phase_style({
        "video": {
            "phaseStyle": {
                "fileCard": "fancy",
            },
        },
    })
    assert resolved["fileCard"] == "fancy"
    assert resolved["componentTree"] == "fancy"
    assert resolved["visualBreakdown"] == "fancy"
    for key in PHASE_STYLE_KEYS - {"fileCard"} - STRUCTURE_PHASE_STYLE_DEFAULT_FANCY:
        assert resolved[key] == "classic", key


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
        lifecycle: fancy
    """)
    path = tmp_path / "pipeline.config.yaml"
    path.write_text(content)
    config = load_config(path)
    assert config.phase_style["lifecycle"] == "fancy"
    assert config.phase_style["fileCard"] == "classic"
    assert config.phase_style["componentTree"] == "fancy"
    assert config.phase_style["visualBreakdown"] == "fancy"


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
        "video": {"phaseStyle": {"visualBreakdown": "fancy"}},
    })
    stack = stack_manifest_payload("react", ["c1"], style)
    assert stack["phaseStyle"] == style
    assert stack["phaseStyle"]["visualBreakdown"] == "fancy"
    assert stack["phaseStyle"]["componentTree"] == "fancy"
    assert stack["phaseStyle"]["chunkView"] == "classic"

    combined = combined_manifest_payload(["c1"], {"react": ["c1"]}, style)
    assert combined["phaseStyle"] == style
    assert "chunkIds" in combined
    assert "stacks" in combined