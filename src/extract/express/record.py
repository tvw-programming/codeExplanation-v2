"""Express chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as ex


def build_express_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    routes, middleware, mounts = ex.extract_express(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["express"]
    record["routes"] = [
        {
            "method": r.method,
            "path": r.path,
            "handler": r.handler,
            "assumed": r.assumed,
            "line": r.line,
            "routerVar": r.router_var,
            "notes": r.note,
            "middleware": [
                {
                    "name": m.name,
                    "order": m.order,
                    "line": m.line,
                    "isAuth": m.is_auth,
                    "assumed": m.assumed,
                    "routerVar": m.router_var,
                }
                for m in middleware
                if m.router_var == r.router_var or m.router_var == "app"
            ],
            "protected": any(
                m.is_auth and (m.router_var == r.router_var or m.router_var == "app")
                for m in middleware
            ),
        }
        for r in routes
    ]
    record["middleware"] = [
        {
            "name": m.name,
            "order": m.order,
            "line": m.line,
            "isAuth": m.is_auth,
            "assumed": m.assumed,
            "routerVar": m.router_var,
            "source": "use",
        }
        for m in middleware
    ]
    record["routeMounts"] = mounts
    assumed = sum(1 for r in routes if r.assumed)
    conf = confidence_from_flags(max(1, len(routes) + len(middleware)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Express in-file routes (incl. route().get/post chains); "
        "cross-file app.use prefixes may be incomplete (assumed)."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="express")
