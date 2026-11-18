"""Phase 5 — VISUAL[HIGHLIGHT:id] cue token generation.

Per the locked rule: store the word index for each cue token (Phase 6's
job, once a real WhisperX transcript exists) and map each cue id to a
line range now. A cue is only generated for a record field that
actually carries a lineRange in the Phase 3 schema — today that is
importantFunctions and routes' handler line (when present as part of
the function it maps to) and dataModels do NOT carry a lineRange in
the locked schema (only a code snippet), so no cue is fabricated for
those; this is an honest gap, not an oversight. eventHandlers also
carry no lineRange in the current extractor output, for the same
reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG_NON_ALNUM_RE.sub("-", name.lower()).strip("-")
    return slug or "cue"


@dataclass
class VisualCue:
    id: str
    token: str
    line_range: list[int]
    label: str
    source_field: str


CUE_SOURCE_FIELDS = ("importantFunctions", "eventHandlers", "routes")


def generate_visual_cues(record: dict) -> list[VisualCue]:
    """Builds one cue per record entry that carries a usable lineRange,
    across every field in CUE_SOURCE_FIELDS. Ids are de-duplicated
    against the chunk's own chunkId so cues stay unique within and
    across chunks.

    An entry with no lineRange still produces no cue — that remains an
    honest gap rather than a fabricated line number. dataModels carry
    only a snippet in the locked schema, so they are still excluded.
    """
    chunk_id = record.get("chunkId", "chunk")
    seen: set[str] = set()
    cues: list[VisualCue] = []

    for source_field in CUE_SOURCE_FIELDS:
        for entry in record.get(source_field, []) or []:
            line_range = entry.get("lineRange")
            if not line_range or len(line_range) != 2:
                continue
            label = entry.get("name") or entry.get("path") or ""
            base_id = f"{chunk_id}-{slugify(label or source_field)}"
            cue_id = base_id
            suffix = 1
            while cue_id in seen:
                suffix += 1
                cue_id = f"{base_id}-{suffix}"
            seen.add(cue_id)
            cues.append(VisualCue(
                id=cue_id,
                token=f"VISUAL[HIGHLIGHT:{cue_id}]",
                line_range=list(line_range),
                label=label,
                source_field=source_field,
            ))

    return cues
