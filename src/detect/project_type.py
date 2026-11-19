"""Phase 1 — project type detection.

Detects project type from marker files (per the locked rule: detection is
marker-file based, not a blind scan for file extensions). Populates the
`projectType` fields: frontend stack, backend stack, architecture
(monolith or microservice), and a Dockerized flag. No "unknown" fallback
value — an unmatched project gets an explicit empty/false state instead.

Stray source files without their stack's marker are surfaced as
`unclaimed_hint_files`, never promoted to a detected stack automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIR_NAMES = {".git", "node_modules", "vendor", "venv", ".venv", "dist", "build", "__pycache__", "target"}

MARKER_FILES = {
    # package.json is the JS ecosystem marker — may yield frontend and/or
    # Express backend depending on dependencies (never invent react_or_angular
    # for an Express-only app).
    "js_ecosystem": ["package.json"],
    "python": ["requirements.txt", "pyproject.toml", "setup.py"],
    "go": ["go.mod"],
    "spring_boot": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "rust": ["Cargo.toml"],
}
# Back-compat alias used by chunker / extractors that still look up the old key.
MARKER_FILES["react_or_angular"] = MARKER_FILES["js_ecosystem"]

DOCKER_MARKERS = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]

HINT_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".java": "spring_boot_or_java",
    ".rs": "rust",
    ".vue": "vue",
}


@dataclass
class MarkerHit:
    directory: str
    marker_file: str


@dataclass
class ProjectType:
    frontend_stack: str | None = None
    backend_stacks: list[str] = field(default_factory=list)
    architecture: str = "monolith"
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
    keys = ("js_ecosystem", "python", "go", "spring_boot", "rust")
    hits: dict[str, list[MarkerHit]] = {stack: [] for stack in keys}
    for directory in _iter_dirs(root, max_depth):
        for stack, filenames in MARKER_FILES.items():
            if stack == "react_or_angular":
                continue  # alias of js_ecosystem
            for filename in filenames:
                candidate = directory / filename
                if candidate.is_file():
                    rel = str(directory.relative_to(root)) if directory != root else ""
                    hits[stack].append(MarkerHit(directory=rel, marker_file=filename))
    # Alias so existing chunker lookups keep working.
    hits["react_or_angular"] = list(hits["js_ecosystem"])
    return hits


def _package_deps(package_json_path: Path) -> dict[str, str] | None:
    try:
        data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


def _classify_js_ecosystem(deps: dict[str, str] | None) -> tuple[str | None, list[str]]:
    """Return (frontend_stack, backend_stacks_from_this_package).

    Honesty: Express is a backend stack. Ambiguous / empty package.json is
    `javascript`, never the silent `react_or_angular` lie.
    """
    if deps is None:
        return "javascript", []

    frontend = None
    backends: list[str] = []

    if "@angular/core" in deps:
        frontend = "angular"
    elif "react" in deps:
        frontend = "react"
    elif "vue" in deps:
        frontend = "vue"
    elif "solid-js" in deps:
        frontend = "solid"
    elif "@builder.io/qwik" in deps or "@qwik.dev/core" in deps:
        frontend = "qwik"

    if "express" in deps:
        backends.append("express")

    if frontend is None and "express" not in deps:
        # package.json present but no FE framework — plain JS module app.
        frontend = "javascript"

    return frontend, backends


def _detect_java_flavor(root: Path, directory: Path) -> str:
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


def _detect_rust_framework(cargo_toml: Path) -> str:
    """Return rust (generic) — framework flavor lives on records as meta."""
    return "rust"


def _is_dockerized(root: Path, max_depth: int = 2) -> bool:
    for directory in _iter_dirs(root, max_depth):
        if any((directory / name).is_file() for name in DOCKER_MARKERS):
            return True
    return False


def _find_unclaimed_hints(root: Path, marker_hits: dict[str, list[MarkerHit]], max_depth: int = 3) -> dict[str, list[str]]:
    claimed_stacks = {stack for stack, hits in marker_hits.items() if hits and stack != "react_or_angular"}
    # js_ecosystem claims vue/js hints when package.json exists
    if marker_hits.get("js_ecosystem"):
        claimed_stacks.update({"vue", "javascript", "react", "angular", "solid", "qwik", "express"})
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
                hinted_stack == stack or hinted_stack.startswith(stack) or stack.startswith(hinted_stack)
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
    backend_stacks: list[str] = []
    backend_service_roots: set[str] = set()

    for hit in marker_hits.get("js_ecosystem", []):
        pkg = root / hit.directory / hit.marker_file if hit.directory else root / hit.marker_file
        deps = _package_deps(pkg)
        fe, be = _classify_js_ecosystem(deps)
        if fe and frontend_stack is None:
            frontend_stack = fe
        elif fe and frontend_stack == "javascript" and fe != "javascript":
            frontend_stack = fe  # prefer concrete framework over plain JS
        for b in be:
            if b not in backend_stacks:
                backend_stacks.append(b)
                backend_service_roots.add(hit.directory)

    if marker_hits.get("go"):
        backend_stacks.append("go")
        backend_service_roots.update(hit.directory for hit in marker_hits["go"])
    if marker_hits.get("python"):
        backend_stacks.append("python")
        backend_service_roots.update(hit.directory for hit in marker_hits["python"])
    if marker_hits.get("spring_boot"):
        flavors = {
            _detect_java_flavor(root, root / hit.directory)
            for hit in marker_hits["spring_boot"]
        }
        backend_stacks.extend(sorted(flavors))
        backend_service_roots.update(hit.directory for hit in marker_hits["spring_boot"])
    if marker_hits.get("rust"):
        backend_stacks.append("rust")
        backend_service_roots.update(hit.directory for hit in marker_hits["rust"])
        for hit in marker_hits["rust"]:
            _detect_rust_framework(root / hit.directory / "Cargo.toml" if hit.directory else root / "Cargo.toml")

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
