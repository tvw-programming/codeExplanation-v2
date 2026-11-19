"""Per-stack manifest puts visual-bearing chunks first (Go Fiber preview fix)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_backend_pilot import _bundle_has_visual_clips, _prioritize_visual_chunks


def _write_bundle(path: Path, **fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def test_prioritize_puts_route_tree_chunk_first(tmp_path: Path):
    stack_dir = tmp_path / "go"
    # Simulate Alumni go order: many unavailable files, then main.go with graph.
    plain = ["firebaseauth", "migrate", "handler", "repo"]
    visual = "server-91d1514b"
    for cid in plain:
        _write_bundle(stack_dir / cid / "bundle.json", chunkId=cid, durationMs=1000)
    _write_bundle(
        stack_dir / visual / "bundle.json",
        chunkId=visual,
        visualGraph={"kind": "route_tree", "rootId": "r", "nodes": [], "edges": [{"id": "e"}]},
        treeNarration={"audio": "tree.wav", "durationMs": 3000},
        lifecycleFlows=[{"id": "f", "steps": []}],
        lifecycleNarration={"audio": "lifecycle.wav", "durationMs": 4000},
        breakdownNarration={"audio": "breakdown.wav", "durationMs": 3000},
    )

    ordered = _prioritize_visual_chunks(stack_dir, plain + [visual])
    assert ordered[0] == visual
    assert ordered[1:] == plain
    assert _bundle_has_visual_clips(stack_dir / visual / "bundle.json")
    assert not _bundle_has_visual_clips(stack_dir / plain[0] / "bundle.json")


def test_prioritize_stable_when_none_have_visuals(tmp_path: Path):
    stack_dir = tmp_path / "go"
    ids = ["a", "b", "c"]
    for cid in ids:
        _write_bundle(stack_dir / cid / "bundle.json", chunkId=cid)
    assert _prioritize_visual_chunks(stack_dir, ids) == ids
