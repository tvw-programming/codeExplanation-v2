"""Phase 1 — project type detection.

Detects project type from marker files (per the locked rule: detection is
marker-file based, not a blind scan for file extensions). Populates the
`projectType` fields: frontend stack, backend stack, architecture
(monolith or microservice), and a Dockerized flag. No "unknown" fallback
value — an unmatched project gets an explicit empty/false state instead,
per the stated requirement.

Stray source files that exist without their stack's marker file (e.g. a
.py script sitting next to a React app with no requirements.txt or
pyproject.toml) are NOT treated as a detected backend stack. They are
surfaced separately as `unclaimed_hint_files` so a human can decide
whether a marker file is just missing. This came up directly while
testing against the alumni repo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIR_NAMES = {".git", "node_modules", "vendor", "venv", ".venv", "dist", "build", "__pycache__"}

MARKER_FILES = {
    "react_or_angular": ["package.json"],
    "python": ["requirements.txt", "pyproject.toml", "setup.py"],
    "go": ["go.mod"],
    "spring_boot": ["pom.xml", "build.gradle", "build.gradle.kts"],
}
DOCKER_MARKERS = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]

# Extensions that hint at a stack even without its marker file present.
# Used only to populate `unclaimed_hint_files`, never to set a stack.
HINT_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".java": "spring_boot_or_java",
}


@dataclass
class MarkerHit:
    directory: str   # path relative to repo root, "" for root
    marker_file: str


@dataclass
class ProjectType:
    frontend_stack: str | None = None          # "react" | "angular" | None
    backend_stacks: list[str] = field(default_factory=list)   # e.g. ["go"], or ["go", "python"]
    architecture: str = "monolith"               # "monolith" | "microservice"
    dockerized: bool = False
    marker_hits: dict[str, list[MarkerHit]] = field(default_factory=dict)
    unclaimed_hint_files: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "frontend": self.frontend_stack,
            "backend": self.backend_stacks,
            "architecture": self.architecture,
            "dockerized": self.dockerized,
        }


def _iter_dirs(root: Path, max_depth: int = 3):
    """Yield directories under `root` up to max_depth, skipping noise dirs."""
    yield root
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth >= max_depth:
            continue
        try:
            children = list(current.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for child in children:
            if child.is_dir() and child.name not in IGNORED_DIR_NAMES and not child.name.startswith("."):
                yield child
                stack.append((child, depth + 1))


def _find_marker_hits(root: Path, max_depth: int = 3) -> dict[str, list[MarkerHit]]:
    hits: dict[str, list[MarkerHit]] = {stack: [] for stack in MARKER_FILES}
    for directory in _iter_dirs(root, max_depth):
        for stack, filenames in MARKER_FILES.items():
            for filename in filenames:
                candidate = directory / filename
                if candidate.is_file():
                    rel = str(directory.relative_to(root)) if directory != root else ""
                    hits[stack].append(MarkerHit(directory=rel, marker_file=filename))
    return hits


def _detect_frontend_flavor(package_json_path: Path) -> str | None:
    """Distinguish React vs Angular from package.json dependencies."""
    try:
        data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "react_or_angular"  # marker present, contents unreadable
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "@angular/core" in deps:
        return "angular"
    if "react" in deps:
        return "react"
    return "react_or_angular"  # package.json exists but neither found


def _detect_java_flavor(root: Path, directory: Path) -> str:
    """spring_boot if Spring Boot is an actual dependency, else plain java."""
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        candidate = directory / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "spring-boot" in text or "org.springframework.boot" in text:
                return "spring_boot"
    return "java"


def _is_dockerized(root: Path, max_depth: int = 2) -> bool:
    for directory in _iter_dirs(root, max_depth):
        if any((directory / name).is_file() for name in DOCKER_MARKERS):
            return True
    return False


def _find_unclaimed_hints(root: Path, marker_hits: dict[str, list[MarkerHit]], max_depth: int = 3) -> dict[str, list[str]]:
    """Source files whose extension hints at a stack that has no marker
    file anywhere in the scanned tree. Surfaced for a human to check,
    never promoted to a detected backend stack automatically."""
    claimed_stacks = {stack for stack, hits in marker_hits.items() if hits}
    found: dict[str, list[str]] = {}
    for directory in _iter_dirs(root, max_depth):
        try:
            children = list(directory.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for child in children:
            if not child.is_file():
                continue
            hinted_stack = HINT_EXTENSIONS.get(child.suffix)
            if hinted_stack is None:
                continue
            already_claimed = any(
                hinted_stack == stack or hinted_stack.startswith(stack)
                for stack in claimed_stacks
            )
            if already_claimed:
                continue
            found.setdefault(hinted_stack, []).append(str(child.relative_to(root)))
    return found


def detect_project_type(root: str | Path, max_depth: int = 3) -> ProjectType:
    root = Path(root)
    marker_hits = _find_marker_hits(root, max_depth)

    frontend_stack = None
    for hit in marker_hits["react_or_angular"]:
        flavor = _detect_frontend_flavor(root / hit.directory / hit.marker_file)
        if flavor in ("react", "angular"):
            frontend_stack = flavor
            break
        if frontend_stack is None:
            frontend_stack = flavor  # react_or_angular, ambiguous

    backend_stacks: list[str] = []
    backend_service_roots: set[str] = set()

    if marker_hits["go"]:
        backend_stacks.append("go")
        backend_service_roots.update(hit.directory for hit in marker_hits["go"])
    if marker_hits["python"]:
        backend_stacks.append("python")
        backend_service_roots.update(hit.directory for hit in marker_hits["python"])
    if marker_hits["spring_boot"]:
        flavors = {
            _detect_java_flavor(root, root / hit.directory)
            for hit in marker_hits["spring_boot"]
        }
        backend_stacks.extend(sorted(flavors))
        backend_service_roots.update(hit.directory for hit in marker_hits["spring_boot"])

    # Architecture heuristic: more than one distinct backend service root
    # (sibling directories each with their own backend marker file) means
    # independently deployable services -> microservice. One backend
    # root (even alongside a separate frontend root) is still a single
    # cohesive app -> monolith. This is an inference, not a sourced rule;
    # flag it in notes if the caller surfaces confidence.
    architecture = "microservice" if len(backend_service_roots) > 1 else "monolith"

    dockerized = _is_dockerized(root)
    unclaimed_hints = _find_unclaimed_hints(root, marker_hits, max_depth)

    return ProjectType(
        frontend_stack=frontend_stack,
        backend_stacks=backend_stacks,
        architecture=architecture,
        dockerized=dockerized,
        marker_hits=marker_hits,
        unclaimed_hint_files=unclaimed_hints,
    )
