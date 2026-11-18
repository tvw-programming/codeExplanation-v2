"""Phase 7 — validates an extracted chunk record against the locked
schema in docs/json-structure-rules.md.

Only the fields the rules doc actually marks "required: yes" are
checked for presence and basic shape. pullRequest/contentHash/
lastUpdated are the Phase 4 storage fields the rules doc also calls
required; pullRequest is allowed to be present-but-null (a documented,
accepted gap — see the Phase 3/4 plan writeup), so this checks the KEY
exists, not that its value is non-null, for that one field.
"""

from __future__ import annotations

REQUIRED_CORE_FIELDS = [
    "chunkId", "filePath", "featureName", "projectType", "language",
    "lineRange", "frameworkOrLibrary", "featureMapping", "confidence", "confidenceLevel",
]
REQUIRED_STORAGE_KEYS = ["contentHash", "lastUpdated", "pullRequest"]
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def validate_record(record: dict) -> list[str]:
    """Returns a list of problem strings; empty means the record is
    schema-valid. A record for a not-yet-implemented stack (Phase 3's
    honest placeholder) will legitimately fail several of these —
    that's surfaced as a real gap, not swallowed."""
    problems: list[str] = []
    chunk_id = record.get("chunkId", "<missing chunkId>")

    for field in REQUIRED_CORE_FIELDS:
        if field not in record or record[field] is None:
            problems.append(f"{chunk_id}: missing required field '{field}'")

    for key in REQUIRED_STORAGE_KEYS:
        if key not in record:
            problems.append(f"{chunk_id}: missing required storage key '{key}' (even if null)")

    line_range = record.get("lineRange")
    if isinstance(line_range, list) and len(line_range) == 2:
        start, end = line_range
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            problems.append(f"{chunk_id}: lineRange {line_range} is not a valid [start, end] with start <= end")
    elif "lineRange" in record and record["lineRange"] is not None:
        problems.append(f"{chunk_id}: lineRange is present but not a 2-element list")

    confidence = record.get("confidence")
    if confidence is not None and not (isinstance(confidence, (int, float)) and 0 <= confidence <= 1):
        problems.append(f"{chunk_id}: confidence {confidence} is out of the required 0-1 range")

    confidence_level = record.get("confidenceLevel")
    if confidence_level is not None and confidence_level not in VALID_CONFIDENCE_LEVELS:
        problems.append(f"{chunk_id}: confidenceLevel '{confidence_level}' is not one of {VALID_CONFIDENCE_LEVELS}")

    feature_mapping = record.get("featureMapping")
    if feature_mapping is not None and not isinstance(feature_mapping, list):
        problems.append(f"{chunk_id}: featureMapping must be a list (may be empty)")

    return problems


def validate_records(records: list[dict]) -> dict:
    """Returns {"problems": {chunkId: [..]}, "validCount": n, "invalidCount": n, "total": n}."""
    problems_by_chunk: dict[str, list[str]] = {}
    for record in records:
        chunk_id = record.get("chunkId", "<missing chunkId>")
        problems = validate_record(record)
        if problems:
            problems_by_chunk[chunk_id] = problems

    total = len(records)
    invalid = len(problems_by_chunk)
    return {
        "problems": problems_by_chunk,
        "validCount": total - invalid,
        "invalidCount": invalid,
        "total": total,
    }
