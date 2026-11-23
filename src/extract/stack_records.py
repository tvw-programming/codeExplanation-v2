"""Thin re-exports of per-stack record builders.

Hardened stacks live under `src/extract/<stack>/` (extract.py + record.py).
Vue / Solid / Qwik / JavaScript remain here until migrated to the same layout.
"""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from .common import confidence_level, read_lines
from .record_base import base_record
from . import vue_extractor as vue
from . import solid_extractor as solid
from . import qwik_extractor as qwik
from . import javascript_extractor as js

# Migrated stacks — import from packages (not flat god-module logic).
from .python import build_python_chunk_record
from .angular import build_angular_chunk_record
from .spring import build_spring_chunk_record
from .express import build_express_chunk_record
from .rust import build_rust_chunk_record

__all__ = [
    "build_python_chunk_record",
    "build_angular_chunk_record",
    "build_spring_chunk_record",
    "build_express_chunk_record",
    "build_rust_chunk_record",
    "build_vue_chunk_record",
    "build_solid_chunk_record",
    "build_qwik_chunk_record",
    "build_javascript_chunk_record",
]


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
    record["eventHandlers"] = [
        {"name": b.get("name") or b["kind"], "lineRange": [b["line"], b["line"]], "assumed": b["assumed"]}
        for b in facts.boundaries if b["kind"] == "handler$"
    ]
    conf = 0.5 if facts.mounts or facts.boundaries else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Qwik regex extract; $ boundaries from source form only."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="qwik")


def build_javascript_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    facts = js.extract_javascript(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = []
    record["moduleImports"] = facts.imports
    record["moduleExports"] = facts.exports
    record["eventHandlers"] = [
        {"name": l["handler"], "lineRange": [l["line"], l["line"]], "assumed": l["assumed"], "event": l["event"]}
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
    conf = 0.5 if facts.imports or facts.listeners else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Vanilla JS module/DOM extract."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="javascript")
