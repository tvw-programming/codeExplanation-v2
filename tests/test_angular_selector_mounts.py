"""Angular selector index → template usage mounts (honesty-preserving)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.angular import (
    build_angular_chunk_record,
    build_selector_index,
    extract_template_mounts,
    parse_selector_fragments,
)
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present
from src.visual.graph_builder import build_angular_selector_tree


def test_extractor_version_is_10():
    assert EXTRACTOR_VERSION == 11


def test_parse_selector_fragments_honesty():
    assert parse_selector_fragments("app-user-card") == [("element", "app-user-card")]
    assert parse_selector_fragments("[appHighlight]") == [("attribute", "apphighlight")]
    assert parse_selector_fragments("app-x, [appX]") == [
        ("element", "app-x"),
        ("attribute", "appx"),
    ]
    # Class selectors and HTML builtins are skipped (high invent risk).
    assert parse_selector_fragments(".foo") == []
    assert parse_selector_fragments("div") == []
    assert parse_selector_fragments("button[type=submit]") == []


def test_unmatched_custom_tag_skipped(tmp_path: Path):
    """Custom tags with no index entry must not invent a child node."""
    (tmp_path / "parent.ts").write_text(
        "@Component({ selector: 'app-parent', template: `<app-ghost></app-ghost>` })\n"
        "export class Parent {}\n"
    )
    idx = build_selector_index(tmp_path)
    mounts = extract_template_mounts("Parent", "<app-ghost></app-ghost>", idx)
    assert mounts == []


def test_duplicate_selector_skipped(tmp_path: Path):
    """Two components claiming the same selector → skip, do not pick a winner."""
    (tmp_path / "a.ts").write_text(
        "@Component({ selector: 'app-dup', template: 'a' })\nexport class DupA {}\n"
    )
    (tmp_path / "b.ts").write_text(
        "@Component({ selector: 'app-dup', template: 'b' })\nexport class DupB {}\n"
    )
    idx = build_selector_index(tmp_path)
    mounts = extract_template_mounts("Host", "<app-dup></app-dup>", idx)
    assert mounts == []


def test_confirmed_element_mount_and_ngfor_assumed(tmp_path: Path):
    (tmp_path / "child.ts").write_text(
        "@Component({ selector: 'app-child', template: '<span></span>' })\n"
        "export class ChildComponent {}\n"
    )
    (tmp_path / "parent.ts").write_text(
        "@Component({ selector: 'app-parent', template: `\n"
        "  <app-child [name]=\"n\"></app-child>\n"
        "  <div *ngFor=\"let x of items\"><app-child></app-child></div>\n"
        "` })\n"
        "export class ParentComponent {\n"
        "  n = 'x';\n"
        "  items = [];\n"
        "}\n"
    )
    idx = build_selector_index(tmp_path)
    assert "app-child" in idx
    tmpl = (
        "  <app-child [name]=\"n\"></app-child>\n"
        "  <div *ngFor=\"let x of items\"><app-child></app-child></div>\n"
    )
    mounts = extract_template_mounts("ParentComponent", tmpl, idx)
    static = [m for m in mounts if not m.assumed]
    dyn = [m for m in mounts if m.assumed]
    assert len(static) == 1
    assert static[0].child == "ChildComponent"
    assert static[0].props and static[0].props[0].name == "name"
    assert len(dyn) == 1
    assert dyn[0].child == "ChildComponent"
    assert "ngFor" in (dyn[0].note or "") or "cardinality" in (dyn[0].note or "")


def test_attribute_selector_mount_is_assumed(tmp_path: Path):
    (tmp_path / "hl.ts").write_text(
        "@Component({ selector: '[appHighlight]', template: '<ng-content></ng-content>' })\n"
        "export class HighlightDirective {}\n"
    )
    idx = build_selector_index(tmp_path)
    mounts = extract_template_mounts("Host", "<p appHighlight>x</p>", idx)
    assert len(mounts) == 1
    assert mounts[0].child == "HighlightDirective"
    assert mounts[0].assumed is True


def test_imports_alone_do_not_invent_mounts(tmp_path: Path):
    """standalone imports: [Child] without template usage → no mount edge."""
    (tmp_path / "child.ts").write_text(
        "@Component({ selector: 'app-child', template: '<span></span>' })\n"
        "export class Child {}\n"
    )
    (tmp_path / "parent.ts").write_text(
        "import { Child } from './child';\n"
        "@Component({ selector: 'app-parent', imports: [Child], template: `<div></div>` })\n"
        "export class Parent {}\n"
    )
    record = build_angular_chunk_record(
        tmp_path,
        ChunkPlan("Parent", "UI", "angular", "parent.ts", 20, "small"),
        {"frontend": "angular", "backend": []},
    )
    assert record["jsxMounts"] == []
    # Still has selector/provides edge from own metadata — not a child mount
    kinds = {e["kind"] for e in (record["visualGraph"] or {}).get("edges", [])}
    assert "mounts" not in kinds


def test_chunk_record_emits_mount_edges(tmp_path: Path):
    (tmp_path / "child.component.ts").write_text(
        "@Component({ selector: 'app-child', template: '<span></span>' })\n"
        "export class ChildComponent {}\n"
    )
    (tmp_path / "parent.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-parent',\n"
        "  template: `<app-child [label]=\"'hi'\"></app-child>`,\n"
        "})\n"
        "export class ParentComponent {}\n"
    )
    record = build_angular_chunk_record(
        tmp_path,
        ChunkPlan("ParentComponent", "UI", "angular", "parent.component.ts", 30, "small"),
        {"frontend": "angular", "backend": []},
    )
    assert record["extractorVersion"] == 11
    assert is_present(record["visualAvailability"]["componentTree"])
    assert len(record["jsxMounts"]) == 1
    mount = record["jsxMounts"][0]
    assert mount["child"] == "ChildComponent"
    assert mount["assumed"] is False
    assert mount["selector"] == "app-child"

    graph = record["visualGraph"]
    assert graph["kind"] == "component_tree"
    mount_edges = [e for e in graph["edges"] if e["kind"] == "mounts"]
    assert len(mount_edges) == 1
    assert mount_edges[0]["assumed"] is False
    assert "ChildComponent" in mount_edges[0]["to"]
    prop_edges = [e for e in graph["edges"] if e["kind"] == "passes_prop"]
    assert any(e["label"] == "label" for e in prop_edges)


def test_external_template_url_mounts(tmp_path: Path):
    (tmp_path / "child.ts").write_text(
        "@Component({ selector: 'app-tile', template: 'x' })\nexport class Tile {}\n"
    )
    (tmp_path / "host.component.html").write_text("<app-tile></app-tile>\n")
    (tmp_path / "host.component.ts").write_text(
        "@Component({ selector: 'app-host', templateUrl: './host.component.html' })\n"
        "export class HostComponent {}\n"
    )
    record = build_angular_chunk_record(
        tmp_path,
        ChunkPlan("HostComponent", "UI", "angular", "host.component.ts", 20, "small"),
        {"frontend": "angular", "backend": []},
    )
    assert any(m["child"] == "Tile" for m in record["jsxMounts"])


def test_graph_builder_never_invents_from_empty_mounts():
    record = {
        "filePath": "x.ts",
        "angularComponent": {
            "name": "X",
            "selector": "app-x",
            "templateUrl": None,
            "line": 1,
            "assumed": False,
        },
        "inputs": [],
        "outputs": [],
        "injectTokens": [],
        "jsxMounts": [],
    }
    graph = build_angular_selector_tree(record)
    assert graph is not None  # selector provides edge remains
    assert not any(e["kind"] == "mounts" for e in graph["edges"])


def test_at_for_control_flow_marks_assumed(tmp_path: Path):
    (tmp_path / "child.ts").write_text(
        "@Component({ selector: 'app-row', template: 'r' })\nexport class Row {}\n"
    )
    idx = build_selector_index(tmp_path)
    tmpl = "@for (item of items) {\n  <app-row></app-row>\n}\n"
    mounts = extract_template_mounts("Host", tmpl, idx)
    assert len(mounts) == 1
    assert mounts[0].assumed is True
