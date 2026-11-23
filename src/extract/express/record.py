"""Express chunk record builder."""

from __future__ import annotations

import re
from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as ex

_AUTH_RE = re.compile(r"(?i)auth|jwt|passport|session")


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
            "middleware": _middleware_for_route(r, middleware),
            "protected": _route_protected(r, middleware),
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
            **({"mountPath": m.mount_path} if m.mount_path is not None else {}),
        }
        for m in middleware
    ]
    record["routeMounts"] = mounts
    assumed = sum(1 for r in routes if r.assumed)
    conf = confidence_from_flags(max(1, len(routes) + len(middleware)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = (
        "Express in-file routes (route chains, path arrays, regex→assumed); "
        "nested literal mounts compose; non-literal / cross-file prefixes assumed; "
        "use(prefix, non-router) is path-scoped middleware, not a mount."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="express")


def _middleware_for_route(
    route: ex.ExpressRoute,
    middleware: list[ex.ExpressMiddleware],
) -> list[dict]:
    """Router/app .use() middleware plus per-route METHOD callback middleware."""
    out: list[dict] = []
    for m in middleware:
        if m.router_var == route.router_var or m.router_var == "app":
            out.append({
                "name": m.name,
                "order": m.order,
                "line": m.line,
                "isAuth": m.is_auth,
                "assumed": m.assumed,
                "routerVar": m.router_var,
            })
    base_order = len(out)
    for i, name in enumerate(route.route_middleware):
        out.append({
            "name": name,
            "order": base_order + i,
            "line": route.line,
            "isAuth": bool(_AUTH_RE.search(name)),
            "assumed": False,
            "routerVar": route.router_var,
            "source": "route_arg",
        })
    return out


def _route_protected(
    route: ex.ExpressRoute,
    middleware: list[ex.ExpressMiddleware],
) -> bool:
    if any(
        m.is_auth and (m.router_var == route.router_var or m.router_var == "app")
        for m in middleware
    ):
        return True
    return any(_AUTH_RE.search(n) for n in route.route_middleware)
