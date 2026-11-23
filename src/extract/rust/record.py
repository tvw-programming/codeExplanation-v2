"""Rust chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_level, confidence_from_flags, read_lines
from ..record_base import base_record
from . import extract as rust


def build_rust_chunk_record(
    root: Path,
    chunk: ChunkPlan,
    project_type_dict: dict,
    *,
    route_index: rust.RustRouteIndex | None = None,
) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    index = route_index
    if index is None:
        index = rust.build_rust_route_index(root)
    facts = rust.extract_rust(
        text, file_path=chunk.file_path, route_index=index,
    )
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = sorted({r.get("framework") for r in facts.routes if r.get("framework")})
    record["rustModules"] = facts.modules
    record["rustUses"] = facts.uses
    record["importantFunctions"] = [
        {"name": f["name"], "lineRange": [f["line"], f["line"]], "calls": [], "sideEffects": []}
        for f in facts.functions
    ]
    routes_out = []
    for r in facts.routes:
        entry = {
            "method": r["method"],
            "path": r["path"],
            "handler": r.get("handler") or "",
            "assumed": bool(r.get("assumed")),
            "line": r["line"],
            "middleware": [],
            "protected": False,
        }
        if r.get("note"):
            entry["note"] = r["note"]
        if "pathResolved" in r and r["pathResolved"] is not None:
            entry["pathResolved"] = r["pathResolved"]
            # Hard rule: pathResolved False ⇒ assumed True
            if r["pathResolved"] is False:
                entry["assumed"] = True
        if r.get("prefixChain"):
            entry["prefixChain"] = r["prefixChain"]
        routes_out.append(entry)
    record["routes"] = routes_out

    not_analyzed = []
    if routes_out and any("pathResolved" in r for r in routes_out):
        if all(r.get("pathResolved") is False for r in routes_out if "pathResolved" in r):
            not_analyzed.append({
                "aspect": "routes",
                "reason": (
                    "No route in this file could be traced to a .nest(...) mount "
                    "onto a resolved root; the prefixes are applied where this "
                    "router is nested, in a file outside this chunk."
                ),
                "verify": (
                    "Find the Router::nest(\"/prefix\", mod::fn()) call that mounts "
                    "this module and prepend its prefix to every path listed here."
                ),
            })
    if not_analyzed:
        record["notAnalyzed"] = not_analyzed

    record["unsafeBlocks"] = facts.unsafe_blocks
    total = max(1, len(facts.routes) + len(facts.modules))
    assumed = sum(1 for r in routes_out if r.get("assumed"))
    conf = confidence_from_flags(total, assumed) if (facts.routes or facts.modules) else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Rust regex extract; literal Axum/Actix/Rocket routes emit real handlers. "
        "In-file .nest composes; cross-file .nest(prefix, mod::fn()) joins via "
        "PrefixGraph only on unique literal module resolution (else assumed/skip). "
        "Unresolved nest targets invent no children. Macro-generated routes may "
        "be missing (partial)."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="rust")
