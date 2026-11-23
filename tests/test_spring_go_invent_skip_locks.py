"""Hard skip-locks: Spring bean-index typed Impl + Go method-set Impl (never invent).

Multi-technology spike in one suite. Prefer empty/skip over guessed edges.
EXTRACTOR_VERSION stays 25 unless extract/record semantics change (they do not).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract import go_extractor as go
from src.extract.go.record import build_backend_go_chunk_record
from src.extract.spring import extract_spring, build_spring_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION

FIX = Path(__file__).resolve().parent / "fixtures"
SPRING_TEMPT = FIX / "spring_bean_index_tempt"
GO_TEMPT = FIX / "go_method_set_tempt"

# APIs that must never exist — invent paths from research blueprints / deferred plan.
SPRING_INVENT_APIS = (
    "build_bean_index",
    "resolve_bean_impl",
    "resolve_injection",
    "index_component_scan",
    "typed_impl_for",
    "infer_impl_from_implements",
)
GO_INVENT_APIS = (
    "infer_impl_from_method_set",
    "method_set_satisfies",
    "build_impl_index",
    "resolve_interface_impl",
)


def test_extractor_version_unchanged_without_semantic_change():
    """Skip-locks only — no record invent → keep EXTRACTOR_VERSION 25."""
    assert EXTRACTOR_VERSION == 25


# ---------------------------------------------------------------------------
# Spring — bean-index typed Impl refusal
# ---------------------------------------------------------------------------


def test_spring_invent_apis_absent():
    import src.extract.spring.extract as spring_extract
    import src.extract.spring as spring_pkg

    for name in SPRING_INVENT_APIS:
        assert not hasattr(spring_extract, name), name
        assert not hasattr(spring_pkg, name), name
        assert name not in dir(spring_extract)


def test_spring_fixture_controller_injectee_stays_interface_not_impl():
    """Controller injects OrderService — never rewrite to OrderServiceImpl."""
    text = (SPRING_TEMPT / "OrderController.java").read_text(encoding="utf-8")
    types, routes = extract_spring(text)
    assert len(types) == 1
    assert types[0].name == "OrderController"
    injectees = types[0].injectees
    assert injectees == [
        {
            "type": "OrderService",
            "field": "orderService",
            "via": "constructor",
            "assumed": False,
        }
    ]
    assert not any("Impl" in (i["type"] or "") for i in injectees)
    assert any(r.path == "/orders" and r.method == "GET" for r in routes)


def test_spring_fixture_impl_file_does_not_bind_interface():
    """``implements OrderService`` + @Service records the class; no iface→Impl edge."""
    text = (SPRING_TEMPT / "OrderServiceImpl.java").read_text(encoding="utf-8")
    types, routes = extract_spring(text)
    assert routes == []
    names = {t.name for t in types}
    assert "OrderServiceImpl" in names
    assert "OrderService" not in names  # bare interface not in this file
    impl = next(t for t in types if t.name == "OrderServiceImpl")
    assert impl.stereotype == "Service"
    assert impl.injectees == []
    # No synthetic proxy / second Impl node
    assert sum(1 for t in types if "Impl" in t.name) == 1


def test_spring_fixture_bare_interface_is_not_a_bean():
    text = (SPRING_TEMPT / "OrderService.java").read_text(encoding="utf-8")
    types, routes = extract_spring(text)
    assert types == []
    assert routes == []


def test_spring_fixture_app_import_scan_never_seeds_beans():
    text = (SPRING_TEMPT / "App.java").read_text(encoding="utf-8")
    types, routes = extract_spring(text)
    assert types == []
    assert routes == []
    assert "OrderServiceImpl" in text  # temptation present in source
    assert not any("Impl" in t.name for t in types)


def test_spring_fixture_jpa_repo_no_proxy_impl():
    text = (SPRING_TEMPT / "OrderRepository.java").read_text(encoding="utf-8")
    types, routes = extract_spring(text)
    assert len(types) == 1
    assert types[0].name == "OrderRepository"
    assert types[0].kind == "interface"
    assert types[0].stereotype == "Repository"
    assert routes == []
    assert not any("Impl" in t.name for t in types)
    assert not any(t.name.startswith("Simple") for t in types)


def test_spring_tempt_tree_di_graph_never_rewrites_to_impl(tmp_path: Path):
    """Multi-file temptation tree → di_graph inject target stays OrderService."""
    for src in SPRING_TEMPT.glob("*.java"):
        (tmp_path / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    chunk = ChunkPlan(
        "OrderController",
        "Orders",
        "spring_boot",
        "OrderController.java",
        40,
        "small",
    )
    record = build_spring_chunk_record(
        tmp_path, chunk, {"frontend": None, "backend": ["spring_boot"]},
    )
    assert record["extractorVersion"] == 25
    injectees = record["springTypes"][0]["injectees"]
    assert {i["type"] for i in injectees} == {"OrderService"}
    assert not any("Impl" in i["type"] for i in injectees)

    graph = record["visualGraph"]
    assert graph is not None
    assert graph["kind"] == "di_graph"
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    inject_edges = [e for e in graph["edges"] if e["kind"] == "injects"]
    assert inject_edges
    labels = {nodes_by_id[e["to"]]["label"] for e in inject_edges}
    assert labels == {"OrderService"}
    assert "OrderServiceImpl" not in labels
    # interfaceOnly meta on the injectee node — runtime Impl not invented here
    for e in inject_edges:
        node = nodes_by_id[e["to"]]
        assert node["meta"].get("interfaceOnly") is True
        assert "Impl" not in (node.get("label") or "")


def test_spring_concatenated_temptation_still_refuses_typed_impl_bind():
    """Same-file interface + Impl + controller — still no inject rewrite / bean-index."""
    parts = [
        (SPRING_TEMPT / "OrderService.java").read_text(encoding="utf-8"),
        (SPRING_TEMPT / "OrderServiceImpl.java").read_text(encoding="utf-8"),
        (SPRING_TEMPT / "OrderController.java").read_text(encoding="utf-8"),
    ]
    text = "\n\n".join(parts)
    types, _ = extract_spring(text)
    names = {t.name for t in types}
    assert "OrderServiceImpl" in names
    assert "OrderController" in names
    # Bare interface still not a SpringType without stereotype / Spring Data extend.
    assert "OrderService" not in names
    ctrl = next(t for t in types if t.name == "OrderController")
    assert {i["type"] for i in ctrl.injectees} == {"OrderService"}
    impl = next(t for t in types if t.name == "OrderServiceImpl")
    assert impl.injectees == []


# ---------------------------------------------------------------------------
# Go — method-set Impl inference refusal; explicit var _ only
# ---------------------------------------------------------------------------


def test_go_invent_apis_absent():
    for name in GO_INVENT_APIS:
        assert not hasattr(go, name), name


def test_go_fixture_method_set_alone_never_asserts():
    text = (GO_TEMPT / "repo.go").read_text(encoding="utf-8")
    assert "var _" not in text
    asserts = go.extract_interface_assertions(text)
    assert asserts == []
    ifaces = go.extract_interfaces(text)
    assert len(ifaces) == 1 and ifaces[0].name == "UserRepo"
    methods = {n for n, _ in ifaces[0].methods}
    assert methods == {"FindByID", "Save"}
    structs = go.extract_structs(text)
    assert any(s.name == "userRepo" for s in structs)
    # Matching method set present in source — still zero assertions.
    fn_names = {f.name for f in go.extract_functions(text)}
    assert {"FindByID", "Save"} <= fn_names


def test_go_fixture_explicit_var_underscore_still_recorded():
    text = (GO_TEMPT / "assert_ok.go").read_text(encoding="utf-8")
    asserts = go.extract_interface_assertions(text)
    forms = {(a.interface, a.concrete, a.form) for a in asserts}
    assert ("Closer", "fileHandle", "value_composite") in forms
    assert ("Closer", "fileHandle", "pointer_nil") in forms
    assert all(a.assumed is False for a in asserts)


def test_go_tempt_record_has_empty_assertions_without_var(tmp_path: Path):
    src = GO_TEMPT / "repo.go"
    dest = tmp_path / "repo.go"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    chunk = ChunkPlan(
        chunk_id="go-method-set-tempt",
        file_path="repo.go",
        feature_name="tempt",
        stack="go",
        total_lines=len(dest.read_text(encoding="utf-8").splitlines()),
    )
    record = build_backend_go_chunk_record(
        tmp_path, chunk, {"type": "go", "framework": "fiber"}, None, True,
    )
    assert record["extractorVersion"] == 25
    assert record["interfaceAssertions"] == []
    iface = next(m for m in record["dataModels"] if m.get("kind") == "interface")
    assert iface["name"] == "UserRepo"
    assert "implementors are not" in (record.get("notes") or "").lower() or (
        "method sets" in (iface.get("notes") or "").lower()
        or "method" in (record.get("notes") or "").lower()
    )


def test_go_assert_fixture_record_keeps_only_explicit_path(tmp_path: Path):
    for src in GO_TEMPT.glob("*.go"):
        (tmp_path / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    # Extract the assert file alone — method-set file must not leak invent into it.
    chunk = ChunkPlan(
        chunk_id="go-assert-ok",
        file_path="assert_ok.go",
        feature_name="tempt",
        stack="go",
        total_lines=20,
    )
    record = build_backend_go_chunk_record(
        tmp_path, chunk, {"type": "go", "framework": "fiber"}, None, True,
    )
    concretes = {(a["interface"], a["concrete"]) for a in record["interfaceAssertions"]}
    assert concretes == {("Closer", "fileHandle")}
    assert not any(a["concrete"] == "userRepo" for a in record["interfaceAssertions"])


def test_go_extract_interface_assertions_source_documents_no_method_set():
    """Source / docstring contract: extract_interface_assertions never method-set."""
    src = inspect.getsource(go.extract_interface_assertions)
    assert "method-set" in src.lower() or "never" in src.lower()
    assert "INTERFACE_ASSERT_RE" in src or "var" in src
