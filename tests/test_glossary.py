from src.narrate.glossary import (
    ContinuityGlossary,
    dependency_first_order,
    back_references,
    forward_previews,
)


def test_dependency_first_order_is_deterministic_and_puts_isolated_chunks_first():
    records = [
        {"chunkId": "b", "featureMapping": ["a"]},
        {"chunkId": "a", "featureMapping": []},
        {"chunkId": "c", "featureMapping": ["a", "b"]},
    ]
    order = dependency_first_order(records)
    assert order == ["a", "b", "c"]


def test_dependency_first_order_ties_broken_by_chunk_id():
    records = [
        {"chunkId": "z", "featureMapping": []},
        {"chunkId": "x", "featureMapping": []},
        {"chunkId": "y", "featureMapping": []},
    ]
    assert dependency_first_order(records) == ["x", "y", "z"]


def test_dependency_first_order_handles_cycles_without_hanging():
    records = [
        {"chunkId": "a", "featureMapping": ["b"]},
        {"chunkId": "b", "featureMapping": ["a"]},
    ]
    order = dependency_first_order(records)
    assert sorted(order) == ["a", "b"]


def test_glossary_register_and_get():
    glossary = ContinuityGlossary()
    glossary.register("a", "Alumni Admin Grid", "Renders the admin table of alumni records.")
    entry = glossary.get("a")
    assert entry.canonical_name == "Alumni Admin Grid"
    assert glossary.get("missing") is None


def test_back_references_only_includes_already_processed_links():
    glossary = ContinuityGlossary()
    glossary.register("a", "A", "summary a")
    glossary.register("b", "B", "summary b")
    record_c = {"chunkId": "c", "featureMapping": ["a", "d"]}
    glossary.register("c", "C", "summary c")
    # "d" was never registered before "c" -> not a back-reference even
    # though it's named in featureMapping.
    assert back_references("c", record_c, glossary) == ["a"]


def test_forward_previews_only_includes_real_unprocessed_links():
    glossary = ContinuityGlossary()
    record_a = {"chunkId": "a", "featureMapping": ["b", "ghost"]}
    glossary.register("a", "A", "summary a")
    all_ids = {"a", "b", "c"}
    # "ghost" is not a real chunk id -> excluded; "b" is real and not
    # yet processed -> included.
    assert forward_previews("a", record_a, all_ids, glossary) == ["b"]


def test_forward_previews_excludes_self_reference():
    glossary = ContinuityGlossary()
    record_a = {"chunkId": "a", "featureMapping": ["a"]}
    glossary.register("a", "A", "summary a")
    assert forward_previews("a", record_a, {"a"}, glossary) == []
