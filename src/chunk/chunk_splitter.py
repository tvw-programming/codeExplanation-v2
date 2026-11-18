"""Phase 2 — size-based chunk splitting (step 3).

Rule: small feature (<=200 total lines) stays one chunk; medium
(200-800) splits at logical boundaries; large (>800) splits into
several chunks.

"Logical boundaries" at the statement/function level needs a real
parser per language and belongs to Phase 3 extraction. What this phase
CAN decide without a parser is the file-level split: each file in a
medium or large feature becomes its own chunk, since a file boundary is
already a real logical boundary. A single file that is itself over the
small threshold is flagged `needs_further_split=True` so Phase 3 knows
to split it again at the statement level once it can parse the file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .feature_grouping import Feature

SMALL_MAX_LINES = 200
MEDIUM_MAX_LINES = 800


def count_lines(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def classify_size(total_lines: int, small_max: int = SMALL_MAX_LINES, medium_max: int = MEDIUM_MAX_LINES) -> str:
    if total_lines <= small_max:
        return "small"
    if total_lines <= medium_max:
        return "medium"
    return "large"


def make_chunk_id(feature_name: str, file_path: str) -> str:
    """Readable feature-name prefix + short hash of file path and feature
    name together, per the locked chunkId rule."""
    digest = hashlib.sha256(f"{file_path}:{feature_name}".encode("utf-8")).hexdigest()[:8]
    slug = "".join(c if c.isalnum() else "-" for c in feature_name.lower()).strip("-")
    slug = "-".join(filter(None, slug.split("-")))  # collapse repeats
    return f"{slug}-{digest}"


@dataclass
class ChunkPlan:
    chunk_id: str
    feature_name: str
    stack: str
    file_path: str                 # primary file for this chunk
    related_files: list[str] = field(default_factory=list)   # other files in the same feature
    total_lines: int = 0
    size_class: str = "small"
    needs_further_split: bool = False   # true => Phase 3 must split this file again (statement level)


def plan_chunks_for_feature(feature: Feature, root: Path,
                             small_max: int = SMALL_MAX_LINES,
                             medium_max: int = MEDIUM_MAX_LINES) -> list[ChunkPlan]:
    file_line_counts = {f: count_lines(root / f) for f in feature.files}
    total_lines = sum(file_line_counts.values())
    size_class = classify_size(total_lines, small_max, medium_max)

    if size_class == "small":
        primary = feature.primary_file or feature.files[0]
        related = [f for f in feature.files if f != primary]
        return [ChunkPlan(
            chunk_id=make_chunk_id(feature.name, primary),
            feature_name=feature.name,
            stack=feature.stack,
            file_path=primary,
            related_files=related,
            total_lines=total_lines,
            size_class=size_class,
            needs_further_split=False,
        )]

    # medium or large: one chunk per file in the feature.
    chunks: list[ChunkPlan] = []
    for f in feature.files:
        file_lines = file_line_counts[f]
        chunks.append(ChunkPlan(
            chunk_id=make_chunk_id(feature.name, f),
            feature_name=feature.name,
            stack=feature.stack,
            file_path=f,
            related_files=[other for other in feature.files if other != f],
            total_lines=file_lines,
            size_class=classify_size(file_lines, small_max, medium_max),
            needs_further_split=file_lines > small_max,
        ))
    return chunks


def plan_chunks(features: list[Feature], root: Path) -> list[ChunkPlan]:
    all_chunks: list[ChunkPlan] = []
    for feature in features:
        if not feature.files:
            continue
        all_chunks.extend(plan_chunks_for_feature(feature, root))
    return all_chunks
