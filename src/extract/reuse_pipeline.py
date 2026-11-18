"""Phase 4 — the reuse-aware extraction pipeline.

Wraps Phase 3's per-chunk builders with the storage/reuse rule: before
extracting a chunk, compare its current content hash against the
stored one; a match skips re-analysis entirely and reuses the stored
record, and a mismatch (or no stored record) runs the extractor and
writes the new result to the mirrored folder. featureMapping is always
recomputed over the full set after this pass, since it is cheap and
mechanical — only the per-file extraction itself is skipped on reuse.
"""

from __future__ import annotations

from pathlib import Path

from src.detect.project_type import ProjectType
from src.chunk.chunker import chunk_repo
from src.storage.mirror_store import needs_reanalysis, read_stored, write_stored
from src.storage.pull_request_lookup import find_last_pull_request_url
from .json_builder import build_frontend_chunk_record, build_backend_go_chunk_record
from .ts_extractor import extract_base_url
from .go_extractor import extract_module_path
from .extractor import _apply_feature_mapping
from .common import read_lines


def extract_repo_with_reuse(
    root: str | Path,
    project_type: ProjectType,
    output_root: str | Path,
    github_owner: str | None = None,
    github_repo: str | None = None,
) -> tuple[list[dict], dict]:
    """Returns (records, stats). stats has reused/reanalyzed counts so a
    caller (or test) can verify reuse is actually happening, not just
    trust the code."""
    root = Path(root)
    output_root = Path(output_root)
    result = chunk_repo(root, project_type)
    project_type_dict = project_type.to_dict()

    base_url = None
    for chunk in result.chunks:
        if chunk.stack in ("react", "angular") and "client" in Path(chunk.file_path).stem.lower():
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
    for hit in project_type.marker_hits.get("react_or_angular", []):
        package_json_dir = hit.directory
        break

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

        if chunk.stack in ("react", "angular"):
            record = build_frontend_chunk_record(root, chunk, project_type_dict, package_json_dir, base_url)
        elif chunk.stack == "go":
            record = build_backend_go_chunk_record(root, chunk, project_type_dict, module_path, uses_fiber)
        else:
            record = {
                "chunkId": chunk.chunk_id,
                "filePath": chunk.file_path,
                "featureName": chunk.feature_name,
                "projectType": project_type_dict,
                "notes": f"Extraction for stack '{chunk.stack}' is not yet implemented in Phase 3.",
                "confidence": 0,
                "confidenceLevel": "low",
                "contentHash": current_hash,
            }

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

    stats = {"reused": reused_count, "reanalyzed": reanalyzed_count, "total": len(records)}
    return records, stats
