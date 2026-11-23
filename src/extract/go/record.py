"""Go (Fiber) chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.storage.mirror_store import EXTRACTOR_VERSION

from ..common import (
    confidence_from_flags,
    confidence_level,
    content_hash,
    detect_language,
    now_iso,
    read_lines,
)
from ..function_context import build_function_context, file_header_comment
from . import extract as go


def _resolve_go_framework_or_library(imports: list[go.GoImport]) -> list[str]:
    libs = [imp.path for imp in imports if not imp.is_stdlib and not imp.is_internal]
    # Fiber first if present, since it's the defining framework for this stack.
    libs.sort(key=lambda p: (0 if "gofiber" in p else 1, p))
    return libs


def build_backend_go_chunk_record(
    root: Path,
    chunk: ChunkPlan,
    project_type_dict: dict,
    module_path: str | None,
    uses_fiber: bool,
) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    imports = go.extract_imports(text, module_path)
    structs = go.extract_structs(text)
    interfaces = go.extract_interfaces(text)
    functions = go.extract_functions(text)
    side_effects = go.extract_side_effects(text)
    routes = go.extract_routes(text, uses_fiber)
    middleware = go.extract_middleware(text)
    mw_factories = go.extract_middleware_factories(text)
    group_parents, fiber_roots = go.extract_route_groups(text)

    framework_or_library = _resolve_go_framework_or_library(imports)
    dependencies = [{"path": imp.path, "usedFor": "internal import"} for imp in imports if imp.is_internal]

    important_functions = [
        {
            "name": fn.name,
            "signature": fn.signature,
            "lineRange": list(fn.line_range),
            "codeSnippet": fn.snippet.text,
            "truncated": fn.snippet.truncated,
            "continuationNote": fn.snippet.continuation_note,
            "secretsRedacted": fn.snippet.secrets_redacted,
            "typeParams": fn.type_params,
            "returnsFiberHandler": fn.returns_fiber_handler,
        }
        for fn in functions
    ]
    for entry in important_functions:
        entry.update(build_function_context(
            name=entry["name"],
            signature=entry["signature"],
            line_range=entry["lineRange"],
            lines=lines,
            all_functions=important_functions,
            language="go",
            api_calls=None,
            side_effects=side_effects,
        ))

    data_models_out = [
        {
            "name": s.name,
            "kind": "struct",
            "typeParams": s.type_params,
            "fields": [{"name": n, "type": t} for n, t in s.fields],
            "methods": [],
            "embedded": [],
            "file": chunk.file_path,
            "codeSnippet": s.snippet.text,
            "truncated": s.snippet.truncated,
            "continuationNote": s.snippet.continuation_note,
            "secretsRedacted": s.snippet.secrets_redacted,
        }
        for s in structs
    ]
    # Interfaces are data models with methods only — never invent which
    # concrete type satisfies them (no Impl edges from this extractor).
    for iface in interfaces:
        data_models_out.append({
            "name": iface.name,
            "kind": "interface",
            "typeParams": iface.type_params,
            "fields": [],
            "methods": [{"name": n, "signature": sig} for n, sig in iface.methods],
            "embedded": list(iface.embedded),
            "file": chunk.file_path,
            "codeSnippet": iface.snippet.text,
            "truncated": iface.snippet.truncated,
            "continuationNote": iface.snippet.continuation_note,
            "secretsRedacted": iface.snippet.secrets_redacted,
            "assumed": False,
            "notes": (
                "Interface method set only; concrete implementors are not "
                "inferred (Go satisfaction is implicit)."
            ),
        })

    side_effects_out = [{"type": kind, "description": f"Detected at line {line}"} for kind, line in side_effects]

    routes_out = []
    for r in routes:
        entry = {
            "path": r.path,
            "method": r.method,
            "type": r.static_or_dynamic,
            "routingLibrary": r.routing_library,
            "protected": r.protected,
            "assumed": r.assumed if r.path_resolved is not False else True,
            "handler": r.handler,
            "notes": r.note,
            "routerVar": r.router_var,
            "line": r.line,
            # Ordered middleware chain for this router (ancestors then self).
            "middleware": [
                {
                    "name": mw.name,
                    "order": mw.order,
                    "line": mw.line,
                    "isAuth": mw.is_auth,
                    "isCors": mw.is_cors,
                    "assumed": mw.assumed,
                    "source": mw.source,
                    "routerVar": mw.router_var,
                }
                for mw in go.middleware_chain_for_router(
                    r.router_var, group_parents, middleware, fiber_roots,
                )
            ],
        }
        if r.path_resolved is not None:
            entry["pathResolved"] = r.path_resolved
        if r.prefix_chain:
            entry["prefixChain"] = r.prefix_chain
        routes_out.append(entry)

    middleware_out = [
        {
            "name": mw.name,
            "order": mw.order,
            "line": mw.line,
            "isAuth": mw.is_auth,
            "isCors": mw.is_cors,
            "assumed": mw.assumed,
            "source": mw.source,
            "routerVar": mw.router_var,
        }
        for mw in middleware
    ]

    middleware_factories_out = [
        {
            "name": fac.name,
            "line": fac.line,
            "receiver": fac.receiver,
            "assumed": fac.assumed,
            "notes": fac.note,
        }
        for fac in mw_factories
    ]

    route_groups_out = [
        {
            "var": var,
            "parent": parent,
            "prefix": prefix,  # None when Group(...) used a non-literal expression
        }
        for var, (parent, prefix) in sorted(group_parents.items())
    ]

    total_claims = len(important_functions) + len(routes_out) + len(data_models_out)
    assumed_claims = sum(1 for r in routes_out if r["assumed"])
    confidence = confidence_from_flags(total_claims, assumed_claims)

    notes = []
    if any(fn["truncated"] for fn in important_functions):
        notes.append("One or more function snippets were trimmed to 120 lines; see continuationNote per entry.")
    if routes_out:
        notes.append(
            "Route protection is inferred from local .Use() / Group(..., mw) calls on this "
            "router or its ancestor groups only; verify before relying on it."
        )
    if any(m.get("kind") == "interface" for m in data_models_out):
        notes.append(
            "Interface types list method signatures only; implementors are not inferred."
        )
    if middleware_factories_out:
        notes.append(
            "fiber.Handler-returning funcs are listed as middlewareFactories; "
            "route attachment from the definition alone is assumed/skipped."
        )
    if any(fn["secretsRedacted"] for fn in important_functions) or any(s["secretsRedacted"] for s in data_models_out):
        notes.append("A possible secret was detected and redacted from one or more code snippets in this "
                      "chunk before it was written; verify the source file for exposed credentials.")
        confidence = min(confidence, 0.5)

    record = {
        "chunkId": chunk.chunk_id,
        "filePath": chunk.file_path,
        "featureName": chunk.feature_name,
        "projectType": project_type_dict,
        "stack": chunk.stack,
        "language": detect_language(chunk.file_path),
        "lineRange": [1, len(lines)],
        # The file's own header comment, where it has one: the author's
        # statement of what this file is for, used as the purpose on the
        # file card that introduces each section of the video.
        "fileDescription": file_header_comment(lines),
        "frameworkOrLibrary": framework_or_library,
        "inputs": [],
        "outputs": [],
        "eventHandlers": [],
        "apiCalls": [],
        "importantFunctions": important_functions,
        "sideEffects": side_effects_out,
        "featureMapping": [],
        "dependencies": dependencies,
        "dataModels": data_models_out,
        "routes": routes_out,
        "middleware": middleware_out,
        "middlewareFactories": middleware_factories_out,
        "routeGroups": route_groups_out,
        "usesFiber": uses_fiber,
        "confidence": confidence,
        "confidenceLevel": confidence_level(confidence),
        "notes": " ".join(notes) if notes else None,
        "contentHash": content_hash(root, chunk.file_path),
        # Lets the reuse cache tell a record written by an older
        # extractor from a current one (see storage/mirror_store.py).
        "extractorVersion": EXTRACTOR_VERSION,
        "lastUpdated": now_iso(),
        "pullRequest": None,
        "pullRequestNote": "Not determined: a shallow git clone has no PR metadata, and this phase "
                            "does not call the GitHub API. Required by the rules doc but genuinely "
                            "unavailable here — see the plan's Phase 3 gap note.",
    }

    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack=chunk.stack)
