"""Vue chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, read_lines
from ..record_base import base_record
from . import extract as vue


def build_vue_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    sfc = vue.extract_vue_sfc(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["vue"]
    stem = Path(chunk.file_path).stem
    record["jsxMounts"] = [
        {"parent": stem, "child": c["child"], "line": c["line"], "assumed": c["assumed"], "props": []}
        for c in sfc.components
    ]
    record["eventHandlers"] = [
        {"name": e["handler"], "lineRange": [1, 1], "assumed": e["assumed"], "event": e["event"]}
        for e in sfc.events
    ]
    record["vueMeta"] = {
        "hasProps": sfc.has_props,
        "hasEmits": sfc.has_emits,
        "scriptSetup": sfc.script_setup,
        "hasVHtml": sfc.has_v_html,
    }
    if sfc.has_v_html:
        record["securityHints"] = [{
            "id": "v-html",
            "ruleId": "xss_html_sink",
            "severity": "high",
            "message": "v-html sink in template.",
            "assumed": False,
        }]
    conf = 0.5 if sfc.components or sfc.events else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Vue SFC regex extract; dynamic <component :is> not resolved."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="vue")
