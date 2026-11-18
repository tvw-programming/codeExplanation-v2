"""Phase 0 — config loader.

Loads pipeline.config.yaml and validates the minimum required structure.
Does not hardcode any repo: the source is always read from config or
passed explicitly as an override (e.g. a CLI argument).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when pipeline.config.yaml is missing required fields."""


@dataclass
class SourceConfig:
    type: str  # "git" | "local_path"
    git: str | None
    local_path: str | None
    prefer: str


@dataclass
class ChunkingConfig:
    small_max_lines: int
    medium_max_lines: int
    target_narration_seconds: tuple[int, int]


@dataclass
class StorageConfig:
    mirror_root: str
    required_fields: list[str] = field(default_factory=list)


@dataclass
class SecurityConfig:
    never_read_patterns: list[str]
    secret_scan_before_write: bool


@dataclass
class PipelineConfig:
    source: SourceConfig
    chunking: ChunkingConfig
    storage: StorageConfig
    security: SecurityConfig
    detection: dict[str, Any]
    raw: dict[str, Any]

    def resolve_source(self, override: str | None = None) -> str:
        """Return the repo URL or local path to use.

        `override` (e.g. a CLI --repo argument) always wins, so the
        pipeline can run against *any* repo without editing config.
        """
        if override:
            return override
        if self.source.prefer == "git" and self.source.git:
            return self.source.git
        if self.source.local_path:
            return self.source.local_path
        raise ConfigError("No source configured: set source.git or source.local_path, "
                           "or pass an explicit --repo override.")


def load_config(path: str | Path) -> PipelineConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    try:
        source_raw = raw["source"]
        chunking_raw = raw["chunking"]
        storage_raw = raw["storage"]
        security_raw = raw["security"]
    except KeyError as exc:
        raise ConfigError(f"Missing required top-level config section: {exc}") from exc

    source = SourceConfig(
        type=source_raw.get("type", "git"),
        git=source_raw.get("git"),
        local_path=source_raw.get("local_path"),
        prefer=source_raw.get("prefer", "git"),
    )
    chunking = ChunkingConfig(
        small_max_lines=int(chunking_raw.get("small_max_lines", 200)),
        medium_max_lines=int(chunking_raw.get("medium_max_lines", 800)),
        target_narration_seconds=tuple(chunking_raw.get("target_narration_seconds", [90, 180])),
    )
    storage = StorageConfig(
        mirror_root=storage_raw.get("mirror_root", "./output/chunks"),
        required_fields=storage_raw.get("required_fields", ["contentHash", "lastUpdated", "pullRequest"]),
    )
    security = SecurityConfig(
        never_read_patterns=security_raw.get("never_read_patterns", [".env*", "*.pem", "*secrets*"]),
        secret_scan_before_write=bool(security_raw.get("secret_scan_before_write", True)),
    )

    return PipelineConfig(
        source=source,
        chunking=chunking,
        storage=storage,
        security=security,
        detection=raw.get("detection", {}),
        raw=raw,
    )
