"""Python chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as py


def build_python_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    functions, routes, imports, _all = py.extract_python(text)
    record = base_record(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = [
        i.module for i in imports
        if i.module.split(".")[0] in ("fastapi", "flask", "django", "starlette")
    ]
    record["importantFunctions"] = [
        {
            "name": f.name,
            "lineRange": list(f.line_range),
            "description": f.docstring,
            "calls": f.calls,
            "decorators": f.decorators,
            "visibility": f.visibility,
            "sideEffects": [],
        }
        for f in functions
    ]
    record["routes"] = [
        {
            "method": r.method,
            "path": r.path,
            "handler": r.handler,
            "assumed": r.assumed,
            "line": r.line,
            "depends": r.depends,
            "middleware": [],
            "protected": any("auth" in d.lower() for d in r.depends),
        }
        for r in routes
    ]
    record["imports"] = [{"module": i.module, "names": i.names, "line": i.line} for i in imports]
    assumed = sum(1 for r in routes if r.assumed)
    conf = confidence_from_flags(max(1, len(functions) + len(routes)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Python via stdlib ast; in-file APIRouter(prefix=) literals compose; "
        "cross-file include_router prefixes stay assumed. "
        "Django urlpatterns path()/re_path()/url() literals only; method UNKNOWN; "
        "include() mounts assumed and not joined across files."
    )
    record["fidelity"] = "syntax"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="python")
