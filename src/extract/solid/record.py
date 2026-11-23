"""Solid chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, read_lines
from ..record_base import base_record
from . import extract as solid


def build_solid_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    stem = Path(chunk.file_path).stem
    facts = solid.extract_solid(text, stem)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["solid-js"]
    record["jsxMounts"] = facts.mounts
    record["signals"] = facts.signals
    record["effects"] = facts.effects
    record["hooks"] = [
        {"name": s["kind"], "kind": s["kind"], "line": s["line"], "owner": stem, "assumed": s["assumed"]}
        for s in facts.signals
    ]
    conf = 0.5 if facts.mounts or facts.signals else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Solid regex extract; signal→subscriber edges assumed under regex fidelity."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="solid")
