from src.render.script_text import strip_visual_tokens, concat_beats


def test_strip_visual_tokens_removes_token_from_text():
    text = "The validateProfile function runs next. VISUAL[HIGHLIGHT:cue-1] It checks the email."
    clean, _ = strip_visual_tokens(text)
    assert "VISUAL" not in clean
    assert clean == "The validateProfile function runs next. It checks the email."


def test_strip_visual_tokens_records_preceding_word_count():
    text = "The validateProfile function runs next. VISUAL[HIGHLIGHT:cue-1] It checks the email."
    clean, indices = strip_visual_tokens(text)
    # "The validateProfile function runs next." = 5 words, so the cue
    # anchors to word index 4 (the last word before it, 0-indexed).
    assert indices["cue-1"] == 4
    assert clean.split()[4] == "next."


def test_strip_visual_tokens_handles_multiple_cues():
    text = "First sentence here. VISUAL[HIGHLIGHT:a] Second one too. VISUAL[HIGHLIGHT:b] Done."
    clean, indices = strip_visual_tokens(text)
    assert indices["a"] < indices["b"]
    assert "VISUAL" not in clean


def test_strip_visual_tokens_cue_at_very_start_anchors_to_zero():
    text = "VISUAL[HIGHLIGHT:a] Hello world."
    clean, indices = strip_visual_tokens(text)
    assert indices["a"] == 0
    assert clean == "Hello world."


def test_strip_visual_tokens_no_cues_returns_unchanged_text():
    text = "Plain narration with no cues at all."
    clean, indices = strip_visual_tokens(text)
    assert clean == text
    assert indices == {}


def test_concat_beats_joins_in_order():
    result = concat_beats("purpose.", "connections.", ["flow1.", "flow2."], "recap.")
    assert result == "purpose. connections. flow1. flow2. recap."
