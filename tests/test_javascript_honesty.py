"""Vanilla JavaScript thin honesty enrichments (EXTRACTOR_VERSION 22)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.javascript import extract as js_extract
from src.extract.javascript.record import build_javascript_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION

FIX = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_22_js():
    assert EXTRACTOR_VERSION == 25


def test_literal_named_and_default_exports():
    text = """
export function boot() {}
export { helper as help, unused };
export default App;
exports.legacy = 1;
module.exports = { alpha, beta: 2 };
"""
    facts = js_extract.extract_javascript(text)
    names = {e["name"] for e in facts.exports}
    assert "boot" in names
    assert "help" in names
    assert "unused" in names
    assert "App" in names
    assert "legacy" in names
    assert "alpha" in names
    assert "beta" in names
    assert all(e.get("assumed") is False for e in facts.exports)


def test_literal_dom_mounts_skip_non_literal():
    text = """
const root = document.getElementById('app');
const q = document.querySelector('.panel');
document.getElementById(dynamicId);
querySelector(other);
"""
    facts = js_extract.extract_javascript(text)
    sels = {m["selector"] for m in facts.mounts}
    assert sels == {"app", ".panel"}
    assert all(m["assumed"] is False for m in facts.mounts)


def test_dynamic_import_literal_only():
    text = """
import('./lazy.js');
import(expr);
import { x } from './mod.js';
"""
    facts = js_extract.extract_javascript(text)
    paths = [i["path"] for i in facts.imports]
    assert "./lazy.js" in paths
    assert "./mod.js" in paths
    assert not any(i["path"] == "expr" for i in facts.imports)


def test_js_fixture_record_graph():
    root = FIX / "javascript"
    # Extend fixture content via inline write in tmp would be better —
    # fixture main.js already has import + export + listener.
    rec = build_javascript_chunk_record(
        root,
        ChunkPlan("main", "app", "javascript", "main.js", 20, "small"),
        {"frontend": "javascript", "backend": []},
    )
    assert rec["extractorVersion"] == 25
    export_names = {e["name"] for e in rec["moduleExports"]}
    assert "boot" in export_names
    assert rec["visualGraph"] is not None
    assert rec["visualGraph"]["kind"] == "module_graph"


def test_js_dom_mounts_in_graph(tmp_path: Path):
    p = tmp_path / "boot.js"
    p.write_text(
        "export function boot() {\n"
        "  document.getElementById('root');\n"
        "}\n",
        encoding="utf-8",
    )
    rec = build_javascript_chunk_record(
        tmp_path,
        ChunkPlan("boot", "app", "javascript", "boot.js", 10, "small"),
        {"frontend": "javascript", "backend": []},
    )
    assert rec["domMounts"]
    labels = {n["label"] for n in rec["visualGraph"]["nodes"]}
    assert "root" in labels
    assert any(e["kind"] == "mounts" for e in rec["visualGraph"]["edges"])
