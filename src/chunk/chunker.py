"""Phase 2 — orchestrator: ties Phase 1's detected marker locations to the
right stack-specific feature grouping, then plans chunks by size.
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
    group_express_features,
    group_rust_features,
)
from .chunk_splitter import ChunkPlan, plan_chunks

FRONTEND_SRC_CANDIDATES = ["src", "app", "."]
FRONTEND_STACKS = {"react", "angular", "vue", "solid", "qwik", "javascript"}


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

    js_hits = project_type.marker_hits.get("js_ecosystem") or project_type.marker_hits.get("react_or_angular") or []
    for hit in js_hits:
        package_json_dir = root / hit.directory if hit.directory else root
        src_root = _find_frontend_src_root(package_json_dir)
        fe = project_type.frontend_stack
        if fe in FRONTEND_STACKS:
            features.extend(group_react_or_angular_features(root, src_root, stack=fe))
        if "express" in project_type.backend_stacks:
            # Express sources often live next to package.json (routes/, src/, .)
            features.extend(group_express_features(root, package_json_dir))

    for hit in project_type.marker_hits.get("go", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_go_features(root, backend_root))

    for hit in project_type.marker_hits.get("python", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_python_agent_features(root, backend_root))

    for hit in project_type.marker_hits.get("spring_boot", []):
        backend_root = root / hit.directory if hit.directory else root
        # Flavor may be spring_boot or java — use detected backend list
        stack = "spring_boot" if "spring_boot" in project_type.backend_stacks else "java"
        features.extend(group_spring_boot_features(root, backend_root, stack=stack))

    for hit in project_type.marker_hits.get("rust", []):
        backend_root = root / hit.directory if hit.directory else root
        features.extend(group_rust_features(root, backend_root))

    chunks = plan_chunks(features, root)
    return ChunkingResult(features=features, chunks=chunks)
