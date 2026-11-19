"""Phase 3 — orchestrator: runs extraction for every chunk the Phase 2
chunker planned, then links frontend calls to backend routes into
featureMapping, plus same-feature sibling links.
"""

from __future__ import annotations

from pathlib import Path

from src.detect.project_type import ProjectType
from src.chunk.chunker import chunk_repo
from .json_builder import build_frontend_chunk_record, build_backend_go_chunk_record
from .stack_records import (
    build_python_chunk_record,
    build_express_chunk_record,
    build_spring_chunk_record,
    build_angular_chunk_record,
    build_vue_chunk_record,
    build_solid_chunk_record,
    build_qwik_chunk_record,
    build_javascript_chunk_record,
    build_rust_chunk_record,
)
from .ts_extractor import extract_base_url
from .go_extractor import extract_module_path
from .feature_mapping import match_calls_to_routes
from .common import read_lines


def _build_record(root, chunk, project_type, project_type_dict, package_json_dir, base_url, module_path, uses_fiber):
    stack = chunk.stack
    if stack == "react":
        return build_frontend_chunk_record(root, chunk, project_type_dict, package_json_dir, base_url)
    if stack == "angular":
        return build_angular_chunk_record(root, chunk, project_type_dict)
    if stack == "go":
        return build_backend_go_chunk_record(root, chunk, project_type_dict, module_path, uses_fiber)
    if stack == "python":
        return build_python_chunk_record(root, chunk, project_type_dict)
    if stack == "express":
        return build_express_chunk_record(root, chunk, project_type_dict)
    if stack in ("spring_boot", "java"):
        return build_spring_chunk_record(root, chunk, project_type_dict)
    if stack == "vue":
        return build_vue_chunk_record(root, chunk, project_type_dict)
    if stack == "solid":
        return build_solid_chunk_record(root, chunk, project_type_dict)
    if stack == "qwik":
        return build_qwik_chunk_record(root, chunk, project_type_dict)
    if stack == "javascript":
        return build_javascript_chunk_record(root, chunk, project_type_dict)
    if stack == "rust":
        return build_rust_chunk_record(root, chunk, project_type_dict)

    from src.visual.pipeline import attach_visuals
    return attach_visuals({
        "chunkId": chunk.chunk_id,
        "filePath": chunk.file_path,
        "featureName": chunk.feature_name,
        "projectType": project_type_dict,
        "stack": stack,
        "notes": f"Extraction for stack '{stack}' is not yet implemented in Phase 3.",
        "confidence": 0,
        "confidenceLevel": "low",
    }, stack=stack)


def extract_repo(root: str | Path, project_type: ProjectType) -> list[dict]:
    root = Path(root)
    result = chunk_repo(root, project_type)
    project_type_dict = project_type.to_dict()

    base_url = None
    for chunk in result.chunks:
        if chunk.stack in ("react", "angular", "vue", "solid", "qwik") and "client" in Path(chunk.file_path).stem.lower():
            text = "\n".join(read_lines(root, chunk.file_path))
            found = extract_base_url(text)
            if found:
                base_url = found
                break

    module_path = None
    uses_fiber = False
    for hit in project_type.marker_hits.get("go", []):
        go_mod_path = root / hit.directory / "go.mod" if hit.directory else root / "go.mod"
        try:
            mod_text = go_mod_path.read_text(encoding="utf-8")
            module_path = module_path or extract_module_path(mod_text)
            uses_fiber = uses_fiber or ("gofiber/fiber" in mod_text)
        except OSError:
            continue

    package_json_dir = ""
    for hit in (project_type.marker_hits.get("js_ecosystem") or project_type.marker_hits.get("react_or_angular") or []):
        package_json_dir = hit.directory
        break

    records: list[dict] = []
    for chunk in result.chunks:
        records.append(_build_record(
            root, chunk, project_type, project_type_dict,
            package_json_dir, base_url, module_path, uses_fiber,
        ))

    _apply_feature_mapping(records, result.chunks, base_url)
    return records


def _apply_feature_mapping(records: list[dict], chunks, base_url: str | None) -> None:
    by_chunk_id = {r["chunkId"]: r for r in records}

    by_feature: dict[str, list[str]] = {}
    for chunk in chunks:
        by_feature.setdefault((chunk.feature_name, chunk.stack), []).append(chunk.chunk_id)
    for (feature_name, stack), chunk_ids in by_feature.items():
        for cid in chunk_ids:
            if cid not in by_chunk_id:
                continue
            siblings = [c for c in chunk_ids if c != cid]
            existing = by_chunk_id[cid].setdefault("featureMapping", [])
            for s in siblings:
                if s not in existing:
                    existing.append(s)

    frontend_calls = []
    backend_routes = []
    for record in records:
        for call in record.get("apiCalls", []):
            frontend_calls.append((record["chunkId"], call["method"], call["url"], call["assumed"]))
        for route in record.get("routes", []):
            backend_routes.append((record["chunkId"], route["method"], route["path"], route["assumed"]))

    links = match_calls_to_routes(frontend_calls, backend_routes, base_url)
    for link in links:
        fe_mapping = by_chunk_id[link.frontend_chunk_id].setdefault("featureMapping", [])
        if link.backend_chunk_id not in fe_mapping:
            fe_mapping.append(link.backend_chunk_id)
        be_mapping = by_chunk_id[link.backend_chunk_id].setdefault("featureMapping", [])
        if link.frontend_chunk_id not in be_mapping:
            be_mapping.append(link.frontend_chunk_id)
