"""Angular chunk record builder."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan

from ..common import confidence_from_flags, confidence_level, read_lines
from ..record_base import base_record
from . import extract as ang


def build_angular_chunk_record(
    root: Path,
    chunk: ChunkPlan,
    project_type_dict: dict,
    *,
    selector_index: dict[str, list[ang.SelectorEntry]] | None = None,
) -> dict:
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

    # Template text for mount scan (sibling file or inline).
    template_for_mounts = tmpl or ""
    if not template_for_mounts:
        m = ang.COMPONENT_RE.search(text)
        if m:
            im = ang.TEMPLATE_INLINE_RE.search(m.group("body"))
            if im:
                template_for_mounts = im.group("body")

    index = selector_index if selector_index is not None else ang.build_selector_index(root)
    mounts = ang.extract_template_mounts(comp.name, template_for_mounts, index)

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
    # Same mount shape as React jsxMounts so shared tooling can read parent→child.
    record["jsxMounts"] = [
        {
            "parent": m.parent,
            "child": m.child,
            "selector": m.selector,
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
        for m in mounts
    ]
    record["selector"] = comp.selector

    assumed_claims = sum(1 for m in mounts if m.assumed)
    total_claims = max(
        1,
        len(comp.inputs) + len(comp.outputs) + len(comp.template_events) + len(mounts),
    )
    if mounts or comp.inputs or comp.outputs or comp.template_events:
        conf = confidence_from_flags(total_claims, assumed_claims)
        conf = max(
            conf,
            0.45 if mounts else (0.55 if (comp.inputs or comp.outputs or comp.template_events) else 0.35),
        )
    else:
        conf = 0.35
    record["confidence"] = conf
    record["confidenceLevel"] = confidence_level(conf)

    mount_note = (
        f"{len(mounts)} template mount(s) via project selector index"
        if mounts
        else "no confirmed template child mounts (unmatched tags skipped)"
    )
    bundle_note = ""
    related = chunk.related_files if isinstance(getattr(chunk, "related_files", None), (list, tuple, set)) else []
    if comp.template_url and related:
        from .extract import resolve_template_url_sibling
        sib = resolve_template_url_sibling(root, chunk.file_path, comp.template_url)
        if sib and sib in related:
            bundle_note = f" templateUrl sibling `{sib}` bundled with class."
    record["notes"] = (
        "Angular dedicated extractor (signal input()/output() + selector→usage mounts); "
        f"{mount_note}.{bundle_note} Duplicate selectors skipped; attribute matches assumed."
    )
    record["fidelity"] = "regex"
    from src.visual.pipeline import attach_visuals
    return attach_visuals(record, stack="angular")
