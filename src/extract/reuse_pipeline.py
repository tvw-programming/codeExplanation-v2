"""Phase 4 — the reuse-aware extraction pipeline."""

from __future__ import annotations

from pathlib import Path

from src.detect.project_type import ProjectType
from src.chunk.chunker import chunk_repo
from src.storage.mirror_store import needs_reanalysis, read_stored, write_stored
from src.storage.pull_request_lookup import find_last_pull_request_url
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
from .extractor import _apply_feature_mapping
from .common import read_lines


def _build_record(
    root, chunk, project_type_dict, package_json_dir, base_url, module_path,
    uses_fiber, current_hash, *, angular_selector_index=None, python_route_index=None,
):
    stack = chunk.stack
    if stack == "react":
        return build_frontend_chunk_record(root, chunk, project_type_dict, package_json_dir, base_url)
    if stack == "angular":
        return build_angular_chunk_record(
            root, chunk, project_type_dict, selector_index=angular_selector_index,
        )
    if stack == "go":
        return build_backend_go_chunk_record(root, chunk, project_type_dict, module_path, uses_fiber)
    if stack == "python":
        return build_python_chunk_record(
            root, chunk, project_type_dict, route_index=python_route_index,
        )
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
        "contentHash": current_hash,
    }, stack=stack)


def extract_repo_with_reuse(
    root: str | Path,
    project_type: ProjectType,
    output_root: str | Path,
    github_owner: str | None = None,
    github_repo: str | None = None,
) -> tuple[list[dict], dict, dict[str, str]]:
    root = Path(root)
    output_root = Path(output_root)
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

    angular_selector_index = None
    if any(c.stack == "angular" for c in result.chunks):
        from .angular.extract import build_selector_index
        angular_selector_index = build_selector_index(root)

    python_route_index = None
    if any(c.stack == "python" for c in result.chunks):
        from .python.extract import build_python_route_index
        python_route_index = build_python_route_index(root)

    records: list[dict] = []
    reused_count = 0
    reanalyzed_count = 0

    for chunk in result.chunks:
        stale, current_hash = needs_reanalysis(output_root, root, chunk.file_path)

        if not stale:
            stored = read_stored(output_root, chunk.file_path)
            records.append(stored)
            reused_count += 1
            continue

        record = _build_record(
            root, chunk, project_type_dict, package_json_dir,
            base_url, module_path, uses_fiber, current_hash,
            angular_selector_index=angular_selector_index,
            python_route_index=python_route_index,
        )

        if github_owner and github_repo:
            pr_url = find_last_pull_request_url(github_owner, github_repo, chunk.file_path)
            if pr_url:
                record["pullRequest"] = pr_url
                record["pullRequestNote"] = None

        records.append(record)
        reanalyzed_count += 1

    _apply_feature_mapping(records, result.chunks, base_url)

    for record in records:
        write_stored(output_root, record["filePath"], record)

    chunk_stacks: dict[str, str] = {
        chunk.chunk_id: chunk.stack for chunk in result.chunks
    }

    stats = {"reused": reused_count, "reanalyzed": reanalyzed_count, "total": len(records)}
    return records, stats, chunk_stacks
