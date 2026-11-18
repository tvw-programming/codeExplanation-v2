"""Phase 5 — orchestrator: turns a repo's extracted chunk records
(Phase 3/4 output) into a narration script per chunk, processing
dependencies first per the locked continuity rule.
"""

from __future__ import annotations

from .glossary import ContinuityGlossary, dependency_first_order, back_references, forward_previews
from .pronunciation import build_pronunciation_table
from .script_builder import build_narration_script, NarrationScript
from .visual_cues import VisualCue


def _canonical_name(record: dict) -> str:
    return record.get("featureName") or record.get("chunkId", "")


def _summary(record: dict) -> str:
    framework = (record.get("frameworkOrLibrary") or [None])[0]
    if framework:
        return f"{_canonical_name(record)} ({framework})"
    return _canonical_name(record)


def _collect_identifiers(record: dict, cues: list[VisualCue]) -> list[str]:
    identifiers: list[str] = []
    for fn in record.get("importantFunctions") or []:
        if fn.get("name"):
            identifiers.append(fn["name"])
    for handler in record.get("eventHandlers") or []:
        if handler.get("name"):
            identifiers.append(handler["name"])
    for route in record.get("routes") or []:
        if route.get("path"):
            identifiers.append(route["path"])
    for model in record.get("dataModels") or []:
        if model.get("name"):
            identifiers.append(model["name"])
    identifiers.append(record.get("featureName", ""))
    return identifiers


def generate_narration_for_repo(records: list[dict]) -> dict[str, dict]:
    """Returns {chunkId: {"script": NarrationScript, "pronunciationTable": {...}}}
    for every record, processed in dependency-first order so each
    chunk's glossary back-references are genuinely already registered."""
    order = dependency_first_order(records)
    by_id = {r["chunkId"]: r for r in records}
    all_ids = set(by_id.keys())

    glossary = ContinuityGlossary()
    results: dict[str, dict] = {}

    for chunk_id in order:
        record = by_id[chunk_id]
        back = back_references(chunk_id, record, glossary)
        # Register this chunk now, so forward_previews below can tell
        # apart "already processed" vs "still ahead" correctly relative
        # to this chunk's own position.
        glossary.register(chunk_id, _canonical_name(record), _summary(record))
        forward = forward_previews(chunk_id, record, all_ids, glossary)

        back_entries = [glossary.get(cid) for cid in back if glossary.get(cid)]
        # Forward-linked chunks aren't registered yet; use their own
        # record to name them rather than failing.
        forward_entries = [
            type(glossary.get(chunk_id))(cid, _canonical_name(by_id[cid]), _summary(by_id[cid]))
            for cid in forward if cid in by_id
        ]

        script = build_narration_script(record, back_entries, forward_entries)
        pronunciation_table = build_pronunciation_table(_collect_identifiers(record, script.visual_cues))

        results[chunk_id] = {
            "script": script,
            "pronunciationTable": pronunciation_table,
            # Phase 6 needs a few record fields (filePath, featureName)
            # to title the rendered section; carry the record rather
            # than re-reading it from disk downstream.
            "record": record,
        }

    return results
