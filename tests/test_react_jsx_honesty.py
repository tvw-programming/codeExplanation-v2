"""React JSX honesty enrichments (EXTRACTOR_VERSION 20)."""

from __future__ import annotations

from src.extract import ts_extractor as ts
from src.extract.react import extract as react_extract
from src.storage.mirror_store import EXTRACTOR_VERSION


def test_extractor_version_22():
    assert EXTRACTOR_VERSION == 23


def test_nested_brace_props_captured():
    attrs = ' style={{ color: "red", margin: 0 }} onClick={() => setX(1)} name={userName}'
    props = {p.name: p for p in react_extract._parse_jsx_props(attrs)}
    assert "style" in props
    assert props["style"].value_kind == "expression"
    assert "color" in (props["style"].value_preview or "")
    assert props["onClick"].value_preview is not None
    assert "setX" in (props["onClick"].value_preview or "")
    assert props["name"].value_preview == "userName"


def test_memo_forwardref_wrappers_on_bind_name():
    text = """
import { memo, forwardRef } from "react";

export const Card = memo(function Card({ title }) {
  return <Inner title={title} style={{ padding: 8 }} />;
});

const Input = memo(forwardRef(function Input(props, ref) {
  useEffect(() => {}, []);
  return <span ref={ref} />;
}));
"""
    functions = ts.extract_functions(text)
    by_name = {f.name: f for f in functions}
    assert "Card" in by_name
    assert by_name["Card"].wrappers == ["memo"]
    assert "Input" in by_name
    assert by_name["Input"].wrappers == ["memo", "forwardRef"]
    mounts, _ = ts.extract_jsx_mounts(text, functions, "File")
    children = {(m.parent, m.child) for m in mounts}
    assert ("Card", "Inner") in children
    card_inner = next(m for m in mounts if m.child == "Inner")
    prop_names = {p.name for p in card_inner.props}
    assert "title" in prop_names
    assert "style" in prop_names


def test_hook_owner_innermost_function_not_file_stem_guess():
    text = """
export function Outer() {
  useState(0);
  return null;
}
function helper() {
  useEffect(() => {}, []);
}
"""
    functions = ts.extract_functions(text)
    hooks = ts.extract_hooks(text, functions, "File")
    by_name = {h.name: h for h in hooks}
    assert by_name["useState"].owner == "Outer"
    assert by_name["useState"].assumed is False
    assert by_name["useEffect"].owner == "helper"
    assert by_name["useEffect"].assumed is False


def test_hook_without_enclosing_function_is_assumed():
    text = "useMemo(() => 1, []);\n"
    hooks = ts.extract_hooks(text, [], "Orphan")
    assert len(hooks) == 1
    assert hooks[0].owner == "Orphan"
    assert hooks[0].assumed is True


def test_default_memo_export_keeps_inner_name():
    text = """
export default memo(function Button({ label }) {
  return <Icon />;
});
"""
    functions = ts.extract_functions(text)
    assert any(f.name == "Button" and f.wrappers == ["memo"] for f in functions)
    mounts, _ = ts.extract_jsx_mounts(text, functions, "File")
    assert any(m.parent == "Button" and m.child == "Icon" for m in mounts)
