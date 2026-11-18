"""Phase 4 — best-effort pullRequest lookup.

Closes part of Phase 3's documented gap: given a GitHub owner/repo and a
file path, find the most recent pull request that touched that file, via
`gh api`. This only works when the session actually has GitHub API
access to that repo (an owned/attached repo with push-level access, per
this environment's rules) — a third-party example repo like the alumni
one is read-only here, and this module does not try to force-attach one
just to read its PR history. When `gh api` fails for any reason (no
access, no commits, no associated PR, network), this returns None and
the caller keeps the existing honest null + note behavior. It never
raises out to the pipeline and never fabricates a URL.
"""

from __future__ import annotations

import json
import subprocess


def _gh_api(path: str) -> list | dict | None:
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def find_last_pull_request_url(owner: str, repo: str, file_path: str) -> str | None:
    """Best effort only. Returns the html_url of the most recent PR
    associated with the latest commit that touched `file_path`, or None
    if that can't be determined (no API access, no commits, no linked
    PR, or any error along the way)."""
    commits = _gh_api(f"repos/{owner}/{repo}/commits?path={file_path}&per_page=1")
    if not isinstance(commits, list) or not commits:
        return None
    sha = commits[0].get("sha")
    if not sha:
        return None

    pulls = _gh_api(f"repos/{owner}/{repo}/commits/{sha}/pulls")
    if not isinstance(pulls, list) or not pulls:
        return None
    return pulls[0].get("html_url")
