"""Resolve and validate video.phaseStyle from pipeline.config.yaml.

Every phase defaults to ``classic`` unless explicitly set to ``fancy``.
"""

from __future__ import annotations

from typing import Final

PHASE_STYLE_KEYS: Final[frozenset[str]] = frozenset({
    "fileCard",
    "componentTree",
    "lifecycle",
    "chunkView",
    "visualBreakdown",
    "architectureDocs",
})

ALLOWED_PHASE_STYLE_VALUES: Final[frozenset[str]] = frozenset({"classic", "fancy"})

# Stable key order for JSON/YAML docs and tests.
PHASE_STYLE_KEY_ORDER: Final[tuple[str, ...]] = tuple(sorted(PHASE_STYLE_KEYS))

DEFAULT_PHASE_STYLE: Final[dict[str, str]] = {
    key: "classic" for key in PHASE_STYLE_KEY_ORDER
}

# Structure clips (tree gate + breakdown L3) opt into fancy when omitted in config.
STRUCTURE_PHASE_STYLE_DEFAULT_FANCY: Final[frozenset[str]] = frozenset({
    "componentTree",
    "visualBreakdown",
})


def resolve_phase_style(raw: dict | None) -> dict[str, str]:
    """Return a fully resolved phaseStyle map (missing keys → classic).

    Reads ``video.phaseStyle`` from the loaded config dict. Unknown keys or
  invalid values raise ``ValueError`` (fail closed; ``load_config`` maps to ``ConfigError``).
    """
    resolved = dict(DEFAULT_PHASE_STYLE)
    for key in STRUCTURE_PHASE_STYLE_DEFAULT_FANCY:
        resolved[key] = "fancy"

    if not raw:
        return resolved

    video = raw.get("video")
    if video is None:
        return resolved
    if not isinstance(video, dict):
        raise ValueError("video must be a mapping when present")

    phase_raw = video.get("phaseStyle")
    if phase_raw is None:
        return resolved
    if not isinstance(phase_raw, dict):
        raise ValueError("video.phaseStyle must be a mapping")

    unknown = set(phase_raw.keys()) - PHASE_STYLE_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown phaseStyle keys: {names}")

    for key, value in phase_raw.items():
        if value not in ALLOWED_PHASE_STYLE_VALUES:
            raise ValueError(
                f"phaseStyle.{key} must be 'classic' or 'fancy', got {value!r}"
            )
        resolved[key] = value
    return resolved


def stack_manifest_payload(
    stack: str,
    chunk_ids: list[str],
    phase_style: dict[str, str],
) -> dict:
    """Per-stack Remotion manifest (chunks/<stack>/manifest.json)."""
    return {
        "stack": stack,
        "chunkIds": chunk_ids,
        "phaseStyle": dict(phase_style),
    }


def combined_manifest_payload(
    chunk_ids: list[str],
    stacks: dict[str, list[str]],
    phase_style: dict[str, str],
) -> dict:
    """Combined Remotion manifest (chunks/manifest.json)."""
    return {
        "chunkIds": chunk_ids,
        "stacks": stacks,
        "phaseStyle": dict(phase_style),
    }