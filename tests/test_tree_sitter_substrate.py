"""Tree-sitter substrate spike — skip/fallback locks (no record invent).

EXTRACTOR_VERSION stays 23: probes do not change chunk-record semantics.
"""

from __future__ import annotations

import os

import pytest

from src.storage.mirror_store import EXTRACTOR_VERSION

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_go")

from src.extract.go.extract import (  # noqa: E402
    extract_functions,
    tree_sitter_decl_names_or_fallback,
)
from src.extract.go.tree_sitter_probe import (  # noqa: E402
    probe_go_declarations,
    probe_go_parse,
)
from src.parse.tree_sitter_support import (  # noqa: E402
    ParserUnavailable,
    catastrophic_parse,
    is_sound,
    line_range,
    load_language,
    parse_source,
    tree_sitter_enabled,
    try_parse,
)


def test_extractor_version_unchanged_by_substrate_spike():
    assert EXTRACTOR_VERSION == 23


def test_runtime_api_is_querycursor_era():
    import tree_sitter

    assert hasattr(tree_sitter, "QueryCursor")


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    assert tree_sitter_enabled() is False
    assert probe_go_declarations("package main\nfunc A() {}\n") is None
    assert tree_sitter_decl_names_or_fallback("package main\nfunc A() {}\n") is None


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_feature_flag_truthy(monkeypatch, value):
    monkeypatch.setenv("CEV_TREE_SITTER", value)
    assert tree_sitter_enabled() is True


def test_parse_go_clean_declarations(monkeypatch):
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = """package main

func Hello() {}

func (s *S) Method() {}

type S struct {
\tX int
}

type Iface interface {
\tMethod()
}
"""
    decls = probe_go_declarations(src)
    assert decls is not None
    by_name = {d.name: d for d in decls}
    assert set(by_name) >= {"Hello", "Method", "S", "Iface"}
    assert by_name["Hello"].kind == "function"
    assert by_name["Method"].kind == "method"
    assert by_name["S"].kind == "type"
    assert by_name["Hello"].line_range[0] == 3

    names = tree_sitter_decl_names_or_fallback(src)
    assert names is not None
    assert "Hello" in names


def test_syntax_error_does_not_raise_and_marks_errors():
    parsed = parse_source("package main\nfunc Broken( {\n", "go")
    assert parsed.had_syntax_errors is True
    assert parsed.error_lines  # at least one ERROR line


def test_damaged_decl_skipped_not_invented(monkeypatch):
    """ERROR regions must not yield invented declaration names."""
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    # Clean sibling + damaged sibling in one file.
    mixed = (
        "package main\n"
        "func Good() {}\n"
        "func Broken( {\n"
    )
    decls = probe_go_declarations(mixed)
    # Either catastrophic fallback (None) or only sound decls (Good).
    if decls is None:
        return
    names = {d.name for d in decls}
    assert "Good" in names
    assert "Broken" not in names


def test_catastrophic_parse_falls_back(monkeypatch):
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    # Nearly all lines damaged → probe returns None → regex path kept.
    garbage = "func {\n" * 20
    assert probe_go_declarations(garbage) is None
    assert tree_sitter_decl_names_or_fallback(garbage) is None


def test_regex_path_unchanged_when_flag_on(monkeypatch):
    """Flag-on probe must not alter regex extract_functions output."""
    src = """package main

func Visible() {
\tprintln("x")
}
"""
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_functions(src)
    assert [f.name for f in off] == [f.name for f in on] == ["Visible"]
    # Probe sees the same name but is not wired into extract_functions yet.
    assert tree_sitter_decl_names_or_fallback(src) == ["Visible"]


def test_missing_grammar_raises_parser_unavailable(monkeypatch):
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    load_language.cache_clear()
    # "rust" is not registered in this spike's GRAMMARS map.
    with pytest.raises(ParserUnavailable):
        parse_source("fn main() {}", "rust")
    assert try_parse("fn main() {}", "rust") is None
    load_language.cache_clear()


def test_line_range_and_is_sound_helpers():
    parsed = parse_source("package main\nfunc Ok() {}\n", "go")
    # Walk to the function_declaration node.
    fn = None
    for child in parsed.root.children:
        if child.type == "function_declaration":
            fn = child
            break
    assert fn is not None
    assert is_sound(fn)
    start, end = line_range(fn)
    assert start == 2 and end >= start


def test_tsx_grammar_loads_when_typescript_package_present():
    pytest.importorskip("tree_sitter_typescript")
    parsed = parse_source("export const X = () => <div/>;", "tsx")
    assert parsed.root is not None


# --- TSX probe (probe-only; regex remains authoritative) ---


def test_tsx_feature_flag_default_off(monkeypatch):
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations
    from src.extract.react.extract import tree_sitter_decl_names_or_fallback as tsx_names

    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    src = "export function App() { return <div/>; }\n"
    assert probe_tsx_declarations(src) is None
    assert tsx_names(src) is None


def test_tsx_probe_clean_declarations(monkeypatch):
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations
    from src.extract.react.extract import tree_sitter_decl_names_or_fallback as tsx_names

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = """
export function App() {
  return <div><Child /></div>;
}
function Child() {
  return <span />;
}
const Memo = () => null;
type Props = { a: string };
interface IFace { x(): void }
class Box { render() { return null; } }
"""
    decls = probe_tsx_declarations(src)
    assert decls is not None
    by_name = {d.name: d for d in decls}
    assert set(by_name) >= {"App", "Child", "Memo", "Props", "IFace", "Box", "render"}
    assert by_name["App"].kind == "function"
    assert by_name["Memo"].kind == "const_fn"
    assert by_name["Props"].kind == "type"
    assert tsx_names(src) is not None
    assert "App" in tsx_names(src)


def test_tsx_probe_skips_damaged_not_invent(monkeypatch):
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    mixed = "function Good() { return null; }\nfunction Broken( {\n"
    decls = probe_tsx_declarations(mixed)
    if decls is None:
        return
    names = {d.name for d in decls}
    assert "Good" in names
    assert "Broken" not in names


def test_tsx_regex_path_unchanged_when_flag_on(monkeypatch):
    """Flag-on probe must not alter regex extract_functions output."""
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.extract import (
        extract_functions,
        tree_sitter_decl_names_or_fallback as tsx_names,
    )

    src = "export function Visible() { return <div/>; }\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_functions(src)
    assert [f.name for f in off] == [f.name for f in on] == ["Visible"]
    assert tsx_names(src) == ["Visible"]


def test_tsx_catastrophic_parse_falls_back(monkeypatch):
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations
    from src.extract.react.extract import tree_sitter_decl_names_or_fallback as tsx_names

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    garbage = "function {\n" * 20
    assert probe_tsx_declarations(garbage) is None
    assert tsx_names(garbage) is None


# --- Java / Spring probe (probe-only; no bean/Impl invent) ---


def test_java_feature_flag_default_off(monkeypatch):
    pytest.importorskip("tree_sitter_java")
    from src.extract.spring.tree_sitter_probe import probe_java_declarations
    from src.extract.spring.extract import tree_sitter_decl_names_or_fallback as java_names

    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    src = "@Service\npublic class Foo {}\n"
    assert probe_java_declarations(src) is None
    assert java_names(src) is None


def test_java_probe_clean_types_and_annotations(monkeypatch):
    pytest.importorskip("tree_sitter_java")
    from src.extract.spring.tree_sitter_probe import probe_java_declarations
    from src.extract.spring.extract import tree_sitter_decl_names_or_fallback as java_names

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = """
package com.example;
import org.springframework.stereotype.Service;
@Service
public class FooService implements FooApi {
  public void run() {}
}
public interface FooApi {
  void run();
}
"""
    decls = probe_java_declarations(src)
    assert decls is not None
    by_kind: dict[str, set[str]] = {}
    for d in decls:
        by_kind.setdefault(d.kind, set()).add(d.name)
    assert "FooService" in by_kind.get("class", set())
    assert "FooApi" in by_kind.get("interface", set())
    assert "run" in by_kind.get("method", set())
    assert "Service" in by_kind.get("annotation", set())
    names = java_names(src)
    assert names is not None
    assert "FooService" in names
    assert "Service" not in names  # annotations excluded from plug-in helper


def test_java_probe_never_invents_impl_from_implements(monkeypatch):
    """Probe may see interface + class names; must not invent *Impl edges."""
    pytest.importorskip("tree_sitter_java")
    from src.extract.spring.tree_sitter_probe import probe_java_declarations
    from src.extract.spring.extract import extract_spring

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = """
public interface PaymentApi { void pay(); }
public class CashPayment implements PaymentApi {
  public void pay() {}
}
"""
    decls = probe_java_declarations(src)
    assert decls is not None
    names = {d.name for d in decls}
    assert "PaymentApi" in names and "CashPayment" in names
    # No invented *Impl node name from implements alone.
    assert not any(n.endswith("Impl") for n in names)
    # Regex extract path unchanged (no stereotype → empty types).
    types, routes = extract_spring(src)
    assert types == [] and routes == []


def test_java_regex_extract_spring_unchanged_when_flag_on(monkeypatch):
    pytest.importorskip("tree_sitter_java")
    from src.extract.spring.extract import extract_spring

    src = """
@Service
public class FooService {
  public void run() {}
}
"""
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off_types, off_routes = extract_spring(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on_types, on_routes = extract_spring(src)
    assert [t.name for t in off_types] == [t.name for t in on_types] == ["FooService"]
    assert off_routes == on_routes == []


def test_java_catastrophic_parse_falls_back(monkeypatch):
    pytest.importorskip("tree_sitter_java")
    from src.extract.spring.tree_sitter_probe import probe_java_declarations
    from src.extract.spring.extract import tree_sitter_decl_names_or_fallback as java_names

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    garbage = "public class {\n" * 20
    assert probe_java_declarations(garbage) is None
    assert java_names(garbage) is None


def test_java_grammar_loads():
    pytest.importorskip("tree_sitter_java")
    parsed = parse_source("public class A {}", "java")
    assert parsed.root is not None
    assert not catastrophic_parse(parsed)
