"""Vanilla JavaScript chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, read_lines
from ..record_base import base_record
from . import extract as js


def build_javascript_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    facts = js.extract_javascript(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = []
    record["moduleImports"] = facts.imports
    record["moduleExports"] = facts.exports
    # Literal DOM mount targets — not JSX; graph builder may surface as meta.
    record["domMounts"] = facts.mounts
    record["eventHandlers"] = [
        {
            "name": l["handler"],
            "lineRange": [l["line"], l["line"]],
            "assumed": l["assumed"],
            "event": l["event"],
        }
        for l in facts.listeners
    ]
    record["securityHints"] = [
        {
            "id": f"sink-{s['kind']}-{s['line']}",
            "ruleId": s["kind"],
            "severity": "high",
            "message": f"Dangerous {s['kind']} sink at line {s['line']}.",
            "assumed": False,
        }
        for s in facts.sinks
    ]
    conf = 0.5 if facts.imports or facts.listeners or facts.exports or facts.mounts else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Vanilla JS module/DOM extract; literal exports + getElementById/"
        "querySelector mounts only; dynamic import(expr) skipped."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="javascript")
