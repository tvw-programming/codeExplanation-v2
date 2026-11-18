"""Phase 2 — orchestrator: ties Phase 1's detected marker locations to the
right stack-specific feature grouping, then plans chunks by size.

Frontend-to-backend linking (matching API calls to routes by URL, for
featureMapping) needs to read and parse the actual call sites and route
definitions, which is Phase 3 extraction work. This module only produces
the feature/chunk plan; featureMapping is populated in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.detect.project_type import ProjectType
from .feature_grouping import (
    Feature,
    group_react_or_angular_features,
    group_go_features,
    group_python_agent_features,
    group_spring_boot_features,
)
from .chunk_splitter import ChunkPlan, plan_chunks

FRONTEND_SRC_CANDIDATES = ["src", "app", "."]


@dataclass
class ChunkingResult:
    features: list[Feature]
    chunks: list[ChunkPlan]


def _find_frontend_src_root(package_json_dir: Path) -> Path:
    for candidate in FRONTEND_SRC_CANDIDATES:
        path = package_json_dir / candidate
        if path.is_dir():
            return path
    return package_json_dir


def chunk_repo(root: str | Path, project_type: ProjectType) -> ChunkingResult:
    root = Path(root)
    features: list[Feature] = []

    for hit in project_type.marker_hits.get("react_or_angular", []):
        package_json_dir = root / hit.directory if hit.directory else root
        src_root = _find_frontend_src_root(package_json_dir)
        stack = project_type.frontend_stack or "react"
        features.extend(group_react_or_angular_features(root, src_root, stack=stack))

    for hit in project_type.marker_hits.get("go", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_go_features(root, backend_root))

    for hit in project_type.marker_hits.get("python", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_python_agent_features(root, backend_root))

    for hit in project_type.marker_hits.get("spring_boot", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_spring_boot_features(root, backend_root))

    chunks = plan_chunks(features, root)
    return ChunkingResult(features=features, chunks=chunks)
