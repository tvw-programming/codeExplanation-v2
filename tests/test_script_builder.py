from src.narrate.script_builder import (
    build_purpose_beat,
    build_connections_beat,
    build_flow_sentences,
    build_flow_beats,
    build_recap_beat,
    build_narration_script,
    estimate_seconds,
    HEDGE_PHRASE,
    MAX_FLOW_SECONDS,
)
from src.narrate.glossary import GlossaryEntry
from src.narrate.visual_cues import generate_visual_cues


def test_purpose_beat_names_feature_and_framework_before_mechanism():
    record = {"featureName": "Profile Rules", "frameworkOrLibrary": ["React"], "eventHandlers": []}
    beat = build_purpose_beat(record)
    assert beat.startswith("This section covers Profile Rules, built with React.")


def test_purpose_beat_mentions_route_count_when_backend_chunk():
    record = {"featureName": "Alumni Repository", "frameworkOrLibrary": ["Go Fiber"],
              "routes": [{}, {}], "eventHandlers": []}
    beat = build_purpose_beat(record)
    assert "2 backend routes" in beat


def test_purpose_beat_mentions_handler_count_when_frontend_chunk():
    record = {"featureName": "Alumni Admin Grid", "frameworkOrLibrary": ["React"],
              "eventHandlers": [{}], "routes": []}
    beat = build_purpose_beat(record)
    assert "1 event handler" in beat and "handlers" not in beat.split("handler")[1][:1]


def test_connections_beat_standalone_when_no_links():
    record = {"featureName": "Profile Rules"}
    beat = build_connections_beat(record, [], [])
    assert "stands on its own" in beat


def test_connections_beat_uses_canonical_names_for_back_and_forward_refs():
    record = {"featureName": "Profile Rules"}
    back = [GlossaryEntry("a", "Alumni Admin Grid", "x")]
    forward = [GlossaryEntry("b", "Profile API", "y")]
    beat = build_connections_beat(record, back, forward)
    assert "Alumni Admin Grid" in beat and "covered earlier" in beat
    assert "Profile API" in beat and "covered later" in beat


def test_flow_sentence_for_important_function_includes_visual_cue_token():
    record = {
        "chunkId": "profile-rules-3f9a2c",
        "importantFunctions": [{"name": "validateProfile", "lineRange": [10, 25]}],
    }
    cues = generate_visual_cues(record)
    sentences = build_flow_sentences(record, cues)
    assert any("VISUAL[HIGHLIGHT:" in s for s in sentences)
    assert any("validateProfile" in s for s in sentences)


def test_flow_sentence_hedges_assumed_route_with_fixed_phrase():
    record = {"routes": [{"method": "GET", "path": "/alumni/:id", "assumed": True}]}
    sentences = build_flow_sentences(record, [])
    assert sentences[0].startswith(HEDGE_PHRASE)


def test_flow_sentence_speaks_verified_route_plainly():
    record = {"routes": [{"method": "GET", "path": "/alumni/:id", "assumed": False}]}
    sentences = build_flow_sentences(record, [])
    assert not sentences[0].startswith(HEDGE_PHRASE)


def test_flow_beats_single_beat_when_short():
    sentences = ["The handleSubmit handler responds to a user action event."]
    beats = build_flow_beats(sentences)
    assert len(beats) == 1


def test_flow_beats_split_when_over_budget_and_each_half_within_budget():
    sentences = [f"The handleAction{i} handler responds to a user action event." for i in range(20)]
    beats = build_flow_beats(sentences)
    assert len(beats) == 2
    for beat in beats:
        assert estimate_seconds(beat) <= MAX_FLOW_SECONDS + 1  # small float tolerance


def test_flow_beats_never_splits_mid_sentence():
    sentences = [f"The handleAction{i} handler responds to a user action event." for i in range(20)]
    beats = build_flow_beats(sentences)
    combined = " ".join(beats)
    # Every original sentence must appear whole in the combined output.
    for s in sentences:
        assert s in combined


def test_flow_beats_fallback_text_when_no_flow_items():
    beats = build_flow_beats([])
    assert len(beats) == 1
    assert "no further steps" in beats[0]


def test_recap_beat_names_feature_and_sets_scope_limit():
    beat = build_recap_beat({"featureName": "Profile Rules"})
    assert beat.startswith("That covers what Profile Rules does.")
    assert "left for review" in beat


def test_build_narration_script_never_speaks_notes_field():
    record = {
        "chunkId": "x",
        "featureName": "Profile Rules",
        "frameworkOrLibrary": ["React"],
        "notes": "SECRET_INTERNAL_REVIEWER_ONLY_TEXT",
        "eventHandlers": [],
    }
    script = build_narration_script(record, [], [])
    full_text = " ".join([script.purpose, script.connections, *script.flow, script.recap])
    assert "SECRET_INTERNAL_REVIEWER_ONLY_TEXT" not in full_text


def test_build_narration_script_flags_within_target_range():
    # A chunk with enough flow content to land in the 90-180s target band.
    record = {
        "chunkId": "x",
        "featureName": "Alumni Admin Grid",
        "frameworkOrLibrary": ["React"],
        "eventHandlers": [{"name": f"handleAction{i}", "eventType": "user action", "assumed": False}
                           for i in range(15)],
    }
    script = build_narration_script(record, [], [])
    assert 90 <= script.estimated_seconds <= 180
    assert script.within_target_range is True


def test_build_narration_script_reports_out_of_range_without_erroring():
    record = {"chunkId": "x", "featureName": "Tiny Chunk", "frameworkOrLibrary": ["React"], "eventHandlers": []}
    script = build_narration_script(record, [], [])
    assert script.within_target_range is False
    assert script.estimated_seconds < 90


def test_cue_token_precedes_its_sentence_so_the_highlight_is_not_late():
    """The token's position decides the cue's anchor word. Appended, the
    line would light up as the narrator finished the sentence about it."""
    record = {
        "chunkId": "c",
        "featureName": "alumni",
        "importantFunctions": [{"name": "ProfilePage", "lineRange": [17, 70]}],
    }
    script = build_narration_script(record, [], [])
    cue = script.visual_cues[0]
    flow = " ".join(script.flow)
    assert flow.index(cue.token) < flow.index("The ProfilePage function runs next.")


def test_event_handler_sentences_carry_their_cue_token():
    record = {
        "chunkId": "c",
        "featureName": "alumni",
        "eventHandlers": [
            {"name": "inline_onClose_L50", "lineRange": [50, 50],
             "eventType": "user_action", "assumed": True},
        ],
    }
    script = build_narration_script(record, [], [])
    assert len(script.visual_cues) == 1
    assert script.visual_cues[0].token in " ".join(script.flow)
