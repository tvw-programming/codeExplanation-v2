"""Angular chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, read_lines
from ..record_base import base_record
from . import extract as ang


def build_angular_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    prelim = ang.extract_angular_component(text, None)
    tmpl = None
    if prelim and prelim.template_url:
        tmpl = ang.load_template_sibling(root, chunk.file_path, prelim.template_url)
    comp = ang.extract_angular_component(text, tmpl)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["@angular/core"]
    if not comp:
        record["confidence"] = 0.3
        record["confidenceLevel"] = "low"
        record["notes"] = "No @Component found; Angular visual tree unavailable."
        record["fidelity"] = "regex"
        from src.visual.pipeline import attach_visuals
        return attach_visuals(record, stack="angular")

    record["angularComponent"] = {
        "name": comp.name,
        "selector": comp.selector,
        "templateUrl": comp.template_url,
        "line": comp.line,
        "assumed": comp.assumed,
    }
    record["inputs"] = [{"name": n} for n in comp.inputs]
    record["outputs"] = [{"name": n, "kind": "callback"} for n in comp.outputs]
    record["eventHandlers"] = [
        {
            "name": e["handler"],
            "lineRange": [comp.line, comp.line],
            "assumed": e.get("assumed", False),
            "event": e["event"],
        }
        for e in comp.template_events
    ] or [
        {"name": m["name"], "lineRange": [m["line"], m["line"]], "assumed": False}
        for m in comp.methods
    ]
    record["apiCalls"] = [
        {"method": c["method"], "url": c["url"], "line": c["line"], "assumed": c["assumed"]}
        for c in comp.api_calls
    ]
    record["injectTokens"] = comp.inject_tokens
    record["importantFunctions"] = [
        {"name": m["name"], "lineRange": [m["line"], m["line"]], "calls": [], "sideEffects": []}
        for m in comp.methods
    ]
    record["jsxMounts"] = []
    record["selector"] = comp.selector
    conf = 0.55 if (comp.inputs or comp.outputs or comp.template_events) else 0.35
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Angular dedicated extractor (incl. signal input()/output()); "
        "project-wide selector index not built — tree is this component unit."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="angular")
