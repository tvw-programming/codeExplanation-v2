"""Shared chunk-record skeleton — stack-agnostic fields only."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.storage.mirror_store import EXTRACTOR_VERSION

from .common import content_hash, detect_language, now_iso, read_lines
from .function_context import file_header_comment


def base_record(root: Path, chunk: ChunkPlan, project_type_dict: dict, lines: list[str] | None = None) -> dict:
    if lines is None:
        lines = read_lines(root, chunk.file_path)
    return {
        "chunkId": chunk.chunk_id,
        "filePath": chunk.file_path,
        "featureName": chunk.feature_name,
        "projectType": project_type_dict,
        "stack": chunk.stack,
        "language": detect_language(chunk.file_path),
        "lineRange": [1, len(lines)],
        "fileDescription": file_header_comment(lines),
        "frameworkOrLibrary": [],
        "inputs": [],
        "outputs": [],
        "eventHandlers": [],
        "apiCalls": [],
        "importantFunctions": [],
        "sideEffects": [],
        "featureMapping": [],
        "dependencies": [],
        "dataModels": [],
        "routes": [],
        "contentHash": content_hash(root, chunk.file_path),
        "extractorVersion": EXTRACTOR_VERSION,
        "lastUpdated": now_iso(),
        "pullRequest": None,
        "pullRequestNote": "Not determined: shallow clone / no GitHub API in this phase.",
    }
