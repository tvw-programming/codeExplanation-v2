"""The analysed project, described for the viewer frontend.

The viewer shows one file tree per technology. Which technologies those
are, and which of them is the frontend, comes from Phase 1 detection —
never from a hardcoded list — so pointing the pipeline at a Spring Boot
+ Vue repo produces a Vue tree and a Spring Boot tree without a code
change here.

Written to render-app/public/chunks/project.json alongside the staged
chunks.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

#: Display order of the roles in the viewer's sidebar.
ROLE_ORDER = {"frontend": 0, "backend": 1, "other": 2}


def _normalize(name: str | None) -> str:
    """Staged stack directories use hyphens because Remotion composition
    ids disallow underscores (`spring_boot` -> `spring-boot`), while
    detection reports the underscored name. Compare on one spelling."""
    return (name or "").strip().lower().replace("_", "-")


def role_for_stack(stack: str, project_type: dict) -> str:
    """frontend / backend / other for one staged stack name."""
    stack_key = _normalize(stack)
    if stack_key and stack_key == _normalize(project_type.get("frontend")):
        return "frontend"
    backends = project_type.get("backend") or []
    if stack_key in {_normalize(b) for b in backends}:
        return "backend"
    return "other"


def build_project_manifest(
    repo_root: str | Path,
    project_type: dict,
    staged_by_stack: dict[str, list[str]],
) -> dict:
    """Describes every staged stack, frontend first, then backends.

    `staged_by_stack` is what run_backend_pilot staged — a stack with no
    successfully rendered chunk is absent, so the viewer never shows a
    tree it cannot play anything from.
    """
    repo_root = Path(repo_root)

    stacks = []
    for stack, chunk_ids in staged_by_stack.items():
        role = role_for_stack(stack, project_type)
        stacks.append(
            {
                "name": stack,
                "role": role,
                "chunkCount": len(chunk_ids),
                "video": f"video-{stack}.mp4",
                "previewVideo": f"video-{stack}-preview.mp4",
                "composition": f"StackVideo-{stack}",
            }
        )

    # Frontend first (left/top of the sidebar), then backends, then
    # anything detection did not place; alphabetical within a role so
    # the order is stable between runs.
    stacks.sort(key=lambda s: (ROLE_ORDER.get(s["role"], 99), s["name"]))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "repoName": repo_root.name,
        "repoRoot": str(repo_root),
        "projectType": project_type,
        "stacks": stacks,
        "generatedAt": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


def write_project_manifest(
    dest: str | Path,
    repo_root: str | Path,
    project_type: dict,
    staged_by_stack: dict[str, list[str]],
) -> dict:
    manifest = build_project_manifest(repo_root, project_type, staged_by_stack)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
