"""Tree-sitter substrate — wiring + probe locks (no invent).

EXTRACTOR_VERSION 25: Go/TSX/Java/Rust/Express span overlays + Vue
dual-parse under CEV_TREE_SITTER. Flag off keeps regex parity.
CI sets CEV_TREE_SITTER=1; missing grammar still falls back to regex.
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


def test_extractor_version_is_24_for_tree_sitter_wiring():
    assert EXTRACTOR_VERSION == 25


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


def test_go_wired_names_match_when_flag_on(monkeypatch):
    """Flag-on overlay keeps function names; spans come from the probe when matched."""
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
    assert tree_sitter_decl_names_or_fallback(src) == ["Visible"]
    # Wired: flag-on line_range comes from the clean probe node.
    decls = probe_go_declarations(src)
    assert decls is not None
    assert on[0].line_range == decls[0].line_range


def test_go_name_mismatch_falls_back_to_regex(monkeypatch):
    """When probe function names diverge from regex, keep the full regex path."""
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = """package main

func Visible() {
\tprintln("x")
}
"""
    # Force a fake mismatch by patching the probe return.
    import src.extract.go.tree_sitter_probe as probe_mod

    real = probe_mod.probe_go_declarations

    def _wrong(text):
        decls = real(text)
        if not decls:
            return decls
        # Rename first function so overlay refuses.
        from src.extract.go.tree_sitter_probe import GoDeclSpan
        return [GoDeclSpan(kind=d.kind, name="Other", line_range=d.line_range) if i == 0 else d
                for i, d in enumerate(decls)]

    monkeypatch.setattr(probe_mod, "probe_go_declarations", _wrong)
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    # Re-enable after capturing regex baseline via extract with flag off.
    off = extract_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_functions(src)
    assert [f.line_range for f in on] == [f.line_range for f in off]


def test_missing_grammar_raises_parser_unavailable(monkeypatch):
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    load_language.cache_clear()
    # Unregistered language key → ParserUnavailable / try_parse None.
    with pytest.raises(ParserUnavailable):
        parse_source("IDENTIFICATION DIVISION.", "cobol")
    assert try_parse("IDENTIFICATION DIVISION.", "cobol") is None
    load_language.cache_clear()


def test_missing_grammar_falls_back_to_regex_extract(monkeypatch):
    """Flag on + substrate unavailable → extract keeps regex (fail-open).

    Proves CI can set CEV_TREE_SITTER=1 without inventing when a grammar
    is missing: try_parse → None → probe → None → regex path unchanged.
    """
    src = """package main

func Visible() {
\tprintln("x")
}
"""
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    import src.extract.go.tree_sitter_probe as probe_mod

    monkeypatch.setattr(probe_mod, "try_parse", lambda *_a, **_k: None)
    on = extract_functions(src)
    assert [f.name for f in on] == [f.name for f in off] == ["Visible"]
    assert [f.line_range for f in on] == [f.line_range for f in off]
    assert probe_go_declarations(src) is None
    assert tree_sitter_decl_names_or_fallback(src) is None


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


def test_tsx_wired_names_match_when_flag_on(monkeypatch):
    """Flag-on overlay keeps function names when probe matches 1:1."""
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.extract import (
        extract_functions,
        tree_sitter_decl_names_or_fallback as tsx_names,
    )
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations

    src = "export function Visible() { return <div/>; }\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_functions(src)
    assert [f.name for f in off] == [f.name for f in on] == ["Visible"]
    assert tsx_names(src) == ["Visible"]
    decls = probe_tsx_declarations(src)
    assert decls is not None
    assert on[0].line_range == decls[0].line_range


def test_tsx_never_invents_jsx_mounts_from_probe(monkeypatch):
    """Probe lists decls only — no element tag names as declarations."""
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.react.tree_sitter_probe import probe_tsx_declarations

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    src = "export function App() { return <UnregisteredChild />; }\n"
    decls = probe_tsx_declarations(src)
    assert decls is not None
    assert "UnregisteredChild" not in {d.name for d in decls}


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


# --- Vue SFC dual-parse honesty ---


def test_vue_dual_parse_flag_off(monkeypatch):
    pytest.importorskip("tree_sitter_html")
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.vue.tree_sitter_probe import probe_vue_sfc, honest_mount_children
    from src.extract.vue.extract import extract_vue_sfc

    sfc = """
<script setup lang=\"ts\">
import HelloWorld from './HelloWorld.vue'
</script>
<template>
  <HelloWorld />
  <UnmatchedThing />
</template>
"""
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    assert probe_vue_sfc(sfc) is None
    assert honest_mount_children(sfc) is None
    # Regex path keeps both PascalCase tags when flag is off.
    facts = extract_vue_sfc(sfc)
    assert {c["child"] for c in facts.components} == {"HelloWorld", "UnmatchedThing"}


def test_vue_dual_parse_skips_unmatched_mounts(monkeypatch):
    pytest.importorskip("tree_sitter_html")
    pytest.importorskip("tree_sitter_typescript")
    from src.extract.vue.extract import extract_vue_sfc
    from src.extract.vue.tree_sitter_probe import probe_vue_sfc

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    sfc = """
<script setup lang=\"ts\">
import HelloWorld from './HelloWorld.vue'
const LocalComp = defineComponent({})
</script>
<template>
  <HelloWorld />
  <LocalComp />
  <UnmatchedThing />
  <div>x</div>
</template>
"""
    result = probe_vue_sfc(sfc)
    assert result is not None
    assert "HelloWorld" in result.honest_mount_names
    assert "LocalComp" in result.honest_mount_names
    assert "UnmatchedThing" not in result.honest_mount_names
    facts = extract_vue_sfc(sfc)
    assert {c["child"] for c in facts.components} == {"HelloWorld", "LocalComp"}


def test_vue_dual_parse_empty_script_falls_back(monkeypatch):
    """No script identifiers → mismatch → regex PascalCase path kept."""
    pytest.importorskip("tree_sitter_html")
    pytest.importorskip("tree_sitter_javascript")
    from src.extract.vue.tree_sitter_probe import probe_vue_sfc
    from src.extract.vue.extract import extract_vue_sfc

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    sfc = """
<script setup>
// no imports / decls
</script>
<template>
  <OrphanMount />
</template>
"""
    assert probe_vue_sfc(sfc) is None
    facts = extract_vue_sfc(sfc)
    assert {c["child"] for c in facts.components} == {"OrphanMount"}


# --- Rust + Express wired function span overlays (no mount/route invent) ---


def test_rust_probe_flag_and_decls(monkeypatch):
    pytest.importorskip("tree_sitter_rust")
    from src.extract.rust.tree_sitter_probe import probe_rust_declarations
    from src.extract.rust.extract import tree_sitter_decl_names_or_fallback as rust_names

    src = "pub fn hello() {}\npub struct S {}\nimpl S { fn m(&self) {} }\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    assert probe_rust_declarations(src) is None
    assert rust_names(src) is None
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    decls = probe_rust_declarations(src)
    assert decls is not None
    names = {d.name for d in decls}
    assert {"hello", "S", "m"} <= names
    assert "hello" in rust_names(src)


def test_rust_wired_fn_spans_when_flag_on(monkeypatch):
    """Flag-on overlays function line_range; never invents nest/route facts."""
    pytest.importorskip("tree_sitter_rust")
    from src.extract.rust.extract import extract_rust
    from src.extract.rust.tree_sitter_probe import probe_rust_declarations

    src = "pub fn hello() {\n    let x = 1;\n}\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_rust(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_rust(src)
    assert [f["name"] for f in off.functions] == [f["name"] for f in on.functions] == ["hello"]
    decls = probe_rust_declarations(src)
    assert decls is not None
    fn_decl = next(d for d in decls if d.kind == "function" and d.name == "hello")
    assert on.functions[0]["line_range"] == fn_decl.line_range
    assert off.functions[0]["line_range"][0] == off.functions[0]["line"]
    # Routes / nests stay empty — span overlay must not invent them.
    assert on.routes == []
    assert off.routes == []


def test_rust_name_mismatch_falls_back_to_regex(monkeypatch):
    pytest.importorskip("tree_sitter_rust")
    from src.extract.rust.extract import extract_rust
    import src.extract.rust.tree_sitter_probe as probe_mod
    from src.extract.rust.tree_sitter_probe import RustDeclSpan

    src = "pub fn hello() {\n    let x = 1;\n}\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_rust(src)
    real = probe_mod.probe_rust_declarations

    def _wrong(text):
        decls = real(text)
        if not decls:
            return decls
        return [
            RustDeclSpan(kind=d.kind, name="other", line_range=d.line_range)
            if d.kind == "function" and d.name == "hello"
            else d
            for d in decls
        ]

    monkeypatch.setattr(probe_mod, "probe_rust_declarations", _wrong)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_rust(src)
    assert [f["line_range"] for f in on.functions] == [f["line_range"] for f in off.functions]


def test_rust_grammar_loads():
    pytest.importorskip("tree_sitter_rust")
    parsed = parse_source("fn main() {}", "rust")
    assert parsed.root is not None


def test_express_js_probe_flag_and_decls(monkeypatch):
    pytest.importorskip("tree_sitter_javascript")
    from src.extract.express.tree_sitter_probe import probe_js_declarations
    from src.extract.express.extract import tree_sitter_decl_names_or_fallback as js_names

    src = "const foo = () => {};\nfunction bar() {}\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    assert probe_js_declarations(src) is None
    assert js_names(src) is None
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    decls = probe_js_declarations(src)
    assert decls is not None
    assert {d.name for d in decls} >= {"foo", "bar"}
    assert js_names(src) is not None


def test_express_wired_fn_spans_when_flag_on(monkeypatch):
    """Flag-on overlays function/const_fn spans; never invents mounts/routes/mw."""
    pytest.importorskip("tree_sitter_javascript")
    from src.extract.express.extract import extract_express, extract_express_functions
    from src.extract.express.tree_sitter_probe import probe_js_declarations

    src = "const foo = () => {\n  return 1;\n};\nfunction bar() {\n  return 2;\n}\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_express_functions(src)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_express_functions(src)
    assert [f["name"] for f in off] == [f["name"] for f in on] == ["foo", "bar"]
    decls = probe_js_declarations(src)
    assert decls is not None
    ts_fns = [d for d in decls if d.kind in ("function", "const_fn")]
    assert [d.name for d in ts_fns] == ["foo", "bar"]
    assert on[0]["line_range"] == ts_fns[0].line_range
    assert on[1]["line_range"] == ts_fns[1].line_range
    # Mount/route/mw path untouched by the function overlay.
    routes, mw, mounts = extract_express(src)
    assert routes == []
    assert mounts == {}
    assert mw == [] or all(m.name for m in mw)  # no invented router mounts


def test_express_name_mismatch_falls_back_to_regex(monkeypatch):
    pytest.importorskip("tree_sitter_javascript")
    from src.extract.express.extract import extract_express_functions
    import src.extract.express.tree_sitter_probe as probe_mod
    from src.extract.express.tree_sitter_probe import JsDeclSpan

    src = "function bar() {\n  return 2;\n}\n"
    monkeypatch.delenv("CEV_TREE_SITTER", raising=False)
    off = extract_express_functions(src)
    real = probe_mod.probe_js_declarations

    def _wrong(text):
        decls = real(text)
        if not decls:
            return decls
        return [
            JsDeclSpan(kind=d.kind, name="other", line_range=d.line_range) if i == 0 else d
            for i, d in enumerate(decls)
        ]

    monkeypatch.setattr(probe_mod, "probe_js_declarations", _wrong)
    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    on = extract_express_functions(src)
    assert [f["line_range"] for f in on] == [f["line_range"] for f in off]


def test_express_js_catastrophic_falls_back(monkeypatch):
    pytest.importorskip("tree_sitter_javascript")
    from src.extract.express.tree_sitter_probe import probe_js_declarations

    monkeypatch.setenv("CEV_TREE_SITTER", "1")
    assert probe_js_declarations("function {\n" * 20) is None
