from src.extract.function_context import (
    build_function_context,
    is_exported,
    leading_doc_comment,
)

TS_SOURCE = '''/**
 * The bearer token for an API call, or null when signed out.
 *
 * @param force - whether to refresh
 */
export async function currentIdToken() {
  return auth ? getAuth() : null;
}

// Plain line comment above a helper,
// continued onto a second line.
function helper(raw, limit) {
  if (!raw) {
    throw new Error('missing');
  }
  return helper2(raw);
}

function helper2(value) {
  return value;
}

function undocumented() {
  return 1;
}
'''


def lines_of(source: str) -> list[str]:
    return source.splitlines()


def test_jsdoc_block_is_read_as_prose_without_markers_or_tags():
    lines = lines_of(TS_SOURCE)
    doc = leading_doc_comment(lines, 6)
    assert doc == "The bearer token for an API call, or null when signed out."


def test_consecutive_line_comments_are_joined():
    lines = lines_of(TS_SOURCE)
    doc = leading_doc_comment(lines, 12)
    assert doc == "Plain line comment above a helper, continued onto a second line."


def test_function_with_no_comment_above_gets_none():
    lines = lines_of(TS_SOURCE)
    assert leading_doc_comment(lines, 23) is None


def test_blank_line_between_comment_and_function_breaks_the_link():
    source = "// Belongs to something else.\n\nfunction thing() {\n  return 1;\n}\n"
    assert leading_doc_comment(lines_of(source), 3) is None


def test_boilerplate_comments_are_not_treated_as_descriptions():
    source = "// Copyright 2026 Example Inc. All rights reserved.\nfunction thing() {}\n"
    assert leading_doc_comment(lines_of(source), 2) is None


def test_secrets_in_a_comment_are_redacted_before_they_can_be_spoken():
    source = (
        "// Use the key AKIAIOSFODNN7EXAMPLE when calling this in staging.\n"
        "function thing() {}\n"
    )
    doc = leading_doc_comment(lines_of(source), 2)
    assert doc is not None
    assert "AKIAIOSFODNN7EXAMPLE" not in doc


def test_go_export_is_the_leading_capital():
    assert is_exported("func New(ctx context.Context) {", "New", "go") is True
    assert is_exported("func parseDraft(row []string) {", "parseDraft", "go") is False


def test_ts_export_is_the_export_keyword():
    assert is_exported("export function a() {", "a", "ts") is True
    assert is_exported("function a() {", "a", "ts") is False


def test_call_graph_links_callers_and_callees_within_the_chunk():
    lines = lines_of(TS_SOURCE)
    entries = [
        {"name": "helper", "signature": "function helper(raw, limit) {", "lineRange": [12, 17]},
        {"name": "helper2", "signature": "function helper2(value) {", "lineRange": [19, 21]},
    ]
    helper = build_function_context(
        "helper", entries[0]["signature"], [12, 17], lines, entries, "ts",
    )
    helper2 = build_function_context(
        "helper2", entries[1]["signature"], [19, 21], lines, entries, "ts",
    )
    assert helper["calls"] == ["helper2"]
    assert helper2["calledBy"] == ["helper"]
    assert helper["raisesError"] is True
    assert helper["params"] == ["raw", "limit"]
    assert helper["lineCount"] == 6


def test_api_calls_and_side_effects_are_attributed_to_the_right_function():
    """A call on line 30 must not be credited to a function ending at 20."""
    class Call:
        def __init__(self, line):
            self.method, self.url, self.line = "GET", "/api/x", line

    class Effect:
        def __init__(self, line):
            self.kind, self.line = "navigation", line

    lines = lines_of(TS_SOURCE)
    entries = [{"name": "helper", "signature": "function helper() {", "lineRange": [12, 17]}]
    context = build_function_context(
        "helper", "function helper() {", [12, 17], lines, entries, "ts",
        api_calls=[Call(14), Call(30)], side_effects=[Effect(99)],
    )
    assert context["apiCalls"] == [{"method": "GET", "url": "/api/x"}]
    assert context["sideEffects"] == []


def test_go_side_effect_tuples_are_handled_like_ts_objects():
    """go_extractor returns (kind, line) tuples while ts_extractor
    returns objects; the context builder must take either."""
    lines = lines_of(TS_SOURCE)
    entries = [{"name": "helper", "signature": "func helper() {", "lineRange": [12, 17]}]
    context = build_function_context(
        "helper", "func helper() {", [12, 17], lines, entries, "go",
        side_effects=[("db_write", 13), ("logging", 99)],
    )
    assert context["sideEffects"] == ["db_write"]
