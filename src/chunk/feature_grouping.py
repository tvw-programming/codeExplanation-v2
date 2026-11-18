"""Phase 2 — feature-wise dynamic chunking: grouping files into features.

Per the locked rule, the unit is the FEATURE, not a fixed component or
folder. Grouping rules differ by stack:

- React / Angular: group by route or component folder.
- Go: group by package/handler — a handler and its matching repository
  (same resource name) are pulled into one feature.
- Python: group by agent — a main file, router, config, and test file
  that share an agent name are pulled into one feature.
- Spring Boot: group by controller/service — same pairing idea as Go.

Nothing here is hardcoded to the alumni-web repo's actual folder names
(e.g. "admin", "alumni", "media") — the grouping works off generic
structural signals (an organizing folder like features/pages/routes, or
a shared filename stem) so it holds for a different repo laid out the
same general way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIR_NAMES = {".git", "node_modules", "vendor", "venv", ".venv", "dist", "build", "__pycache__"}

FRONTEND_SOURCE_EXTENSIONS = {".tsx", ".ts", ".jsx", ".js"}
GO_SOURCE_EXTENSION = ".go"
PYTHON_SOURCE_EXTENSION = ".py"
JAVA_SOURCE_EXTENSION = ".java"

# Folder names that conventionally organize frontend features/routes.
FRONTEND_ORGANIZING_DIR_NAMES = ["features", "pages", "routes", "views", "modules"]

# Folder names that conventionally hold Go/Spring handler-ish or
# repository-ish code, used for the handler<->repository pairing pass.
RESOURCE_DIR_NAMES = {"handler", "handlers", "controller", "controllers", "repository", "repositories", "service", "services"}

# Suffixes stripped from a filename stem to find its "resource name" for pairing.
RESOURCE_SUFFIX_PATTERN = re.compile(
    r"(_handler|_repository|_service|_controller|Handler|Repository|Service|Controller)$"
)

PYTHON_AGENT_SUFFIXES = ["main", "router", "config", "test"]


@dataclass
class Feature:
    name: str
    stack: str                       # "react" | "angular" | "go" | "python" | "spring_boot" | "java"
    files: list[str] = field(default_factory=list)   # paths relative to repo root
    primary_file: str | None = None   # the defining file, if one is clear


def _relpath(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _iter_files(directory: Path, extensions: set[str], recursive: bool = True):
    pattern = "**/*" if recursive else "*"
    for path in directory.glob(pattern):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES or part.startswith(".") for part in path.parts):
            continue
        if path.suffix in extensions:
            yield path


def _pick_primary(files: list[Path]) -> Path | None:
    """Prefer an index/page/main-looking file as the primary; else the
    first file alphabetically for stability."""
    for f in sorted(files):
        stem_lower = f.stem.lower()
        if stem_lower in ("index", "page", "main") or stem_lower.endswith("page"):
            return f
    return sorted(files)[0] if files else None


# ---------------------------------------------------------------------------
# React / Angular
# ---------------------------------------------------------------------------

def group_react_or_angular_features(root: Path, src_root: Path, stack: str = "react") -> list[Feature]:
    """Group a frontend source tree into features.

    - If an organizing folder (features/pages/routes/views/modules) exists
      under src_root, each of its immediate subdirectories is one feature.
    - Any other immediate subdirectory of src_root is itself one feature
      (all files under it, recursively).
    - Loose files directly in src_root (no subdirectory) are grouped into
      one feature named after src_root's own directory name.
    """
    features: list[Feature] = []
    if not src_root.is_dir():
        return features

    organizing_dir = None
    for name in FRONTEND_ORGANIZING_DIR_NAMES:
        candidate = src_root / name
        if candidate.is_dir():
            organizing_dir = candidate
            break

    handled_dirs: set[Path] = set()

    if organizing_dir is not None:
        handled_dirs.add(organizing_dir)
        for sub in sorted(p for p in organizing_dir.iterdir() if p.is_dir()):
            files = sorted(_iter_files(sub, FRONTEND_SOURCE_EXTENSIONS))
            if not files:
                continue
            primary = _pick_primary(files)
            features.append(Feature(
                name=sub.name,
                stack=stack,
                files=[_relpath(root, f) for f in files],
                primary_file=_relpath(root, primary) if primary else None,
            ))

    loose_files: list[Path] = []
    for entry in sorted(src_root.iterdir()):
        if entry in handled_dirs:
            continue
        if entry.is_file() and entry.suffix in FRONTEND_SOURCE_EXTENSIONS:
            loose_files.append(entry)
        elif entry.is_dir() and entry.name not in IGNORED_DIR_NAMES and not entry.name.startswith("."):
            files = sorted(_iter_files(entry, FRONTEND_SOURCE_EXTENSIONS))
            if not files:
                continue
            primary = _pick_primary(files)
            features.append(Feature(
                name=entry.name,
                stack=stack,
                files=[_relpath(root, f) for f in files],
                primary_file=_relpath(root, primary) if primary else None,
            ))

    if loose_files:
        primary = _pick_primary(loose_files)
        features.append(Feature(
            name=src_root.name,
            stack=stack,
            files=[_relpath(root, f) for f in loose_files],
            primary_file=_relpath(root, primary) if primary else None,
        ))

    return features


# ---------------------------------------------------------------------------
# Go (and, by the same shape, Spring Boot/Java)
# ---------------------------------------------------------------------------

def _resource_stem(filename_stem: str) -> str:
    """Strip a known handler/repository/service/controller suffix to get
    the shared resource name, e.g. 'alumni_handler' -> 'alumni',
    'AlumniController' -> 'Alumni'."""
    return RESOURCE_SUFFIX_PATTERN.sub("", filename_stem)


def _group_by_resource_pairing(root: Path, backend_root: Path, extension: str, stack: str) -> list[Feature]:
    """Generic pairing pass shared by Go and Spring Boot/Java:

    - Within directories that look like resource layers (handler/
      repository/service/controller), pair files across those
      directories by shared resource-name stem into one feature.
    - Any other directory under backend_root becomes its own feature
      (all files in it), since it's a cohesive package rather than a
      resource split across layers.
    - A directory with only one file and no siblings is still its own
      single-file feature.
    """
    features: list[Feature] = []
    if not backend_root.is_dir():
        return features

    resource_dirs: list[Path] = []
    other_dirs: list[Path] = []

    for path in backend_root.rglob("*"):
        if not path.is_dir():
            continue
        if any(part in IGNORED_DIR_NAMES or part.startswith(".") for part in path.parts):
            continue
        if path.name.lower() in RESOURCE_DIR_NAMES:
            resource_dirs.append(path)

    resource_dir_set = set(resource_dirs)

    # Pair files across resource dirs by resource-name stem.
    by_resource_name: dict[str, list[Path]] = {}
    for rdir in resource_dirs:
        for f in sorted(rdir.glob(f"*{extension}")):
            resource_name = _resource_stem(f.stem)
            by_resource_name.setdefault(resource_name, []).append(f)

    for resource_name, files in sorted(by_resource_name.items()):
        primary = _pick_primary(files)
        features.append(Feature(
            name=resource_name,
            stack=stack,
            files=[_relpath(root, f) for f in sorted(files)],
            primary_file=_relpath(root, primary) if primary else None,
        ))

    # Every other directory under backend_root (not a resource dir, and
    # not an ancestor that only exists to contain resource dirs) becomes
    # its own feature from its direct files.
    visited: set[Path] = set()
    for path in sorted(backend_root.rglob("*")):
        if not path.is_dir() or path in resource_dir_set:
            continue
        if any(part in IGNORED_DIR_NAMES or part.startswith(".") for part in path.parts):
            continue
        direct_files = sorted(p for p in path.glob(f"*{extension}") if p.is_file())
        if not direct_files:
            continue
        # Skip a dir that is purely an ancestor of resource dirs with no files of its own — already excluded by direct_files check.
        if path in visited:
            continue
        visited.add(path)
        primary = _pick_primary(direct_files)
        features.append(Feature(
            name=path.name,
            stack=stack,
            files=[_relpath(root, f) for f in direct_files],
            primary_file=_relpath(root, primary) if primary else None,
        ))

    # backend_root's own direct files (not in any subdirectory), if any.
    direct_root_files = sorted(p for p in backend_root.glob(f"*{extension}") if p.is_file())
    if direct_root_files:
        primary = _pick_primary(direct_root_files)
        features.append(Feature(
            name=backend_root.name,
            stack=stack,
            files=[_relpath(root, f) for f in direct_root_files],
            primary_file=_relpath(root, primary) if primary else None,
        ))

    return features


def group_go_features(root: Path, backend_root: Path) -> list[Feature]:
    return _group_by_resource_pairing(root, backend_root, GO_SOURCE_EXTENSION, stack="go")


def group_spring_boot_features(root: Path, backend_root: Path, stack: str = "spring_boot") -> list[Feature]:
    return _group_by_resource_pairing(root, backend_root, JAVA_SOURCE_EXTENSION, stack=stack)


# ---------------------------------------------------------------------------
# Python agents
# ---------------------------------------------------------------------------

def group_python_agent_features(root: Path, backend_root: Path) -> list[Feature]:
    """Group Python files into agent features: a main file, a router, a
    config file, and a test file that share an agent name belong to one
    feature, per the locked requirement.

    Matching strategy: within each directory, group files whose stem
    equals, or starts/ends with, one of PYTHON_AGENT_SUFFIXES around a
    shared agent-name core (e.g. "payments_agent.py" + "payments_router.py"
    + "payments_config.py" + "test_payments_agent.py" -> agent "payments").
    Files that match no agent pattern become their own single-file
    feature so nothing is silently dropped.
    """
    features: list[Feature] = []
    if not backend_root.is_dir():
        return features

    for directory in sorted({p.parent for p in backend_root.rglob(f"*{PYTHON_SOURCE_EXTENSION}")
                              if not any(part in IGNORED_DIR_NAMES or part.startswith(".") for part in p.parts)}):
        files = sorted(p for p in directory.glob(f"*{PYTHON_SOURCE_EXTENSION}") if p.is_file())
        grouped: dict[str, list[Path]] = {}
        unmatched: list[Path] = []

        for f in files:
            stem = f.stem
            agent_name = None
            if stem.startswith("test_"):
                rest = stem[len("test_"):]
                for suffix in PYTHON_AGENT_SUFFIXES:
                    if rest.endswith(f"_{suffix}") or rest == suffix:
                        agent_name = rest[: -(len(suffix) + 1)] if rest.endswith(f"_{suffix}") else rest
                        break
                else:
                    agent_name = rest
            else:
                for suffix in PYTHON_AGENT_SUFFIXES:
                    if stem.endswith(f"_{suffix}"):
                        agent_name = stem[: -(len(suffix) + 1)]
                        break

            if agent_name:
                grouped.setdefault(agent_name, []).append(f)
            else:
                unmatched.append(f)

        for agent_name, agent_files in sorted(grouped.items()):
            primary = _pick_primary(agent_files)
            features.append(Feature(
                name=agent_name,
                stack="python",
                files=[_relpath(root, f) for f in sorted(agent_files)],
                primary_file=_relpath(root, primary) if primary else None,
            ))

        for f in unmatched:
            features.append(Feature(
                name=f.stem,
                stack="python",
                files=[_relpath(root, f)],
                primary_file=_relpath(root, f),
            ))

    return features
