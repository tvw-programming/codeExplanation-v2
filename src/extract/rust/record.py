"""Rust chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, confidence_from_flags, read_lines
from ..record_base import base_record
from . import extract as rust


def build_rust_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    facts = rust.extract_rust(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = sorted({r.get("framework") for r in facts.routes if r.get("framework")})
    record["rustModules"] = facts.modules
    record["rustUses"] = facts.uses
    record["importantFunctions"] = [
        {"name": f["name"], "lineRange": [f["line"], f["line"]], "calls": [], "sideEffects": []}
        for f in facts.functions
    ]
    record["routes"] = [
        {
            "method": r["method"],
            "path": r["path"],
            "handler": r.get("handler") or "",
            "assumed": bool(r.get("assumed")),
            "line": r["line"],
            "middleware": [],
            "protected": False,
            **({"note": r["note"]} if r.get("note") else {}),
        }
        for r in facts.routes
    ]
    record["unsafeBlocks"] = facts.unsafe_blocks
    total = max(1, len(facts.routes) + len(facts.modules))
    assumed = sum(1 for r in facts.routes if r.get("assumed"))
    conf = confidence_from_flags(total, assumed) if (facts.routes or facts.modules) else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Rust regex extract; literal Axum/Actix/Rocket routes emit real handlers. "
        "In-file .nest composes; unresolved nest targets invent no children. "
        "Macro-generated routes may be missing (partial)."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="rust")
