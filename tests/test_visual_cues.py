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


def test_event_handlers_with_a_line_range_get_their_own_cue():
    """The narration says "the inline_onClose_L50 handler responds to..."
    — without a cue, nothing on screen points at line 50."""
    record = {
        "chunkId": "alumni-06f407dc",
        "importantFunctions": [{"name": "ProfilePage", "lineRange": [17, 70]}],
        "eventHandlers": [
            {"name": "handleSubmit", "lineRange": [21, 21]},
            {"name": "inline_onClose_L50", "lineRange": [50, 50]},
        ],
    }
    cues = generate_visual_cues(record)
    by_label = {c.label: c for c in cues}
    assert by_label["inline_onClose_L50"].line_range == [50, 50]
    assert by_label["inline_onClose_L50"].source_field == "eventHandlers"
    assert by_label["handleSubmit"].line_range == [21, 21]


def test_entries_without_a_line_range_still_produce_no_cue():
    """An honest gap stays a gap rather than a fabricated line number."""
    record = {
        "chunkId": "x",
        "eventHandlers": [{"name": "mystery"}, {"name": "partial", "lineRange": [7]}],
    }
    assert generate_visual_cues(record) == []


def test_a_handler_and_a_function_sharing_a_name_get_separate_cues():
    record = {
        "chunkId": "x",
        "importantFunctions": [{"name": "submit", "lineRange": [1, 5]}],
        "eventHandlers": [{"name": "submit", "lineRange": [20, 20]}],
    }
    cues = generate_visual_cues(record)
    assert len(cues) == 2
    assert cues[0].id != cues[1].id
    assert {c.source_field for c in cues} == {"importantFunctions", "eventHandlers"}
