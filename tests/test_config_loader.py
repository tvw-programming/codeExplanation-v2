import textwrap
from pathlib import Path

import pytest

from src.config.load_config import load_config, ConfigError


def _write_config(tmp_path: Path, extra: str = "") -> Path:
    content = textwrap.dedent(f"""
    source:
      type: git
      git: "https://github.com/tvw-programming/Alumni-web"
      local_path: null
      prefer: git
    chunking:
      small_max_lines: 200
      medium_max_lines: 800
      target_narration_seconds: [90, 180]
    storage:
      mirror_root: "./output/chunks"
      required_fields: ["contentHash", "lastUpdated", "pullRequest"]
    security:
      never_read_patterns: [".env*", "*.pem", "*secrets*"]
      secret_scan_before_write: true
    {extra}
    """)
    path = tmp_path / "pipeline.config.yaml"
    path.write_text(content)
    return path


def test_load_config_happy_path(tmp_path):
    path = _write_config(tmp_path)
    config = load_config(path)
    assert config.source.git == "https://github.com/tvw-programming/Alumni-web"
    assert config.chunking.small_max_lines == 200
    assert config.storage.required_fields == ["contentHash", "lastUpdated", "pullRequest"]
    assert config.security.secret_scan_before_write is True
    assert config.phase_style["fileCard"] == "classic"
    assert all(v == "classic" for v in config.phase_style.values())


def test_resolve_source_uses_git_by_default(tmp_path):
    path = _write_config(tmp_path)
    config = load_config(path)
    assert config.resolve_source() == "https://github.com/tvw-programming/Alumni-web"


def test_resolve_source_override_wins(tmp_path):
    path = _write_config(tmp_path)
    config = load_config(path)
    assert config.resolve_source("https://github.com/other/repo") == "https://github.com/other/repo"


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_missing_required_section_raises(tmp_path):
    path = tmp_path / "pipeline.config.yaml"
    path.write_text("source:\n  type: git\n")
    with pytest.raises(ConfigError):
        load_config(path)
