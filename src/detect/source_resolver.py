"""Phase 0 — dynamic repo input.

Accepts any git URL or local path. Nothing about the source repo is
hardcoded; the alumni repo is only the first test case, passed through
config or a CLI override exactly like any other repo would be.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class SourceResolutionError(RuntimeError):
    pass


@dataclass
class ResolvedSource:
    kind: str          # "git" | "local_path"
    original: str       # what the caller passed in
    local_root: Path     # where the code actually lives on disk


def _looks_like_git_url(value: str) -> bool:
    if value.startswith("git@"):
        return True
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and parsed.netloc != "" and value.endswith((".git",)) or (
        parsed.scheme in ("http", "https") and "github.com" in parsed.netloc
    )


def resolve_source(value: str, workdir: Path) -> ResolvedSource:
    """Resolve `value` (a git URL or local path) into a local directory
    the rest of the pipeline can read from.

    This is the only place that distinguishes "git" vs "local_path" —
    every later phase just sees a `local_root` directory.
    """
    candidate = Path(value).expanduser()
    if candidate.exists():
        return ResolvedSource(kind="local_path", original=value, local_root=candidate.resolve())

    if _looks_like_git_url(value):
        workdir.mkdir(parents=True, exist_ok=True)
        dest = workdir / _slug_from_url(value)
        if not dest.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", value, str(dest)],
                check=True,
                capture_output=True,
            )
        return ResolvedSource(kind="git", original=value, local_root=dest.resolve())

    raise SourceResolutionError(
        f"Could not resolve source '{value}': not an existing local path and "
        "not recognized as a git URL."
    )


def _slug_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name
