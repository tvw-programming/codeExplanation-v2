"""Python chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as py


def build_python_chunk_record(
    root: Path,
    chunk: ChunkPlan,
    project_type_dict: dict,
    *,
    route_index: py.PythonRouteIndex | None = None,
) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    # Build index lazily when caller did not pre-pass (single-chunk tests).
    index = route_index
    if index is None:
        index = py.build_python_route_index(root)
    functions, routes, imports, _all = py.extract_python(
        text, file_path=chunk.file_path, route_index=index,
    )
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
    routes_out = []
    for r in routes:
        entry = {
            "method": r.method,
            "path": r.path,
            "handler": r.handler,
            "assumed": r.assumed,
            "line": r.line,
            "depends": r.depends,
            "middleware": [],
            "protected": any("auth" in d.lower() for d in r.depends),
        }
        if r.path_resolved is not None:
            entry["pathResolved"] = r.path_resolved
            # Hard rule: pathResolved False ⇒ assumed True
            if r.path_resolved is False:
                entry["assumed"] = True
        if r.prefix_chain:
            entry["prefixChain"] = r.prefix_chain
        if r.note:
            entry["notes"] = r.note
        routes_out.append(entry)
    record["routes"] = routes_out

    not_analyzed = []
    if routes_out and all(r.get("pathResolved") is False for r in routes_out if "pathResolved" in r):
        # Only escalate when every route that carries pathResolved failed —
        # and at least one such route exists.
        if any("pathResolved" in r for r in routes_out):
            not_analyzed.append({
                "aspect": "routes",
                "reason": (
                    "No route in this file could be traced to a mounted root; "
                    "the prefixes are applied where this router is mounted, "
                    "in a file outside this chunk."
                ),
                "verify": (
                    "Find the include_router()/include()/register_blueprint() "
                    "call that mounts this module and prepend its prefix to "
                    "every path listed here."
                ),
            })
    if not_analyzed:
        record["notAnalyzed"] = not_analyzed

    record["imports"] = [{"module": i.module, "names": i.names, "line": i.line} for i in imports]
    assumed = sum(1 for r in routes_out if r["assumed"])
    conf = confidence_from_flags(max(1, len(functions) + len(routes)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Python via stdlib ast; in-file APIRouter(prefix=)/Blueprint(url_prefix=) "
        "and include_router/register_blueprint literal mounts compose via shared "
        "PrefixGraph; cross-file include_router / register_blueprint / Django "
        "include() join only on unique literal resolution (else assumed/skip). "
        "Django urlpatterns path()/re_path()/url() literals; method UNKNOWN unless "
        "the view/CBV is defined in-file with require_*/api_view or HTTP verb methods."
    )
    record["fidelity"] = "syntax"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="python")
