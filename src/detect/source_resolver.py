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


def _host_is_github(netloc: str) -> bool:
    """Exact-or-subdomain match, never a bare substring check — fixed
    after a code review found "github.com" in parsed.netloc accepted
    github.com.attacker.net as a GitHub URL."""
    host = netloc.split("@")[-1].split(":")[0].lower()
    return host == "github.com" or host.endswith(".github.com")


def _looks_like_git_url(value: str) -> bool:
    if value.startswith("git@"):
        return True
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return value.endswith(".git") or _host_is_github(parsed.netloc)


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
        workdir_resolved = workdir.resolve()
        slug = _slug_from_url(value)
        dest = workdir / slug

        # Fixed after a code review found a path-traversal bug: a crafted
        # value like "https://github.com/someorg/.." produced slug ".."
        # and resolved local_root to workdir's PARENT (an arbitrary,
        # already-existing directory), silently skipping the clone and
        # handing the rest of the pipeline the wrong directory to scan.
        # Reject any slug that isn't a single, safe path segment, and
        # double-check the resolved destination actually stays inside
        # workdir before trusting it.
        if not slug or slug in (".", "..") or "/" in slug or "\\" in slug:
            raise SourceResolutionError(
                f"Could not resolve source '{value}': the derived clone directory "
                f"name '{slug}' is not a safe path segment."
            )
        dest_resolved = dest.resolve()
        if dest_resolved == workdir_resolved or workdir_resolved not in dest_resolved.parents:
            raise SourceResolutionError(
                f"Could not resolve source '{value}': the clone destination "
                f"'{dest_resolved}' would fall outside the clone workdir."
            )

        if not dest.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "--", value, str(dest)],
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
