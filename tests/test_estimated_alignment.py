from src.render.estimated_alignment import build_estimated_words


def test_splits_words_evenly_across_duration():
    words = build_estimated_words("one two three four", 4000)
    assert [w.word for w in words] == ["one", "two", "three", "four"]
    assert words[0].start_ms == 0
    assert words[0].end_ms == 1000
    assert words[-1].start_ms == 3000
    assert words[-1].end_ms == 4000


def test_empty_text_returns_empty_list():
    assert build_estimated_words("", 1000) == []
    assert build_estimated_words("   ", 1000) == []


def test_single_word_spans_full_duration():
    words = build_estimated_words("hello", 2500)
    assert words[0].start_ms == 0
    assert words[0].end_ms == 2500
