"""Phase 3 — assembles the final per-chunk JSON record against the full
schema in docs/json-structure-rules.md.

This is the integration point: it calls the TS/Go extractors, resolves
frameworkOrLibrary against the repo's actual package.json/go.mod,
computes confidence from how many claims had to be marked assumed, and
fills contentHash/lastUpdated per the Phase 4 storage rule.

pullRequest (required by the rules doc) is a known, documented gap: a
shallow git clone has no GitHub PR metadata, and this phase does not
call the GitHub API. It is left as null with an explanatory note and
pulls the chunk's confidence down, rather than being faked. See the
plan doc for this limitation and how to close it (a GitHub API lookup
keyed by the file path).
"""

from __future__ import annotations

import json as json_mod
from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.storage.mirror_store import EXTRACTOR_VERSION
from .function_context import build_function_context, file_header_comment
from .common import (
    detect_language, read_lines, content_hash, now_iso,
    confidence_from_flags, confidence_level,
)
from . import ts_extractor as ts
from . import go_extractor as go

TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
GO_EXTENSION = ".go"


def _read_package_json_deps(root: Path, package_json_dir: str) -> dict[str, str]:
    path = root / package_json_dir / "package.json" if package_json_dir else root / "package.json"
    try:
        data = json_mod.loads(path.read_text(encoding="utf-8"))
    except (OSError, json_mod.JSONDecodeError):
        return {}
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


def _resolve_frontend_framework_or_library(imports: list[ts.ImportInfo], known_deps: set[str]) -> list[str]:
    libs: list[str] = []
    for imp in imports:
        if imp.is_internal:
            continue
        # An import source like '@mui/icons-material/Add' should match
        # the package '@mui/icons-material', not fail to match at all.
        candidate = imp.source
        if candidate in known_deps:
            libs.append(candidate)
            continue
        if candidate.startswith("@"):
            parts = candidate.split("/")
            scoped = "/".join(parts[:2]) if len(parts) >= 2 else candidate
            if scoped in known_deps:
                libs.append(scoped)
                continue
        else:
            top = candidate.split("/")[0]
            if top in known_deps:
                libs.append(top)
                continue
    # Stable order, primary (most-imported) first.
    seen_order: list[str] = []
    counts: dict[str, int] = {}
    for lib in libs:
        counts[lib] = counts.get(lib, 0) + 1
        if lib not in seen_order:
            seen_order.append(lib)
    seen_order.sort(key=lambda l: -counts[l])
    return seen_order


def _resolve_go_framework_or_library(imports: list[go.GoImport]) -> list[str]:
    libs = [imp.path for imp in imports if not imp.is_stdlib and not imp.is_internal]
    # Fiber first if present, since it's the defining framework for this stack.
    libs.sort(key=lambda p: (0 if "gofiber" in p else 1, p))
    return libs


def build_frontend_chunk_record(
    root: Path,
    chunk: ChunkPlan,
    project_type_dict: dict,
    package_json_dir: str,
    base_url: str | None,
) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    imports = ts.extract_imports(text)
    models = ts.extract_interfaces(text)
    functions = ts.extract_functions(text)
    handlers = ts.extract_event_handlers(text, functions)
    api_calls = ts.extract_api_calls(text)
    side_effects = ts.extract_side_effects(text)

    known_deps = set(_read_package_json_deps(root, package_json_dir))
    framework_or_library = _resolve_frontend_framework_or_library(imports, known_deps)

    dependencies = [
        {"path": imp.source, "usedFor": "internal import"}
        for imp in imports if imp.is_internal
    ]

    component_name = Path(chunk.file_path).stem
    props_model = ts.find_props_interface(component_name, models)
    inputs = (
        [{"name": f.name, "type": f.type, "default": None, "description": None} for f in props_model.fields]
        if props_model else []
    )

    # React visual Slice A: JSX mounts, hooks, HTML sinks. Angular shares
    # this builder today but attach_visuals will mark its visuals unavailable.
    jsx_mounts, jsx_providers = ts.extract_jsx_mounts(text, functions, component_name)
    hooks = ts.extract_hooks(text, functions, component_name)
    html_sinks = ts.extract_html_sink_hints(text)
    callback_outputs = ts.callback_outputs_from_mounts(jsx_mounts)

    important_functions = [
        {
            "name": fn.name,
            "signature": fn.signature,
            "lineRange": list(fn.line_range),
            "codeSnippet": fn.snippet.text,
            "truncated": fn.snippet.truncated,
            "continuationNote": fn.snippet.continuation_note,
            "secretsRedacted": fn.snippet.secrets_redacted,
        }
        for fn in functions if not fn.is_event_handler
    ]
    # Second pass: the call graph needs every function's line range, so
    # the context can only be built once the list above exists.
    for entry in important_functions:
        entry.update(build_function_context(
            name=entry["name"],
            signature=entry["signature"],
            line_range=entry["lineRange"],
            lines=lines,
            all_functions=important_functions,
            language="ts",
            api_calls=api_calls,
            side_effects=side_effects,
        ))

    event_handlers = [
        {
            "name": h.name,
            "signature": h.signature,
            "description": None,
            "eventType": h.event_type,
            # The extractor already knows which line each handler sits
            # on (ExtractedEventHandler.line); carrying it through as a
            # lineRange is what lets Phase 5 generate a VISUAL cue for
            # the handler, so the narration's "the X handler responds
            # to..." sentence can actually highlight the line it is
            # talking about. Single-line range: regex extraction knows
            # where the handler is bound, not where its body ends.
            "lineRange": [h.line, h.line],
            "assumed": h.assumed,
            "notes": h.note,
        }
        for h in handlers
    ]

    api_calls_out = [
        {
            "method": c.method,
            "url": c.url,
            "urlPattern": c.url if c.url_is_template else None,
            "assumed": c.url_is_template,
            "headers": None,
            "queryParams": None,
            "sampleRequestBody": None,
            "sampleResponse": None,
            "line": c.line,
        }
        for c in api_calls
    ]

    jsx_mounts_out = [
        {
            "parent": m.parent,
            "child": m.child,
            "line": m.line,
            "assumed": m.assumed,
            "note": m.note,
            "props": [
                {
                    "name": p.name,
                    "valueKind": p.value_kind,
                    "valuePreview": p.value_preview,
                    "assumed": p.assumed,
                }
                for p in m.props
            ],
        }
        for m in jsx_mounts
    ]
    jsx_providers_out = [
        {"name": p.name, "line": p.line, "assumed": p.assumed} for p in jsx_providers
    ]
    hooks_out = [
        {
            "name": h.name,
            "kind": h.kind,
            "line": h.line,
            "owner": h.owner,
            "assumed": h.assumed,
        }
        for h in hooks
    ]
    security_hints = [
        {
            "id": h.id,
            "ruleId": h.rule_id,
            "message": h.message,
            "line": h.line,
            "severity": h.severity,
            "assumed": h.assumed,
        }
        for h in html_sinks
    ]

    side_effects_out = [{"type": kind, "description": f"Detected at line {line}"} for kind, line in
                         [(e.kind, e.line) for e in side_effects]]

    data_models_out = [
        {
            "name": m.name,
            "fields": [{"name": f.name, "type": f.type} for f in m.fields],
            "file": chunk.file_path,
            "codeSnippet": m.snippet.text,
            "truncated": m.snippet.truncated,
            "continuationNote": m.snippet.continuation_note,
            "secretsRedacted": m.snippet.secrets_redacted,
        }
        for m in models
    ]

    total_claims = len(important_functions) + len(event_handlers) + len(api_calls_out) + len(data_models_out)
    assumed_claims = sum(1 for h in event_handlers if h["assumed"]) + sum(1 for c in api_calls_out if c["assumed"])
    confidence = confidence_from_flags(total_claims, assumed_claims)

    notes = []
    if not props_model and inputs == []:
        notes.append(f"No {component_name}Props interface found; inputs left empty rather than guessed.")
    if any(fn["truncated"] for fn in important_functions):
        notes.append("One or more function snippets were trimmed to 120 lines; see continuationNote per entry.")
    if any(fn["secretsRedacted"] for fn in important_functions) or any(m["secretsRedacted"] for m in data_models_out):
        notes.append("A possible secret was detected and redacted from one or more code snippets in this "
                      "chunk before it was written; verify the source file for exposed credentials.")
        confidence = min(confidence, 0.5)

    # Prefer named-function body ranges on event handlers when available,
    # so lifecycle steps can associate apiCalls inside the handler.
    handler_bodies = {fn.name: list(fn.line_range) for fn in functions if fn.is_event_handler}
    for h in event_handlers:
        if h["name"] in handler_bodies and not h["assumed"]:
            h["lineRange"] = handler_bodies[h["name"]]

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
        "inputs": inputs,
        "outputs": callback_outputs,
        "eventHandlers": event_handlers,
        "apiCalls": api_calls_out,
        "importantFunctions": important_functions,
        "sideEffects": side_effects_out,
        "jsxMounts": jsx_mounts_out,
        "jsxProviders": jsx_providers_out,
        "hooks": hooks_out,
        "securityHints": security_hints,
        "featureMapping": [],   # filled in by the orchestrator once all chunks are extracted
        "dependencies": dependencies,
        "dataModels": data_models_out,
        "routes": [],
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
    functions = go.extract_functions(text)
    side_effects = go.extract_side_effects(text)
    routes = go.extract_routes(text, uses_fiber)
    middleware = go.extract_middleware(text)
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
            "fields": [{"name": n, "type": t} for n, t in s.fields],
            "file": chunk.file_path,
            "codeSnippet": s.snippet.text,
            "truncated": s.snippet.truncated,
            "continuationNote": s.snippet.continuation_note,
            "secretsRedacted": s.snippet.secrets_redacted,
        }
        for s in structs
    ]

    side_effects_out = [{"type": kind, "description": f"Detected at line {line}"} for kind, line in side_effects]

    routes_out = [
        {
            "path": r.path,
            "method": r.method,
            "type": r.static_or_dynamic,
            "routingLibrary": r.routing_library,
            "protected": r.protected,
            "assumed": r.assumed,
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
        for r in routes
    ]

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

    route_groups_out = [
        {
            "var": var,
            "parent": parent,
            "prefix": prefix,
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
