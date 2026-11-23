"""Spring Boot chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as spring


def build_spring_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    types, routes = spring.extract_spring(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["spring-boot"] if types else []
    record["springTypes"] = [
        {
            "name": t.name,
            "stereotype": t.stereotype,
            "classPath": t.class_path,
            "line": t.line,
            "injectees": t.injectees,
            "methods": t.methods,
        }
        for t in types
    ]
    record["routes"] = [
        {
            "method": r.method,
            "path": r.path,
            "handler": r.handler,
            "assumed": r.assumed,
            "line": r.line,
            "controller": r.controller,
            "protected": r.has_security,
            "middleware": [],
        }
        for r in routes
    ]
    assumed = sum(1 for r in routes if r.assumed)
    conf = confidence_from_flags(max(1, len(types) + len(routes)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Spring DI is by type (constructor/field/Lombok RequiredArgsConstructor); "
        "imports are never treated as injects."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack=chunk.stack)
