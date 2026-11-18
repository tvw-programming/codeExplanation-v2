"""Phase 5 — continuity glossary across chunks.

Per the locked rule: keep a glossary keyed by stable chunk IDs, one
canonical name and a short summary per chunk; use back-references and
forward previews only where featureMapping shows a real link; process
dependencies first so later chunks can point back to earlier ones.

"Dependency-first" is resolved here with a topological sort over the
featureMapping edges. featureMapping is a symmetric, undirected list of
chunkIds (see extractor.py — a link is written onto both ends), not a
directed dependency graph, so there is no single correct dependency
order to recover from it. The order used here is deterministic rather
than "correct": process chunks with fewer not-yet-seen links first,
breaking ties by chunkId, so that a chunk's first-seen neighbors become
its "earlier" (back-reference) set and the rest become "later"
(forward-preview) candidates. This heuristic is documented here rather
than presented as a real dependency analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GlossaryEntry:
    chunk_id: str
    canonical_name: str
    summary: str


class ContinuityGlossary:
    def __init__(self) -> None:
        self._entries: dict[str, GlossaryEntry] = {}
        self._order: list[str] = []

    def register(self, chunk_id: str, canonical_name: str, summary: str) -> None:
        if chunk_id not in self._entries:
            self._order.append(chunk_id)
        self._entries[chunk_id] = GlossaryEntry(chunk_id, canonical_name, summary)

    def get(self, chunk_id: str) -> GlossaryEntry | None:
        return self._entries.get(chunk_id)

    def processed_before(self, chunk_id: str) -> list[str]:
        """Chunk ids registered strictly before this one, in registration order."""
        if chunk_id not in self._order:
            return list(self._order)
        return self._order[: self._order.index(chunk_id)]


def dependency_first_order(records: list[dict]) -> list[str]:
    """Returns chunkIds ordered so each chunk's already-registered
    featureMapping links are processed first. Deterministic tie-break
    by chunkId so re-running on the same input always gives the same
    order."""
    remaining = {r["chunkId"]: set(r.get("featureMapping") or []) for r in records}
    processed: list[str] = []
    processed_set: set[str] = set()

    while remaining:
        # Pick the chunk with the fewest not-yet-processed links; ties
        # broken by chunkId for determinism.
        def unresolved_count(chunk_id: str) -> int:
            return len(remaining[chunk_id] - processed_set)

        next_id = min(remaining.keys(), key=lambda cid: (unresolved_count(cid), cid))
        processed.append(next_id)
        processed_set.add(next_id)
        del remaining[next_id]

    return processed


def back_references(chunk_id: str, record: dict, glossary: "ContinuityGlossary") -> list[str]:
    """featureMapping links that point to chunks already registered in
    the glossary before this one — a real, already-established link."""
    links = set(record.get("featureMapping") or [])
    earlier = set(glossary.processed_before(chunk_id))
    return sorted(links & earlier)


def forward_previews(chunk_id: str, record: dict, all_chunk_ids: set[str], glossary: "ContinuityGlossary") -> list[str]:
    """featureMapping links to real chunks not yet registered before
    this one — a genuine later call, previewed rather than explained."""
    links = set(record.get("featureMapping") or [])
    earlier = set(glossary.processed_before(chunk_id))
    return sorted((links & all_chunk_ids) - earlier - {chunk_id})
