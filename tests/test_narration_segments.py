from src.render.narration_segments import (
    build_narration_segments,
    segment_label,
    split_sentences,
)
from src.render.timing import TranscriptWord


def words_for(text: str, duration_ms: int) -> list[TranscriptWord]:
    parts = [w for w in text.split() if w]
    slot = duration_ms / len(parts)
    return [
        TranscriptWord(word=w, start_ms=round(i * slot), end_ms=round((i + 1) * slot))
        for i, w in enumerate(parts)
    ]


TEXT = "This section covers alumni. The ProfilePage function runs next. That covers it."


def test_labels_count_up_through_the_alphabet_and_past_it():
    assert segment_label(0) == "A"
    assert segment_label(25) == "Z"
    assert segment_label(26) == "AA"
    assert segment_label(27) == "AB"


def test_splits_on_sentence_boundaries():
    assert split_sentences(TEXT) == [
        "This section covers alumni.",
        "The ProfilePage function runs next.",
        "That covers it.",
    ]


def test_one_segment_per_sentence_with_sequential_labels():
    segments = build_narration_segments(TEXT, words_for(TEXT, 12000), fps=30, duration_ms=12000)
    assert [s["label"] for s in segments] == ["A", "B", "C"]
    assert segments[1]["text"] == "The ProfilePage function runs next."


def test_segments_tile_the_whole_chunk_with_no_gaps():
    """Exactly one segment must be active at any frame, or the panel
    would show nothing highlighted partway through."""
    segments = build_narration_segments(TEXT, words_for(TEXT, 12000), fps=30, duration_ms=12000)
    assert segments[0]["fromFrame"] == 0
    for current, nxt in zip(segments, segments[1:]):
        assert current["toFrame"] == nxt["fromFrame"]
    assert segments[-1]["toFrame"] >= 360


def test_segment_windows_follow_the_word_timings():
    segments = build_narration_segments(TEXT, words_for(TEXT, 12000), fps=30, duration_ms=12000)
    # 13 words over 12s; the second sentence starts at word 4.
    assert 80 <= segments[1]["fromFrame"] <= 130


def test_short_transcript_clamps_and_marks_the_segment_assumed():
    """A real transcript rarely has the same word count as the text it
    was transcribed from; the overflow must be visible, not silent."""
    segments = build_narration_segments(TEXT, words_for("one two three", 3000), fps=30, duration_ms=3000)
    assert segments[-1]["assumed"] is True
    assert "clamped" in (segments[-1]["note"] or "")


def test_no_words_falls_back_to_even_spacing_marked_assumed():
    segments = build_narration_segments(TEXT, [], fps=30, duration_ms=9000)
    assert len(segments) == 3
    assert all(s["assumed"] for s in segments)
    assert segments[0]["fromFrame"] == 0
    assert segments[-1]["toFrame"] == 270


def test_empty_text_produces_no_segments():
    assert build_narration_segments("", words_for("a b", 1000), fps=30, duration_ms=1000) == []
