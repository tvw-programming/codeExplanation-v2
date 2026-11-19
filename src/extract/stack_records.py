"""Per-stack chunk record builders for stacks beyond React/Go."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.storage.mirror_store import EXTRACTOR_VERSION
from .common import (
    content_hash,
    detect_language,
    now_iso,
    confidence_from_flags,
    confidence_level,
    read_lines,
)
from .function_context import file_header_comment
from . import python_extractor as py
from . import express_extractor as ex
from . import spring_extractor as spring
from . import angular_extractor as ang
from . import vue_extractor as vue
from . import solid_extractor as solid
from . import qwik_extractor as qwik
from . import javascript_extractor as js
from . import rust_extractor as rust


def _base(root: Path, chunk: ChunkPlan, project_type_dict: dict, lines: list[str]) -> dict:
    return {
        "chunkId": chunk.chunk_id,
        "filePath": chunk.file_path,
        "featureName": chunk.feature_name,
        "projectType": project_type_dict,
        "stack": chunk.stack,
        "language": detect_language(chunk.file_path),
        "lineRange": [1, len(lines)],
        "fileDescription": file_header_comment(lines),
        "frameworkOrLibrary": [],
        "inputs": [],
        "outputs": [],
        "eventHandlers": [],
        "apiCalls": [],
        "importantFunctions": [],
        "sideEffects": [],
        "featureMapping": [],
        "dependencies": [],
        "dataModels": [],
        "routes": [],
        "contentHash": content_hash(root, chunk.file_path),
        "extractorVersion": EXTRACTOR_VERSION,
        "lastUpdated": now_iso(),
        "pullRequest": None,
        "pullRequestNote": "Not determined: shallow clone / no GitHub API in this phase.",
    }


def build_python_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    functions, routes, imports, _all = py.extract_python(text)
    record = _base(root, chunk, project_type_dict, lines)
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
    record["notes"] = "Python via stdlib ast; cross-file router prefixes unresolved stay assumed."
    record["fidelity"] = "syntax"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="python")


def build_express_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    routes, middleware, mounts = ex.extract_express(text)
    record = _base(root, chunk, project_type_dict, lines)
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
    record["notes"] = "Express in-file routes; cross-file app.use prefixes may be incomplete (assumed)."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="express")


def build_spring_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    types, routes = spring.extract_spring(text)
    record = _base(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = ["spring-boot"] if types else []
    record["springTypes"] = [
        {
            "name": t.name,
            "stereotype": t.stereotype,
            "classPath": t.class_path,
            "line": t.line,
            "injectees": t.injectees,
            "methods": t.methods,
        }
        for t in types
    ]
    record["routes"] = [
        {
            "method": r.method,
            "path": r.path,
            "handler": r.handler,
            "assumed": r.assumed,
            "line": r.line,
            "controller": r.controller,
            "protected": r.has_security,
            "middleware": [],
        }
        for r in routes
    ]
    # DI edges live on springTypes — never derived from imports.
    assumed = sum(1 for r in routes if r.assumed)
    conf = confidence_from_flags(max(1, len(types) + len(routes)), assumed)
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Spring DI is by type (constructor/field); imports are never treated as injects."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack=chunk.stack)


def build_angular_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    # Peek for templateUrl then load sibling
    prelim = ang.extract_angular_component(text, None)
    tmpl = None
    if prelim and prelim.template_url:
        tmpl = ang.load_template_sibling(root, chunk.file_path, prelim.template_url)
    comp = ang.extract_angular_component(text, tmpl)
    record = _base(root, chunk, project_type_dict, lines)
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
        {"name": e["handler"], "lineRange": [comp.line, comp.line], "assumed": e.get("assumed", False), "event": e["event"]}
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
    # Selector usage as mounts: self → referenced selectors not resolved project-wide
    record["jsxMounts"] = []  # not JSX; angular tree uses angularComponent + inputs
    record["selector"] = comp.selector
    conf = 0.55 if (comp.inputs or comp.outputs or comp.template_events) else 0.35
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Angular dedicated extractor; project-wide selector index not built — tree is this component unit."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="angular")


def build_vue_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    sfc = vue.extract_vue_sfc(text)
    record = _base(root, chunk, project_type_dict, lines)
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
    record = _base(root, chunk, project_type_dict, lines)
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
    record = _base(root, chunk, project_type_dict, lines)
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
    record = _base(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = []
    record["moduleImports"] = facts.imports
    record["moduleExports"] = facts.exports
    record["eventHandlers"] = [
        {"name": l["handler"], "lineRange": [l["line"], l["line"]], "assumed": l["assumed"], "event": l["event"]}
        for l in facts.listeners
    ]
    record["securityHints"] = [
        {"id": f"sink-{s['kind']}-{s['line']}", "ruleId": s["kind"], "severity": "high",
         "message": f"Dangerous {s['kind']} sink at line {s['line']}.", "assumed": False}
        for s in facts.sinks
    ]
    conf = 0.5 if facts.imports or facts.listeners else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Vanilla JS module/DOM extract."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="javascript")


def build_rust_chunk_record(root: Path, chunk: ChunkPlan, project_type_dict: dict) -> dict:
    lines = read_lines(root, chunk.file_path)
    text = "\n".join(lines)
    facts = rust.extract_rust(text)
    record = _base(root, chunk, project_type_dict, lines)
    record["frameworkOrLibrary"] = sorted({r.get("framework") for r in facts.routes if r.get("framework")})
    record["rustModules"] = facts.modules
    record["rustUses"] = facts.uses
    record["importantFunctions"] = [
        {"name": f["name"], "lineRange": [f["line"], f["line"]], "calls": [], "sideEffects": []}
        for f in facts.functions
    ]
    record["routes"] = [
        {
            "method": r["method"],
            "path": r["path"],
            "handler": "handler",
            "assumed": r["assumed"],
            "line": r["line"],
            "middleware": [],
            "protected": False,
        }
        for r in facts.routes
    ]
    record["unsafeBlocks"] = facts.unsafe_blocks
    conf = 0.45 if facts.routes or facts.modules else 0.3
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)
    record["notes"] = "Rust regex extract; macro-generated routes may be missing (partial)."
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="rust")
