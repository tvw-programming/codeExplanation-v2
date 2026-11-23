"""Qwik chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, read_lines
from ..record_base import base_record
from . import extract as qwik


def build_qwik_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    stem = Path(chunk.file_path).stem
    facts = qwik.extract_qwik(text, stem)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["@builder.io/qwik"]
    record["jsxMounts"] = facts.mounts
    record["qwikBoundaries"] = facts.boundaries
    record["signals"] = facts.signals
    record["effects"] = facts.effects
    record["hooks"] = [
        {
            "name": s["kind"],
            "kind": s["kind"],
            "line": s["line"],
            "owner": s.get("owner") or stem,
            "assumed": s.get("assumed", True),
        }
        for s in facts.signals
    ] + [
        {
            "name": e["kind"],
            "kind": e["kind"],
            "line": e["line"],
            "owner": e.get("owner") or stem,
            "assumed": e.get("assumed", True),
        }
        for e in facts.effects
    ]
    record["eventHandlers"] = [
        {
            "name": b.get("name") or b["kind"],
            "lineRange": [b["line"], b["line"]],
            "assumed": b["assumed"],
        }
        for b in facts.boundaries if b["kind"] == "handler$"
    ]
    conf = 0.5 if facts.mounts or facts.boundaries else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Qwik regex extract; component$ bind names when proven; "
        "$ boundaries from source form only."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="qwik")
