from src.narrate.visual_cues import generate_visual_cues, slugify


def _record(important_functions):
    return {"chunkId": "profile-rules-3f9a2c", "importantFunctions": important_functions}


def test_generates_one_cue_per_function_with_line_range():
    record = _record([
        {"name": "validateProfile", "lineRange": [10, 25]},
        {"name": "normalizeEmail", "lineRange": [27, 40]},
    ])
    cues = generate_visual_cues(record)
    assert [c.label for c in cues] == ["validateProfile", "normalizeEmail"]
    assert cues[0].line_range == [10, 25]
    assert cues[0].token == f"VISUAL[HIGHLIGHT:{cues[0].id}]"


def test_skips_functions_with_no_line_range():
    record = _record([{"name": "mystery"}])
    assert generate_visual_cues(record) == []


def test_cue_ids_are_deduplicated_when_names_collide():
    record = _record([
        {"name": "handle", "lineRange": [1, 5]},
        {"name": "handle", "lineRange": [10, 15]},
    ])
    cues = generate_visual_cues(record)
    assert cues[0].id != cues[1].id


def test_cue_ids_are_prefixed_by_chunk_id_for_global_uniqueness():
    record = _record([{"name": "validateProfile", "lineRange": [1, 5]}])
    cues = generate_visual_cues(record)
    assert cues[0].id.startswith("profile-rules-3f9a2c-")


def test_slugify_handles_punctuation_and_case():
    assert slugify("Validate Profile!") == "validate-profile"
    assert slugify("") == "cue"


def test_no_cues_when_no_important_functions():
    assert generate_visual_cues({"chunkId": "x", "importantFunctions": []}) == []
    assert generate_visual_cues({"chunkId": "x"}) == []
